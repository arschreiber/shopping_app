"""Gerichte-Use-Cases: CRUD, Zutatenzeilen, Kategorien, Kochbestaetigung."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.enums import CategoryAxis, Effort, SuitableFor, Unit
from ..domain.model import IngredientSpec
from ..domain.nutrition import DishNutrition, dish_nutrition
from ..domain.units import DIMENSION_OF
from .articles import ValidationError


@dataclass(frozen=True, slots=True)
class IngredientInput:
    article_id: int
    quantity: Decimal | None
    unit: Unit
    note: str | None = None


@dataclass(frozen=True, slots=True)
class CategoryInput:
    axis: CategoryAxis
    name: str


def list_dishes(
    session: Session, *, query: str | None = None, include_archived: bool = False
) -> list[m.Dish]:
    stmt = select(m.Dish).order_by(m.Dish.name)
    if not include_archived:
        stmt = stmt.where(m.Dish.archived.is_(False))
    if query:
        stmt = stmt.where(m.Dish.name.icontains(query))
    return list(session.scalars(stmt))


def get_dish(session: Session, dish_id: int) -> m.Dish:
    dish = session.get(m.Dish, dish_id)
    if dish is None:
        raise ValidationError(f"Gericht {dish_id} existiert nicht")
    return dish


def create_dish(
    session: Session,
    *,
    name: str,
    portions: int,
    packable: bool = True,
    reheatable: bool = True,
    allow_double: bool = True,
    allow_triple: bool = False,
    effort: Effort = Effort.NORMAL,
    suitable_for: SuitableFor = SuitableFor.BOTH,
    rating: int | None = None,
    prep_text: str | None = None,
    note: str | None = None,
    ingredients: list[IngredientInput] | None = None,
    categories: list[CategoryInput] | None = None,
) -> m.Dish:
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Name fehlt")
    if portions not in (1, 2, 3):
        raise ValidationError("Portionen müssen 1, 2 oder 3 sein")
    existing = session.scalar(
        select(m.Dish).where(func.lower(m.Dish.name) == cleaned.lower())
    )
    if existing is not None and not existing.archived:
        raise ValidationError(f"'{cleaned}' gibt es schon")
    if existing is not None:
        # Ein archiviertes Gericht darf seinen eigenen Namen nicht für immer blockieren:
        # es taucht in keiner Liste auf, der Fehler wäre also nicht nachvollziehbar.
        # Also wiederbeleben und überschreiben - genau dafür archivieren wir statt zu
        # löschen: die Koch-Historie bleibt erhalten.
        existing.archived = False
        return update_dish(
            session,
            existing.id,
            portions=portions,
            packable=packable,
            reheatable=reheatable,
            allow_double=allow_double,
            allow_triple=allow_triple,
            effort=effort,
            suitable_for=suitable_for,
            rating=rating,
            prep_text=prep_text,
            note=note,
            ingredients=ingredients or [],
            categories=categories or [],
        )

    dish = m.Dish(
        name=cleaned,
        portions=portions,
        packable=packable,
        reheatable=reheatable,
        allow_double=allow_double,
        allow_triple=allow_triple,
        effort=effort.value,
        suitable_for=suitable_for.value,
        rating=rating,
        prep_text=prep_text,
        note=note,
    )
    session.add(dish)
    session.flush()
    _replace_ingredients(session, dish, ingredients or [])
    _replace_categories(session, dish, categories or [])
    return dish


def update_dish(session: Session, dish_id: int, **changes) -> m.Dish:
    dish = get_dish(session, dish_id)
    ingredients = changes.pop("ingredients", None)
    categories = changes.pop("categories", None)

    if (portions := changes.pop("portions", None)) is not None:
        if portions not in (1, 2, 3):
            raise ValidationError("Portionen müssen 1, 2 oder 3 sein")
        dish.portions = portions
    if (name := changes.pop("name", None)) is not None:
        dish.name = _rename_target(session, dish, name)
    for field in (
        "packable", "reheatable", "allow_double", "allow_triple", "rating", "prep_text",
        "note", "archived",
    ):
        if (value := changes.pop(field, None)) is not None:
            setattr(dish, field, value.strip() if isinstance(value, str) else value)
    if (effort := changes.pop("effort", None)) is not None:
        dish.effort = Effort(effort).value
    if (suitable := changes.pop("suitable_for", None)) is not None:
        dish.suitable_for = SuitableFor(suitable).value

    if ingredients is not None:
        _replace_ingredients(session, dish, ingredients)
    if categories is not None:
        _replace_categories(session, dish, categories)
    return dish


def _rename_target(session: Session, dish: m.Dish, name: str) -> str:
    """Der neue Name - sofern kein anderes Gericht ihn hat, auch kein archiviertes.

    Ohne die Prüfung lief die Umbenennung in den UNIQUE-Index (500) - oder, bei anderer
    Groß-/Kleinschreibung, an ihm vorbei zu zwei Gerichten, die gleich heißen.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ValidationError("Name fehlt")
    other = session.scalar(
        select(m.Dish).where(
            func.lower(m.Dish.name) == cleaned.lower(), m.Dish.id != dish.id
        )
    )
    if other is not None:
        hint = " (archiviert)" if other.archived else ""
        raise ValidationError(f"'{cleaned}' gibt es schon{hint}")
    return cleaned


