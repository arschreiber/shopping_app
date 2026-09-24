"""Gerichte-Router inklusive Zeilen-Parser (ARCHITECTURE.md §7)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, status

from ...db import mappers
from ...domain.enums import Meal
from ...services import articles as articles_service
from ...services import dishes as service
from ...services.ingredient_parsing import (
    parse_lines,
    suggested_article_unit,
    unit_matches_article,
)
from ..deps import CatalogDep, SessionDep
from ..mapping import category_out, dish_out, dish_summary, nutrition_out
from ..schemas.common import (
    ArticleOut,
    ArticleSuggestion,
    CategoryOut,
    CookConfirmIn,
    DishIn,
    DishNutritionOut,
    DishOut,
    DishPatch,
    DishSummary,
    NutritionPreviewIn,
    ParsedLineOut,
    ParseIn,
    ParseOut,
)

router = APIRouter(prefix="/api", tags=["dishes"])


def _history(session) -> tuple[dict[int, int], dict[int, date]]:
    ages = mappers.cooked_weeks_ago(session, date.today())
    from sqlalchemy import select

    from ...db import models as m

    rows = session.execute(
        select(m.CookLog.dish_id, m.CookLog.cooked_at).where(m.CookLog.confirmed.is_(True))
    ).all()
    last: dict[int, date] = {}
    for dish_id, cooked_at in rows:
        if dish_id not in last or cooked_at > last[dish_id]:
            last[dish_id] = cooked_at
    return ages, last


@router.get("/dishes", response_model=list[DishSummary])
def list_dishes(
    session: SessionDep, q: str | None = None, include_archived: bool = False
) -> list[DishSummary]:
    ages, last = _history(session)
    nutrition = service.nutrition_by_dish(session)
    return [
        dish_summary(
            dish,
            weeks_since=ages.get(dish.id),
            last_cooked=last.get(dish.id),
            nutrition=nutrition.get(dish.id),
        )
        for dish in service.list_dishes(session, query=q, include_archived=include_archived)
    ]


@router.post("/dishes", response_model=DishOut, status_code=status.HTTP_201_CREATED)
def create_dish(session: SessionDep, payload: DishIn) -> DishOut:
    dish = service.create_dish(
        session,
        name=payload.name,
        portions=payload.portions,
        packable=payload.packable,
        effort=payload.effort,
        suitable_for=payload.suitable_for,
        rating=payload.rating,
        prep_text=payload.prep_text,
        note=payload.note,
        ingredients=[
            service.IngredientInput(
                article_id=row.article_id,
                quantity=row.quantity,
                unit=row.unit,
                note=row.note,
            )
            for row in payload.ingredients
        ],
        categories=[
            service.CategoryInput(axis=row.axis, name=row.name) for row in payload.categories
        ],
    )
    session.flush()
    session.refresh(dish)
    return dish_out(dish, nutrition=service.nutrition_for(session, dish))


@router.get("/dishes/{dish_id}", response_model=DishOut)
def get_dish(session: SessionDep, dish_id: int) -> DishOut:
    ages, last = _history(session)
    dish = service.get_dish(session, dish_id)
    return dish_out(
        dish,
        weeks_since=ages.get(dish_id),
        last_cooked=last.get(dish_id),
        nutrition=service.nutrition_for(session, dish),
    )


@router.patch("/dishes/{dish_id}", response_model=DishOut)
def update_dish(session: SessionDep, dish_id: int, payload: DishPatch) -> DishOut:
    changes = payload.model_dump(exclude_unset=True)
    if "ingredients" in changes and changes["ingredients"] is not None:
        changes["ingredients"] = [
            service.IngredientInput(
                article_id=row["article_id"],
                quantity=row["quantity"],
                unit=row["unit"],
                note=row.get("note"),
            )
            for row in changes["ingredients"]
        ]
    if "categories" in changes and changes["categories"] is not None:
        changes["categories"] = [
            service.CategoryInput(axis=row["axis"], name=row["name"])
            for row in changes["categories"]
        ]
    dish = service.update_dish(session, dish_id, **changes)
    session.flush()
    session.refresh(dish)
    return dish_out(dish, nutrition=service.nutrition_for(session, dish))


@router.delete("/dishes/{dish_id}", response_model=DishOut)
def archive_dish(session: SessionDep, dish_id: int) -> DishOut:
    """Archivieren statt loeschen - der Verlauf soll erhalten bleiben."""
    dish = service.archive_dish(session, dish_id)
    session.flush()
    session.refresh(dish)
    return dish_out(dish)


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(session: SessionDep) -> list[CategoryOut]:
    """Chip-Picker, haeufigste zuerst (ARCHITECTURE.md §7)."""
    return [category_out(c, usage) for c, usage in service.category_usage(session)]


@router.post("/nutrition/preview", response_model=DishNutritionOut)
def preview_nutrition(session: SessionDep, payload: NutritionPreviewIn) -> DishNutritionOut:
    """Nährwerte für ein noch nicht gespeichertes Gericht.

    Die Rechnung liegt in `domain/nutrition.py` - das Frontend soll sie nicht
    nachbauen (ARCHITECTURE.md §7: keine Logik-Duplikate im Frontend).
    """
    result = service.nutrition_preview(
        session,
        [
            service.IngredientInput(
                article_id=row.article_id, quantity=row.quantity, unit=row.unit
            )
            for row in payload.ingredients
        ],
        portions=payload.portions,
    )
    return nutrition_out(result)  # type: ignore[return-value]


@router.post("/parse/ingredients", response_model=ParseOut)
def parse_ingredients(
    session: SessionDep, catalog: CatalogDep, payload: ParseIn
) -> ParseOut:
    """Eine Zeile pro Zutat -> strukturierte Zeilen. Deterministisch, kein LLM."""
    index = articles_service.name_index(session)
    units = mappers.article_units(session)
    out: list[ParsedLineOut] = []
    for line in parse_lines(payload.text, index, units):
        conflict = False
        if line.article_id is not None:
            article_unit = units.get(line.article_id)
            conflict = article_unit is not None and not unit_matches_article(
                line.unit, article_unit
            )
        suggestion = None
        near: list[ArticleSuggestion] = []
        if line.article_id is None and line.name:
            hits = catalog.suggest(line.name, limit=1)
            suggestion = hits[0].name if hits else None
            # Bevor ein neuer Artikel entsteht: gibt es schon einen, der gemeint ist?
            near = [
                ArticleSuggestion(
                    article=ArticleOut.of(article),
                    score=hit.score,
                    kind=hit.kind,
                    matched_name=hit.matched_name,
                )
                for article, hit in articles_service.suggestions_for(session, line.name)
            ]
        out.append(
            ParsedLineOut(
                raw=line.raw,
                name=line.name,
                quantity=line.quantity,
                unit=line.unit,
                article_id=line.article_id,
                article_name=line.article_name,
                confidence=line.confidence,
                note=line.note,
                suggested_unit=suggested_article_unit(line.unit),
                unit_conflict=conflict,
                catalog_suggestion=suggestion,
                suggestions=near,
            )
        )
    return ParseOut(lines=out)


@router.post("/cook-log", response_model=DishOut)
def confirm_cooked(session: SessionDep, payload: CookConfirmIn) -> DishOut:
    """Ein-Klick-Bestaetigung am Folgetag (general_plan.md §8 Nr. 11)."""
    slot_id = None
    if payload.slot_day is not None and payload.slot_meal is not None:
        slot_id = _slot_id_for(session, payload.cooked_at, payload.slot_day, payload.slot_meal)
    service.confirm_cooked(
        session,
        dish_id=payload.dish_id,
        cooked_at=payload.cooked_at,
        slot_id=slot_id,
        rating=payload.rating,
        note=payload.note,
    )
    session.flush()
    dish = service.get_dish(session, payload.dish_id)
    return dish_out(dish)


def _slot_id_for(session, cooked_at: date, day: int, meal: Meal) -> int | None:
    from sqlalchemy import select

    from ...db import models as m

    iso = cooked_at.isocalendar()
    week = session.scalar(
        select(m.Week).where(m.Week.iso_year == iso.year, m.Week.iso_week == iso.week)
    )
    if week is None:
        return None
    for slot in week.slots:
        if slot.day == day and slot.meal == meal.value:
            return slot.id
    return None
