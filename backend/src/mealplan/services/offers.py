"""Angebots-Use-Cases (Phase 2).

Die Regel aus ARCHITECTURE.md §5: der letzte *gute* Snapshot bleibt der, den die App
liest. Ein fehlgeschlagener Abruf leert die Angebotsansicht nie - abgelaufene Angebote
verschwinden aber trotzdem, sobald ihr "gültig bis" vorbei ist.

Was in den Plan und auf die Einkaufsliste wirkt (Bonus, Hinweise, Merkliste), nimmt nur
*bestätigte* Zuordnungen: die automatische Zuordnung hält "Gefüllte Paprika" für
Paprika. Bestätigt wird in der Angebote-Ansicht (Stufe 2).

Hat ein Artikel einen Richtpreis, zählt ein Angebot für ihn nur, wenn sein Grundpreis
darunter liegt - und ein Grundpreis, der sich nicht bestimmen lässt, liegt nie darunter.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.enums import SyncKind, SyncStatus, Unit
from ..domain.unit_price import (
    COMPARE_UNIT,
    Compared,
    UnitPrice,
    compare,
    in_article_unit,
    offer_quantity,
    pack_unit_price,
    unit_price,
)
from ..domain.units import trim
from ..matching.normalize import normalize
from ..ports import OfferSnapshotData, OfferSource
from .articles import ValidationError
from .matching import match_snapshot
from .stores import offer_stores, store_ref

LOG = logging.getLogger(__name__)

KEEP_SNAPSHOTS = 6  # pro Laden: drei Wochen Mo+Do - genug zum Nachvollziehen
_FETCH_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class OfferView:
    offer_id: int
    store_id: int
    store_name: str
    raw_name: str
    brand: str | None
    pack: str | None
    category: str | None
    price: Decimal | None
    old_price: Decimal | None
    base_price: str | None
    savings: Decimal | None
    valid_from: str | None
    valid_to: str | None
    article_id: int | None
    article_name: str | None
    match_confirmed: bool
    # Zum Nachprüfen: was im Prospekt steht und woher es kommt
    description: str | None = None
    image_url: str | None = None
    source_url: str | None = None
    market_label: str | None = None
    market_url: str | None = None
    source_detail: str | None = None
    fetched_at: datetime | None = None
    # Richtpreis: der Grundpreis in der Einheit des Artikels und das Urteil darüber
    unit_price: Decimal | None = None
    unit_price_unit: str | None = None
    target_price: Decimal | None = None
    price_verdict: str | None = None  # None = kein Richtpreis | ok | too_expensive | unknown
    # Normalpreis des Artikels (Grundpreis) und wie weit das Angebot davon weg ist:
    # negativ = günstiger als normal. Nur, wenn beide Preise vergleichbar sind.
    regular_unit_price: Decimal | None = None
    normal_diff: Decimal | None = None
    normal_diff_percent: int | None = None
    # Einheit, in der Richt- und Normalpreis des Artikels gelten (kg | l | Stück)
    article_price_unit: str | None = None
    # Der Angebotspreis in dieser Einheit - bei Stück-Angeboten über das Stückgewicht
    # umgerechnet (`compared_via_piece`, ein Schätzwert; `piece_size` sagt, womit).
    compared_price: Decimal | None = None
    compared_via_piece: bool = False
    piece_size: Decimal | None = None
    # Mindestpackung: wie groß das Angebot ist (in der Einheit des Artikels), ab wann es
    # zählt, und das Urteil darüber
    offer_amount: Decimal | None = None
    min_offer_amount: Decimal | None = None
    pack_verdict: str | None = None  # None = keine Grenze | ok | too_small | unknown

    @property
    def counts(self) -> bool:
        """Gilt das Angebot für seinen Artikel? Zugeordnet, nicht über dem Richtpreis und
        nicht kleiner als die Mindestpackung."""
        return self.article_id is not None and _passes(self.price_verdict, self.pack_verdict)


VERDICT_OK, VERDICT_TOO_EXPENSIVE, VERDICT_UNKNOWN = "ok", "too_expensive", "unknown"
VERDICT_TOO_SMALL = "too_small"


def _passes(price_verdict: str | None, pack_verdict: str | None) -> bool:
    return price_verdict in (None, VERDICT_OK) and pack_verdict in (None, VERDICT_OK)


@dataclass(frozen=True, slots=True)
class StoreStatus:
    """Stand pro Laden für die Angebote-Seite: letzter Abruf und was davon noch gilt."""

    store_id: int
    store_name: str
    last_fetched_at: datetime | None
    last_status: SyncStatus | None
    last_error: str | None
    market_label: str | None
    current_count: int


def latest_snapshot(session: Session, store_id: int) -> m.OfferSnapshot | None:
    """Nur OK-Snapshots - ein leerer Abruf verdraengt den letzten guten nicht."""
    return session.scalar(
        select(m.OfferSnapshot)
        .where(
            m.OfferSnapshot.store_id == store_id,
            m.OfferSnapshot.status == SyncStatus.OK.value,
        )
        .order_by(m.OfferSnapshot.fetched_at.desc(), m.OfferSnapshot.id.desc())
        .limit(1)
    )


def current_offers(
    session: Session, *, today: date | None = None, confirmed_only: bool = False
) -> list[OfferView]:
    """Die heute gültigen Angebote aller Läden aus deren letztem guten Abruf.

    `confirmed_only`: für alles, was auf Liste und Planer wirkt - dann trägt ein Angebot
    nur einen Artikel, wenn die Zuordnung bestätigt ist *und* es den Richtpreis hält.
    """
    today = today or date.today()
    out: list[OfferView] = []
    articles = {a.id: a for a in session.scalars(select(m.Article))}
    for store in session.scalars(select(m.Store).order_by(m.Store.name)):
        snapshot = latest_snapshot(session, store.id)
        if snapshot is None:
            continue
        matches = {
            row.normalized_offer_name: row
            for row in session.scalars(
                select(m.OfferMatch).where(m.OfferMatch.store_id == store.id)
            )
        }
        for offer in snapshot.offers:
            if offer.valid_to is not None and offer.valid_to < today:
                continue
            match = matches.get(normalize(offer.raw_name))
            confirmed = bool(match and match.confirmed)
            article = articles.get(match.article_id) if match and match.article_id else None
            price = _unit_price_of(offer)
            compared = _compared(price, article)
            verdict = _verdict(compared, article)
            amount = _amount(offer, price, article)
            pack_verdict = _pack_verdict(amount, article)
            if confirmed_only and not (confirmed and _passes(verdict, pack_verdict)):
                article = None
                verdict = pack_verdict = amount = None
            regular, diff, percent = _against_normal(compared, article)
            savings = (
                offer.old_price - offer.price
                if offer.old_price is not None and offer.price is not None
                else None
            )
            out.append(
                OfferView(
                    offer_id=offer.id,
                    store_id=store.id,
                    store_name=store.name,
                    raw_name=offer.raw_name,
                    brand=offer.brand,
                    pack=offer.pack,
                    category=offer.category,
                    price=offer.price,
                    old_price=offer.old_price,
                    base_price=offer.base_price,
                    savings=savings,
                    valid_from=offer.valid_from.isoformat() if offer.valid_from else None,
                    valid_to=offer.valid_to.isoformat() if offer.valid_to else None,
                    article_id=article.id if article else None,
                    article_name=article.canonical_name if article else None,
                    match_confirmed=confirmed,
                    description=offer.description,
                    image_url=offer.image_url,
                    source_url=offer.source_url,
                    market_label=snapshot.market_label,
                    market_url=snapshot.market_url,
                    source_detail=snapshot.source_detail,
                    fetched_at=snapshot.fetched_at,
                    unit_price=price.value if price else None,
                    unit_price_unit=price.unit if price else None,
                    target_price=article.max_unit_price if article else None,
                    price_verdict=verdict,
                    regular_unit_price=regular,
                    normal_diff=diff,
                    normal_diff_percent=percent,
                    article_price_unit=COMPARE_UNIT.get(Unit(article.unit)) if article else None,
                    compared_price=compared.value if compared and article else None,
                    compared_via_piece=bool(compared and article and compared.via_piece),
                    piece_size=article.piece_size if article else None,
                    offer_amount=amount,
                    min_offer_amount=trim(article.min_offer_amount) if article else None,
                    pack_verdict=pack_verdict,
                )
            )
    return out


def _compared(price: UnitPrice | None, article: m.Article | None) -> Compared | None:
    """Der Angebotspreis in der Einheit des Artikels, notfalls übers Stückgewicht."""
    if article is None:
        return None
    return compare(price, Unit(article.unit), article.piece_size)


def regular_unit_price(article: m.Article) -> Decimal | None:
    """Der Normalpreis des Artikels als Grundpreis - auch wenn er pro Stück eingegeben ist."""
    return pack_unit_price(
        article.regular_pack_amount,
        article.regular_pack_price,
        Unit(article.unit),
        in_pieces=article.regular_pack_unit == Unit.STUECK.value,
        piece_size=article.piece_size,
    )


def _against_normal(
    compared: Compared | None, article: m.Article | None
) -> tuple[Decimal | None, Decimal | None, int | None]:
    """(Normalpreis, Abstand, Abstand in %) - in der Einheit des Artikels."""
    if article is None:
        return None, None, None
    regular = regular_unit_price(article)
    if regular is None or compared is None:
        return regular, None, None
    diff = compared.value - regular
    return regular, diff, round(diff / regular * 100)


def _unit_price_of(offer: m.Offer) -> UnitPrice | None:
    """Beim Speichern gerechnet; ältere Angebote (vor dem Richtpreis) erst hier."""
    if offer.unit_price is not None and offer.unit_price_unit:
        return UnitPrice(offer.unit_price, offer.unit_price_unit)
    return unit_price(offer.price, offer.base_price, offer.pack, offer.description)


def _amount(offer: m.Offer, price: UnitPrice | None, article: m.Article | None) -> Decimal | None:
    """Wie groß das Angebot ist, in der Einheit des Artikels - Stück über das Stückgewicht."""
    if article is None:
        return None
    quantity = offer_quantity(offer.price, price, offer.pack, offer.description)
    amount = in_article_unit(quantity, Unit(article.unit), article.piece_size)
    return trim(amount)


def _pack_verdict(amount: Decimal | None, article: m.Article | None) -> str | None:
    """Mindestpackung: "Heidelbeeren ab 400 g" - unbekannte Größe zählt dann auch nicht."""
    if article is None or article.min_offer_amount is None:
        return None
    if amount is None:
        return VERDICT_UNKNOWN
    return VERDICT_OK if amount >= article.min_offer_amount else VERDICT_TOO_SMALL


def _verdict(compared: Compared | None, article: m.Article | None) -> str | None:
    if article is None or article.max_unit_price is None:
        return None
    if compared is None:
        return VERDICT_UNKNOWN
    return VERDICT_OK if compared.value <= article.max_unit_price else VERDICT_TOO_EXPENSIVE


def unmatched(session: Session) -> list[OfferView]:
    return [view for view in current_offers(session) if view.article_id is None]


def store_status(session: Session, *, today: date | None = None) -> list[StoreStatus]:
    current: dict[int, int] = {}
    for view in current_offers(session, today=today):
        current[view.store_id] = current.get(view.store_id, 0) + 1
    out = []
    for store in offer_stores(session):
        last = session.scalar(
            select(m.OfferSnapshot)
            .where(m.OfferSnapshot.store_id == store.id)
            .order_by(m.OfferSnapshot.fetched_at.desc(), m.OfferSnapshot.id.desc())
            .limit(1)
        )
        out.append(
            StoreStatus(
                store_id=store.id,
                store_name=store.name,
                last_fetched_at=last.fetched_at if last else None,
                last_status=SyncStatus(last.status) if last else None,
                last_error=last.error if last else None,
                market_label=last.market_label if last else None,
                current_count=current.get(store.id, 0),
            )
        )
    return out


def savings_by_dish(session: Session, week: m.Week) -> dict[int, Decimal]:
    """Angebots-Bonus pro Gericht: Summe der Ersparnis seiner Zutaten.

    Nur bestätigte Zuordnungen, nur mit "statt"-Preis. Den liefern die Quellen selten -
    eine bessere Grundlage für den Bonus kommt mit Stufe 3.
    """
    by_article = _savings_by_article(session)
    if not by_article:
        return {}
    rows = session.execute(select(m.Ingredient.dish_id, m.Ingredient.article_id)).all()
    out: dict[int, Decimal] = {}
    for dish_id, article_id in rows:
        saving = by_article.get(article_id)
        if saving:
            out[dish_id] = out.get(dish_id, Decimal(0)) + saving
    return out


def _savings_by_article(session: Session) -> dict[int, Decimal]:
    out: dict[int, Decimal] = {}
    for view in current_offers(session, confirmed_only=True):
        if view.article_id is None or view.savings is None or view.savings <= 0:
            continue
        current = out.get(view.article_id)
        if current is None or view.savings > current:
            out[view.article_id] = view.savings
    return out


def offer_hints(session: Session, article_ids: list[int]) -> dict[int, str]:
    """Kurztext für die Einkaufsliste: "Rewe 3,99 € (statt 5,49 €), bis Sa"."""
    if not article_ids:
        return {}
    wanted = set(article_ids)
    out: dict[int, str] = {}
    for view in current_offers(session, confirmed_only=True):
        if view.article_id not in wanted or view.price is None:
            continue
        parts = [f"{view.store_name} {view.price:.2f} €".replace(".", ",")]
        if view.old_price:
            parts.append(f"statt {view.old_price:.2f} €".replace(".", ","))
        if view.valid_to:
            parts.append(f"bis {view.valid_to}")
        out[view.article_id] = ", ".join(parts)
    return out


def watchlist_suggestions(session: Session) -> list[OfferView]:
    """Stammartikel-Watchlist: "Kaffee bei Aldi 4,99 €, mit auf die Liste?" (Plan §5)."""
    watched = set(
        session.scalars(select(m.Article.id).where(m.Article.is_watchlist.is_(True)))
    )
    return [
        view
        for view in current_offers(session, confirmed_only=True)
        if view.article_id in watched
    ]


def ingest(session: Session, data: OfferSnapshotData) -> m.OfferSnapshot:
    """Schreibt einen Snapshot inklusive `raw_payload` (Reprocessing ohne neuen Abruf)."""
    snapshot = m.OfferSnapshot(
        store_id=data.store_id,
        source=data.source,
        fetched_at=data.fetched_at,
        status=(SyncStatus.OK if data.usable else SyncStatus.FAILED).value,
        offer_count=len(data.offers),
        raw_payload=data.raw_payload,
        market_label=data.market_label,
        market_url=data.market_url[:500] if data.market_url else None,
        source_detail=data.source_detail[:60] if data.source_detail else None,
        error=data.error if not data.usable else None,
        valid_from=min((o.valid_from for o in data.offers if o.valid_from), default=None),
        valid_to=max((o.valid_to for o in data.offers if o.valid_to), default=None),
    )
    session.add(snapshot)
    session.flush()
    for raw in data.offers:
        price = unit_price(raw.price, raw.base_price, raw.pack, raw.description)
        session.add(
            m.Offer(
                snapshot_id=snapshot.id,
                raw_name=raw.raw_name[:200],
                brand=raw.brand[:80] if raw.brand else None,
                price=raw.price,
                old_price=raw.old_price,
                base_price=raw.base_price[:60] if raw.base_price else None,
                pack=raw.pack[:60] if raw.pack else None,
                category=raw.category[:60] if raw.category else None,
                description=raw.description[:300] if raw.description else None,
                image_url=raw.image_url if raw.image_url and len(raw.image_url) <= 500 else None,
                source_url=(
                    raw.source_url if raw.source_url and len(raw.source_url) <= 500 else None
                ),
                unit_price=price.value if price else None,
                unit_price_unit=price.unit if price else None,
                valid_from=raw.valid_from,
                valid_to=raw.valid_to,
            )
        )
    session.flush()
    session.refresh(snapshot)
    if data.usable:
        match_snapshot(session, snapshot)
    _prune(session, data.store_id)
    return snapshot


def _prune(session: Session, store_id: int) -> None:
    """Ältere Abrufe weg - der Rohdaten-Anteil wächst sonst um ~1 MB pro Woche.

    Der letzte gute bleibt immer, auch wenn danach mehr als KEEP_SNAPSHOTS fehlschlugen.
    """
    snapshots = list(
        session.scalars(
            select(m.OfferSnapshot)
            .where(m.OfferSnapshot.store_id == store_id)
            .order_by(m.OfferSnapshot.fetched_at.desc(), m.OfferSnapshot.id.desc())
        )
    )
    good = latest_snapshot(session, store_id)
    for old in snapshots[KEEP_SNAPSHOTS:]:
        if old is not good:
            session.delete(old)
    session.flush()


def fetch_all(session: Session, source: OfferSource) -> list[m.OfferSnapshot]:
    """Abruf aller Läden mit Angeboten - Cron (Mo/Do früh) und der Knopf.

    Erst alle Quellen abfragen, dann in einem Rutsch schreiben: ein Abruf dauert
    Sekunden pro Laden, und so lange soll niemand auf die Schreibsperre warten.
    """
    if not _FETCH_LOCK.acquire(blocking=False):
        raise ValidationError("Angebote werden gerade schon abgerufen")
    try:
        started = datetime.now(UTC)
        stores = offer_stores(session)
        if not stores:
            LOG.info("Kein Laden mit Angeboten eingerichtet - nichts abzurufen")
            return []
        results = [(store, source.fetch(store_ref(store))) for store in stores]

        run = m.SyncRun(
            kind=SyncKind.OFFER_FETCH.value, status=SyncStatus.OK.value, started_at=started
        )
        session.add(run)
        snapshots: list[m.OfferSnapshot] = []
        failures: list[str] = []
        for store, data in results:
            snapshots.append(ingest(session, data))
            if not data.usable:
                failures.append(f"{store.name}: {data.error or 'keine Angebote'}")

        run.finished_at = datetime.now(UTC)
        if failures and len(failures) == len(snapshots):
            run.status = SyncStatus.FAILED.value
        elif failures:
            run.status = SyncStatus.PARTIAL.value
        run.error = "; ".join(failures) or None
        run.summary = {
            "stores": len(snapshots),
            "offers": sum(s.offer_count for s in snapshots),
            "source": source.name,
        }
        session.flush()
        LOG.info("Angebots-Abruf: %s Läden, %s Fehler", len(snapshots), len(failures))
        return snapshots
    finally:
        _FETCH_LOCK.release()