def archive_dish(session: Session, dish_id: int) -> m.Dish:
    """Nicht loeschen: der Plan-Verlauf und `cook_log` sollen erhalten bleiben."""
    dish = get_dish(session, dish_id)
    dish.archived = True
    return dish


def _replace_ingredients(
    session: Session, dish: m.Dish, ingredients: list[IngredientInput]
) -> None:
    units = dict(session.execute(select(m.Article.id, m.Article.unit)).all())
    dish.ingredients.clear()
    session.flush()
    for index, row in enumerate(ingredients):
        article_unit = units.get(row.article_id)
        if article_unit is None:
            raise ValidationError(f"Artikel {row.article_id} existiert nicht")
        if DIMENSION_OF[row.unit] != DIMENSION_OF[Unit(article_unit)]:
            raise ValidationError(
                f"Einheit {row.unit.value} passt nicht zur Artikeleinheit {article_unit} "
                "- Dimensionswechsel wird nicht geraten (general_plan.md §8 Nr. 10)"
            )
        session.add(
            m.Ingredient(
                dish_id=dish.id,
                article_id=row.article_id,
                quantity=row.quantity,
                unit=row.unit.value,
                sort_order=index,
                note=row.note,
            )
        )


def _replace_categories(
    session: Session, dish: m.Dish, categories: list[CategoryInput]
) -> None:
    dish.categories.clear()
    session.flush()
    for row in categories:
        dish.categories.append(ensure_category(session, row.axis, row.name))


def ensure_category(session: Session, axis: CategoryAxis, name: str) -> m.Category:
    cleaned = name.strip()
    existing = session.scalar(
        select(m.Category).where(
            m.Category.axis == axis.value, func.lower(m.Category.name) == cleaned.lower()
        )
    )
    if existing is not None:
        return existing
    category = m.Category(axis=axis.value, name=cleaned)
    session.add(category)
    session.flush()
    return category


def category_usage(session: Session) -> list[tuple[m.Category, int]]:
    """Kategorien mit Nutzungszahl - haeufigste Chips vorne (ARCHITECTURE.md §7)."""
    counts = dict(
        session.execute(
            select(m.DishCategory.category_id, func.count())
            .group_by(m.DishCategory.category_id)
        ).all()
    )
    categories = session.scalars(select(m.Category).order_by(m.Category.name)).all()
    return sorted(
        ((c, counts.get(c.id, 0)) for c in categories),
        key=lambda pair: (-pair[1], pair[0].name),
    )


def nutrition_for(session: Session, dish: m.Dish) -> DishNutrition:
    """Nährwerte eines gespeicherten Gerichts, je Portion."""
    from ..db.mappers import article_nutrition_index

    return dish_nutrition(
        [
            IngredientSpec(
                article_id=row.article_id, quantity=row.quantity, unit=Unit(row.unit)
            )
            for row in dish.ingredients
        ],
        article_nutrition_index(session),
        portions=dish.portions,
    )


def nutrition_by_dish(session: Session) -> dict[int, DishNutrition]:
    """Für die Gerichte-Liste: einmal alle Artikel laden, dann je Gericht rechnen."""
    from ..db.mappers import article_nutrition_index, ingredients_by_dish

    facts = article_nutrition_index(session)
    lines = ingredients_by_dish(session)
    portions = dict(session.execute(select(m.Dish.id, m.Dish.portions)).all())
    return {
        dish_id: dish_nutrition(
            lines.get(dish_id, []), facts, portions=portions.get(dish_id, 2)
        )
        for dish_id in portions
    }


def nutrition_preview(
    session: Session, rows: list[IngredientInput], *, portions: int
) -> DishNutrition:
    """Vorschau für das Formular - bevor das Gericht gespeichert ist."""
    from ..db.mappers import article_nutrition_index

    return dish_nutrition(
        [
            IngredientSpec(article_id=row.article_id, quantity=row.quantity, unit=row.unit)
            for row in rows
        ],
        article_nutrition_index(session),
        portions=portions,
    )


def confirm_cooked(
    session: Session,
    *,
    dish_id: int,
    cooked_at: date,
    slot_id: int | None = None,
    rating: int | None = None,
    note: str | None = None,
) -> m.CookLog:
    """Ein-Klick-Bestaetigung "gekocht" (general_plan.md §8 Nr. 11)."""
    dish = get_dish(session, dish_id)
    entry = session.scalar(
        select(m.CookLog).where(
            m.CookLog.dish_id == dish_id, m.CookLog.cooked_at == cooked_at
        )
    )
    if entry is None:
        entry = m.CookLog(dish_id=dish_id, cooked_at=cooked_at, slot_id=slot_id)
        session.add(entry)
    entry.confirmed = True
    if rating is not None:
        entry.rating = rating
        dish.rating = rating  # Bewertung am Gericht mitfuehren (Plan Phase 3)
    if note is not None:
        entry.note = note
    return entry


def cook_history(session: Session, dish_id: int) -> list[m.CookLog]:
    return list(
        session.scalars(
            select(m.CookLog)
            .where(m.CookLog.dish_id == dish_id)
            .order_by(m.CookLog.cooked_at.desc())
        )
    )
