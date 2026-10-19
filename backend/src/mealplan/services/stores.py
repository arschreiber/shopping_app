"""Läden (Phase 2): wo eingekauft wird, und ob dort Angebote abgerufen werden.

Die Läden stehen in der Datenbank, nicht in `config.local.toml`: das `data/`-Verzeichnis
gehört im Container root, eine Datei dort zu bearbeiten hieße `sudo`. Ins Repo kommt
die PLZ so oder so nicht.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.enums import Chain
from ..ports import StoreRef
from .articles import ValidationError

OFFER_SOURCE = "korbunio"
_POSTAL = re.compile(r"\d{5}")
_MARKET = re.compile(r"\d{1,30}")


@dataclass(frozen=True, slots=True)
class StoreInput:
    name: str
    chain: Chain
    postal_code: str | None = None
    market_id: str | None = None
    offers_enabled: bool = False
    is_primary: bool = False


def list_stores(session: Session) -> list[m.Store]:
    return list(
        session.scalars(select(m.Store).order_by(m.Store.is_primary.desc(), m.Store.name))
    )


def get_store(session: Session, store_id: int) -> m.Store:
    store = session.get(m.Store, store_id)
    if store is None:
        raise ValidationError(f"Laden {store_id} existiert nicht")
    return store


def create_store(session: Session, data: StoreInput) -> m.Store:
    store = m.Store(name="", chain=data.chain.value)
    session.add(store)
    _apply(session, store, data)
    session.flush()
    return store


def update_store(session: Session, store_id: int, **changes) -> m.Store:
    store = get_store(session, store_id)
    current = StoreInput(
        name=store.name,
        chain=Chain(store.chain),
        postal_code=store.postal_code,
        market_id=store.market_id,
        offers_enabled=store.offer_source is not None,
        is_primary=store.is_primary,
    )
    given = {key: value for key, value in changes.items() if value is not None}
    merged = StoreInput(**{**_as_dict(current), **given})
    _apply(session, store, merged)
    session.flush()
    return store


def delete_store(session: Session, store_id: int) -> None:
    """Mit ihm gehen seine Abrufe und Zuordnungen (FK CASCADE); Wochen behalten ihre
    Einträge, nur ohne Laden (SET NULL)."""
    session.delete(get_store(session, store_id))
    session.flush()


def store_ref(store: m.Store) -> StoreRef:
    return StoreRef(
        id=store.id,
        chain=store.chain,
        postal_code=store.postal_code or "",
        market_id=store.market_id,
    )


def offer_stores(session: Session) -> list[m.Store]:
    """Läden, für die Angebote abgerufen werden."""
    return [s for s in list_stores(session) if s.offer_source and s.postal_code]


def _apply(session: Session, store: m.Store, data: StoreInput) -> None:
    name = data.name.strip()
    if not name:
        raise ValidationError("Name fehlt")
    taken = session.scalar(
        select(m.Store.id).where(func.lower(m.Store.name) == name.lower(), m.Store.id != store.id)
    )
    if taken is not None:
        raise ValidationError(f"'{name}' gibt es schon")

    postal = (data.postal_code or "").strip() or None
    if postal is not None and not _POSTAL.fullmatch(postal):
        raise ValidationError("Die PLZ hat fünf Ziffern")
    market = (data.market_id or "").strip() or None
    if market is not None and not _MARKET.fullmatch(market):
        raise ValidationError("Die Markt-ID besteht nur aus Ziffern")
    if data.offers_enabled and postal is None:
        raise ValidationError(f"{name}: für Angebote braucht der Laden eine PLZ")

    store.name = name
    store.chain = data.chain.value
    store.postal_code = postal
    store.market_id = market
    store.offer_source = OFFER_SOURCE if data.offers_enabled else None
    if data.is_primary:
        # Es gibt genau einen Hauptladen - wer einen neuen wählt, löst den alten ab.
        for other in session.scalars(select(m.Store).where(m.Store.is_primary.is_(True))):
            if other is not store:
                other.is_primary = False
    store.is_primary = data.is_primary


def _as_dict(data: StoreInput) -> dict:
    return {field: getattr(data, field) for field in StoreInput.__dataclass_fields__}
