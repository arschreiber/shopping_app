"""Betriebs-Router: Health, Sync-Historie, Einstellungen, Angebote."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from ...db import models as m
from ...domain.enums import SyncKind
from ...services import bring_sync as sync_service
from ...services import matching as matching_service
from ...services import offers as offers_service
from ...services import settings_store
from ...services import stores as stores_service
from ...services import weeks as weeks_service
from ...services.articles import ValidationError
from ..deps import CatalogDep, OfferSourceDep, SessionDep, SyncDep
from ..schemas.common import (
    HealthOut,
    OfferMatchIn,
    OfferOut,
    SettingsIn,
    SettingsOut,
    StandardSlotOut,
    StandardWeekIn,
    StoreStatusOut,
    SyncRunOut,
)

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthOut)
def health(session: SessionDep, sync: SyncDep, catalog: CatalogDep) -> HealthOut:
    """Ein Integrationsbruch soll an der Oberfläche sichtbar sein (ARCHITECTURE.md §8)."""
    last_push = sync_service.last_run(session, SyncKind.BRING_PUSH)
    last_fetch = sync_service.last_run(session, SyncKind.OFFER_FETCH)
    return HealthOut(
        db="ok",
        dishes=session.scalar(select(func.count()).select_from(m.Dish)) or 0,
        articles=session.scalar(select(func.count()).select_from(m.Article)) or 0,
        catalog_cached=getattr(catalog, "is_cached", lambda: False)(),
        sync_adapter=sync.name,
        last_bring_push=last_push.started_at if last_push else None,
        last_offer_fetch=last_fetch.started_at if last_fetch else None,
    )


@router.get("/sync-runs", response_model=list[SyncRunOut])
def sync_runs(session: SessionDep, limit: int = 20) -> list[SyncRunOut]:
    runs = sync_service.recent_runs(session, limit=limit)
    return [SyncRunOut.model_validate(run) for run in runs]


@router.get("/settings", response_model=SettingsOut)
def get_settings(session: SessionDep) -> SettingsOut:
    return SettingsOut.model_validate(settings_store.all_settings(session))


@router.put("/settings", response_model=SettingsOut)
def put_settings(session: SessionDep, payload: SettingsIn) -> SettingsOut:
    """Planer-Gewichte kommen aus der DB - Spike 4 kalibriert ohne Deploy."""
    if payload.planner_weights is not None:
        settings_store.put(session, settings_store.KEY_WEIGHTS, payload.planner_weights)
    if payload.household is not None:
        settings_store.put(session, settings_store.KEY_HOUSEHOLD, payload.household)
    if payload.shopping is not None:
        settings_store.put(session, settings_store.KEY_SHOPPING, payload.shopping)
    session.flush()
    return SettingsOut.model_validate(settings_store.all_settings(session))


@router.get("/settings/standard-week", response_model=list[StandardSlotOut])
def get_standard_week(session: SessionDep) -> list[StandardSlotOut]:
    return [StandardSlotOut.model_validate(slot) for slot in weeks_service.standard_week(session)]


@router.put("/settings/standard-week", response_model=list[StandardSlotOut])
def put_standard_week(session: SessionDep, payload: StandardWeekIn) -> list[StandardSlotOut]:
    """Das Raster, mit dem neue Wochen anfangen. Fehlende Mahlzeiten: zwei zu Hause."""
    saved = weeks_service.save_standard_week(
        session,
        [
            weeks_service.StandardSlot(
                day=row.day,
                meal=row.meal,
                eaters_home=row.eaters_home,
                packed_portions=row.packed_portions,
                packed_fresh=row.packed_fresh,
                time_budget=row.time_budget,
            )
            for row in payload.slots
        ],
    )
    return [StandardSlotOut.model_validate(slot) for slot in saved]


@router.get("/offers", response_model=list[OfferOut])
def offers(session: SessionDep) -> list[OfferOut]:
    return [OfferOut.model_validate(view) for view in offers_service.current_offers(session)]


@router.get("/offers/status", response_model=list[StoreStatusOut])
def offer_status(session: SessionDep) -> list[StoreStatusOut]:
    """Pro Laden: letzter Abruf, welcher Markt, wie viele Angebote noch gelten."""
    return [StoreStatusOut.model_validate(row) for row in offers_service.store_status(session)]


@router.post("/offers/fetch", response_model=list[StoreStatusOut])
def fetch_offers(session: SessionDep, source: OfferSourceDep) -> list[StoreStatusOut]:
    """Der Knopf "Angebote abrufen" - derselbe Ablauf wie der Abruf Mo/Do früh.

    Synchron: ein Abruf dauert ein paar Sekunden pro Laden (beim ersten Mal für eine PLZ
    bis zu 20), und das Ergebnis ist genau das, worauf man wartet.
    """
    if source is None:
        raise ValidationError("Keine Angebotsquelle konfiguriert (MEALPLAN_KORBUNIO_URL)")
    if not stores_service.offer_stores(session):
        raise ValidationError(
            "Noch kein Laden mit Angeboten - unter Einstellungen → Läden einen anlegen"
        )
    offers_service.fetch_all(session, source)
    return [StoreStatusOut.model_validate(row) for row in offers_service.store_status(session)]


@router.get("/offers/unmatched", response_model=list[OfferOut])
def unmatched(session: SessionDep) -> list[OfferOut]:
    """"Unzugeordnet"-Ansicht mit Ein-Klick-Zuordnung (general_plan.md §7)."""
    return [OfferOut.model_validate(view) for view in offers_service.unmatched(session)]


@router.get("/offers/watchlist", response_model=list[OfferOut])
def watchlist(session: SessionDep) -> list[OfferOut]:
    return [
        OfferOut.model_validate(view)
        for view in offers_service.watchlist_suggestions(session)
    ]


@router.post("/offers/match", status_code=204)
def match_offer(session: SessionDep, payload: OfferMatchIn) -> None:
    matching_service.confirm(
        session,
        offer_name=payload.offer_name,
        store_id=payload.store_id,
        article_id=payload.article_id,
    )
