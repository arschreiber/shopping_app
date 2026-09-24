"""Einkaufslisten-Router: aggregieren, abhaken, nach Bring! pushen."""

from __future__ import annotations

from fastapi import APIRouter

from ...domain.enums import ListStatus
from ...domain.units import trim
from ...services import bring_sync as sync_service
from ...services import shopping_list as service
from ..deps import SessionDep, SyncDep
from ..schemas.common import (
    AddItemIn,
    HaveAlreadyIn,
    PushOut,
    ShoppingItemOut,
    ShoppingListOut,
)

router = APIRouter(prefix="/api/weeks", tags=["shopping"])


def _out(session, iso: str, shopping) -> ShoppingListOut:
    lines = service.to_lines(session, shopping)
    return ShoppingListOut(
        iso=iso,
        status=ListStatus(shopping.status),
        sent_at=shopping.sent_at,
        items=[
            ShoppingItemOut(
                article_id=line.article_id,
                article_name=line.article_name,
                quantity=trim(line.quantity),
                unit=line.unit,
                spec_text=line.spec_text,
                source=line.source,
                have_already=line.have_already,
                is_staple=line.is_staple,
                from_dish_ids=list(line.from_dish_ids),
                bring_name=line.bring_name,
                offer_hint=line.offer_hint,
            )
            for line in lines
        ],
        open_count=sum(1 for line in lines if not line.have_already),
        text_export=service.as_text(session, shopping),
    )


@router.get("/{iso}/shopping-list", response_model=ShoppingListOut)
def get_shopping_list(session: SessionDep, iso: str, rebuild: bool = True) -> ShoppingListOut:
    shopping = service.get_list(session, iso, rebuild_first=rebuild)
    return _out(session, iso, shopping)


@router.patch("/{iso}/shopping-list/have-already", response_model=ShoppingListOut)
def set_have_already(session: SessionDep, iso: str, payload: HaveAlreadyIn) -> ShoppingListOut:
    shopping = service.set_have_already(
        session, iso, article_id=payload.article_id, have_already=payload.have_already
    )
    session.flush()
    return _out(session, iso, shopping)


@router.post("/{iso}/shopping-list/items", response_model=ShoppingListOut)
def add_item(session: SessionDep, iso: str, payload: AddItemIn) -> ShoppingListOut:
    shopping = service.add_manual(
        session,
        iso,
        article_id=payload.article_id,
        quantity=payload.quantity,
        source=payload.source,
    )
    return _out(session, iso, shopping)


@router.delete("/{iso}/shopping-list/items/{article_id}", response_model=ShoppingListOut)
def remove_item(session: SessionDep, iso: str, article_id: int) -> ShoppingListOut:
    shopping = service.remove_item(session, iso, article_id=article_id)
    return _out(session, iso, shopping)


@router.post("/{iso}/shopping-list/push", response_model=PushOut)
def push(session: SessionDep, iso: str, sync: SyncDep) -> PushOut:
    """Diff-Push. Schlaegt er fehl, kommt der Text-Fallback im selben Response mit."""
    service.get_list(session, iso, rebuild_first=True)
    outcome = sync_service.push(session, iso, sync)
    result = outcome.result
    return PushOut(
        ok=result.ok,
        adapter=sync.name,
        items_sent=outcome.items_sent,
        created=[item.name for item in result.created],
        updated=[item.name for item in result.updated],
        removed=list(result.removed),
        error=result.error,
        text_fallback=result.text_fallback,
        run_id=outcome.run_id,
    )
