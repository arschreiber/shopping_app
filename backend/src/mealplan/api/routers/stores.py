"""Läden (Phase 2): wo eingekauft wird und ob dort Angebote abgerufen werden."""

from __future__ import annotations

from fastapi import APIRouter, status

from ...db import models as m
from ...services import stores as service
from ..deps import SessionDep
from ..schemas.common import StoreIn, StoreOut, StorePatch

router = APIRouter(prefix="/api/stores", tags=["stores"])


def store_out(store: m.Store) -> StoreOut:
    return StoreOut(
        id=store.id,
        name=store.name,
        chain=store.chain,
        postal_code=store.postal_code,
        market_id=store.market_id,
        offers_enabled=store.offer_source is not None,
        is_primary=store.is_primary,
    )


@router.get("", response_model=list[StoreOut])
def list_stores(session: SessionDep) -> list[StoreOut]:
    return [store_out(store) for store in service.list_stores(session)]


@router.post("", response_model=StoreOut, status_code=status.HTTP_201_CREATED)
def create_store(session: SessionDep, payload: StoreIn) -> StoreOut:
    data = service.StoreInput(**payload.model_dump())
    return store_out(service.create_store(session, data))


@router.patch("/{store_id}", response_model=StoreOut)
def update_store(session: SessionDep, store_id: int, payload: StorePatch) -> StoreOut:
    changes = payload.model_dump(exclude_unset=True)
    return store_out(service.update_store(session, store_id, **changes))


@router.delete("/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_store(session: SessionDep, store_id: int) -> None:
    service.delete_store(session, store_id)
