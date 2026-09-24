"""Angebots-Use-Cases (Phase 2).

Im MVP liefern diese Funktionen leere Ergebnisse - die Tabellen existieren, die Quelle
ist noch nicht konfiguriert. Wichtig ist die Regel aus ARCHITECTURE.md §5: der letzte
*gute* Snapshot bleibt der, den die App liest. Ein fehlgeschlagener Abruf leert die
Angebotsansicht nie.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.enums import SyncKind, SyncStatus
from ..ports import OfferSnapshotData, OfferSource
from .matching import match_snapshot

LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OfferView:
    offer_id: int
    store_name: str
    raw_name: str
    brand: str | None
    price: Decimal | None
    old_price: Decimal | None
    savings: Decimal | None
    valid_to: str | None
    article_id: int | None
    article_name: str | None


def latest_snapshot(session: Session, store_id: int) -> m.OfferSnapshot | None:
    """Nur OK-Snapshots - ein leerer Abruf verdraengt den letzten guten nicht."""
    return session.scalar(
        select(m.OfferSnapshot)
        .where(
            m.OfferSnapshot.store_id == store_id,
            m.OfferSnapshot.status == SyncStatus.OK.value,
        )
        .order_by(m.OfferSnapshot.fetched_at.desc())
        .limit(1)
    )


def store_ids(session: Session) -> list[int]:
    return list(session.scalars(select(m.Store.id)))


def current_offers(session: Session) -> list[OfferView]:
    out: list[OfferView] = []
    articles = {a.id: a.canonical_name for a in session.scalars(select(m.Article))}
    for store in session.scalars(select(m.Store)):
        snapshot = latest_snapshot(session, store.id)
        if snapshot is None:
            continue
        matches = {
            row.normalized_offer_name: row
            for row in session.scalars(
                select(m.OfferMatch).where(m.OfferMatch.store_id == store.id)
            )
        }
        from ..matching.normalize import normalize

        for offer in snapshot.offers:
            match = matches.get(normalize(offer.raw_name))
            article_id = match.article_id if match else None
            savings = (
                offer.old_price - offer.price
                if offer.old_price is not None and offer.price is not None
                else None
            )
            out.append(
                OfferView(
                    offer_id=offer.id,
                    store_name=store.name,
                    raw_name=offer.raw_name,
                    brand=offer.brand,
                    price=offer.price,
                    old_price=offer.old_price,
                    savings=savings,
                    valid_to=offer.valid_to.isoformat() if offer.valid_to else None,
                    article_id=article_id,
                    article_name=articles.get(article_id) if article_id else None,
                )
            )
    return out


def unmatched(session: Session) -> list[OfferView]:
    return [view for view in current_offers(session) if view.article_id is None]


def savings_by_dish(session: Session, week: m.Week) -> dict[int, Decimal]:
    """Angebots-Bonus pro Gericht: Summe der Ersparnis seiner Zutaten.

    Phase 2. Ohne Snapshots ist das Ergebnis leer und der Score-Beitrag damit 0 -
    genau so soll der MVP laufen.
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
    for view in current_offers(session):
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
    for view in current_offers(session):
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
    return [view for view in current_offers(session) if view.article_id in watched]


def store_offer_queries(session: Session) -> list[str]:
    """Suchbegriffe für den Abruf: Stammartikel + alles, was in Gerichten vorkommt."""
    rows = session.scalars(
        select(m.Article.canonical_name).where(
            m.Article.is_watchlist.is_(True) | m.Article.is_staple.is_(False)
        )
    ).all()
    return sorted(set(rows))


def ingest(session: Session, data: OfferSnapshotData) -> m.OfferSnapshot:
    """Schreibt einen Snapshot inklusive `raw_payload` (Reprocessing ohne neuen Abruf)."""
    snapshot = m.OfferSnapshot(
        store_id=data.store_id,
        source=data.source,
        fetched_at=data.fetched_at,
        status=(SyncStatus.OK if data.usable else SyncStatus.FAILED).value,
        offer_count=len(data.offers),
        raw_payload=data.raw_payload,
        valid_from=min((o.valid_from for o in data.offers if o.valid_from), default=None),
        valid_to=max((o.valid_to for o in data.offers if o.valid_to), default=None),
    )
    session.add(snapshot)
    session.flush()
    for raw in data.offers:
        session.add(
            m.Offer(
                snapshot_id=snapshot.id,
                raw_name=raw.raw_name,
                brand=raw.brand,
                price=raw.price,
                old_price=raw.old_price,
                base_price=raw.base_price,
                valid_from=raw.valid_from,
                valid_to=raw.valid_to,
            )
        )
    session.flush()
    session.refresh(snapshot)
    if data.usable:
        match_snapshot(session, snapshot)
    return snapshot


def fetch_all(session: Session, source: OfferSource) -> list[m.OfferSnapshot]:
    """Cron-Einstieg (Mo/Do frueh). Jeder Laden einzeln, Fehler pro Laden protokolliert."""
    run = m.SyncRun(kind=SyncKind.OFFER_FETCH.value, status=SyncStatus.OK.value)
    session.add(run)
    session.flush()

    queries = store_offer_queries(session)
    snapshots: list[m.OfferSnapshot] = []
    failures: list[str] = []
    for store in session.scalars(select(m.Store)):
        data = source.fetch(store.id, store.market_id, queries)
        snapshot = ingest(session, data)
        snapshots.append(snapshot)
        if not data.usable:
            failures.append(f"{store.name}: {data.error or 'keine Treffer'}")

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
    return snapshots
