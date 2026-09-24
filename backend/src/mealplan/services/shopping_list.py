"""Einkaufsliste: aus dem Plan aggregieren, abhaken, Stammartikel ergaenzen."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import mappers
from ..db import models as m
from ..domain.enums import ItemSource, ListStatus, Unit
from ..domain.shopping import build_shopping_list
from ..domain.units import Quantity, format_quantity
from .articles import ValidationError, staple_ids
from .weeks import get_or_create_week


@dataclass(frozen=True, slots=True)
class ListLine:
    article_id: int
    article_name: str
    quantity: Decimal | None
    unit: Unit
    spec_text: str
    source: ItemSource
    have_already: bool
    is_staple: bool
    from_dish_ids: tuple[int, ...]
    bring_name: str | None
    offer_hint: str | None = None


def rebuild(session: Session, iso: str) -> m.ShoppingList:
    """Erzeugt/aktualisiert die Liste aus dem Plan.

    Manuelle Zeilen (`MANUAL`, `WATCHLIST`) und `have_already`-Haken bleiben erhalten -
    die Liste wird während des Montags-Rituals mehrfach neu gebaut.
    """
    week = get_or_create_week(session, iso)
    shopping = _get_or_create(session, week)

    snapshot = mappers.build_snapshot(
        session, week, weights=_weights(session), leftover_shelf_life_days=_shelf_life(session)
    )
    plan = mappers.plan_from_week(week)

    manual = {
        item.article_id: item
        for item in shopping.items
        if item.source != ItemSource.RECIPE.value
    }
    checked = {item.article_id for item in shopping.items if item.have_already}
    pulled_in = {
        item.article_id
        for item in shopping.items
        if item.source == ItemSource.RECIPE.value and item.article.is_staple
    }

    draft = build_shopping_list(
        plan,
        snapshot,
        ingredients=mappers.ingredients_by_dish(session),
        article_units=mappers.article_units(session),
        staples=staple_ids(session),
        include_staples=frozenset(pulled_in),
    )

    # "Gesendet" bleibt gesendet, solange sich an den Rezeptzeilen nichts ändert. Sonst
    # fällt der Status bei jedem Laden der Seite auf DRAFT zurück und die Anzeige
    # "an Bring! gesendet" wäre nie zu sehen.
    previous = {
        (item.article_id, item.quantity, item.unit)
        for item in shopping.items
        if item.source == ItemSource.RECIPE.value
    }
    current = {(line.article_id, line.quantity, line.unit.value) for line in draft.lines}
    if previous != current and shopping.status == ListStatus.SENT.value:
        shopping.status = ListStatus.DRAFT.value

    for item in list(shopping.items):
        if item.source == ItemSource.RECIPE.value:
            shopping.items.remove(item)
    session.flush()

    for line in draft.lines:
        session.add(
            m.ShoppingListItem(
                shopping_list_id=shopping.id,
                article_id=line.article_id,
                quantity=line.quantity,
                unit=line.unit.value,
                source=ItemSource.RECIPE.value,
                have_already=line.article_id in checked,
                spec_text=format_quantity(Quantity(line.quantity, line.unit)),
                from_dish_ids=list(line.from_dish_ids),
            )
        )
    for article_id, item in manual.items():
        if article_id not in {line.article_id for line in draft.lines}:
            item.have_already = article_id in checked
    session.flush()
    session.refresh(shopping)
    return shopping


def _get_or_create(session: Session, week: m.Week) -> m.ShoppingList:
    existing = session.scalar(
        select(m.ShoppingList).where(m.ShoppingList.week_id == week.id)
    )
    if existing is not None:
        return existing
    shopping = m.ShoppingList(week_id=week.id, status=ListStatus.DRAFT.value)
    session.add(shopping)
    session.flush()
    return shopping


def _weights(session: Session):
    from . import settings_store

    return settings_store.weights(session)


def _shelf_life(session: Session) -> int:
    from . import settings_store

    return settings_store.leftover_shelf_life(session)


def get_list(session: Session, iso: str, *, rebuild_first: bool = True) -> m.ShoppingList:
    if rebuild_first:
        return rebuild(session, iso)
    week = get_or_create_week(session, iso)
    return _get_or_create(session, week)


def to_lines(session: Session, shopping: m.ShoppingList) -> list[ListLine]:
    from .offers import offer_hints

    hints = offer_hints(session, [item.article_id for item in shopping.items])
    out = [
        ListLine(
            article_id=item.article_id,
            article_name=item.article.canonical_name,
            quantity=item.quantity,
            unit=Unit(item.unit),
            spec_text=item.spec_text or format_quantity(Quantity(item.quantity, Unit(item.unit))),
            source=ItemSource(item.source),
            have_already=item.have_already,
            is_staple=item.article.is_staple,
            from_dish_ids=tuple(item.from_dish_ids or []),
            bring_name=item.article.bring_catalog_name,
            offer_hint=hints.get(item.article_id),
        )
        for item in shopping.items
    ]
    out.sort(key=lambda line: (line.have_already, line.article_name.lower()))
    return out


def set_have_already(
    session: Session, iso: str, *, article_id: int, have_already: bool
) -> m.ShoppingList:
    shopping = get_list(session, iso, rebuild_first=False)
    for item in shopping.items:
        if item.article_id == article_id:
            item.have_already = have_already
            return shopping
    raise ValidationError(f"Artikel {article_id} steht nicht auf der Liste")


def add_manual(
    session: Session,
    iso: str,
    *,
    article_id: int,
    quantity: Decimal | None = None,
    source: ItemSource = ItemSource.MANUAL,
) -> m.ShoppingList:
    shopping = get_list(session, iso, rebuild_first=False)
    article = session.get(m.Article, article_id)
    if article is None:
        raise ValidationError(f"Artikel {article_id} existiert nicht")
    for item in shopping.items:
        if item.article_id == article_id:
            item.quantity = quantity if quantity is not None else item.quantity
            item.have_already = False
            return shopping
    unit = Unit(article.unit)
    session.add(
        m.ShoppingListItem(
            shopping_list_id=shopping.id,
            article_id=article_id,
            quantity=quantity,
            unit=unit.value,
            source=source.value,
            spec_text=format_quantity(Quantity(quantity, unit)),
        )
    )
    session.flush()
    session.refresh(shopping)
    return shopping


def remove_item(session: Session, iso: str, *, article_id: int) -> m.ShoppingList:
    shopping = get_list(session, iso, rebuild_first=False)
    for item in list(shopping.items):
        if item.article_id == article_id:
            shopping.items.remove(item)
            session.flush()
            return shopping
    raise ValidationError(f"Artikel {article_id} steht nicht auf der Liste")


def as_text(session: Session, shopping: m.ShoppingList) -> str:
    """Fallback-Export (ARCHITECTURE.md §5): Liste zum Teilen, wenn Bring! bricht."""
    lines = [line for line in to_lines(session, shopping) if not line.have_already]
    if not lines:
        return "Einkaufsliste ist leer."
    rendered = [f"- {line.article_name}: {line.spec_text}" for line in lines]
    return "Einkaufsliste\n" + "\n".join(rendered)
