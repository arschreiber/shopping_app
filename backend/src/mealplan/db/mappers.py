"""ORM <-> Domänen-Snapshots (ARCHITECTURE.md §2).

Hier - und nur hier - werden die *für eine Woche abgeleiteten* Fakten berechnet:
`weeks_since_cooked` (aus `cook_log`) und `offer_savings_eur` (Phase 2). Damit bleibt die
Domäne ohne Uhr und ohne Session.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.enums import (
    AssignmentKind,
    CategoryAxis,
    Effort,
    Meal,
    SlotSpecial,
    SuitableFor,
    TimeBudget,
    Unit,
)
from ..domain.model import (
    Assignment,
    Category,
    Contribution,
    DishSpec,
    IngredientSpec,
    Plan,
    PlanningSnapshot,
    ScoreBreakdown,
    SlotKey,
    SlotSpec,
)
from ..domain.nutrition import ArticleNutrition, article_nutrition
from ..domain.weights import PlannerWeights
from . import models as m


def week_start(iso_year: int, iso_week: int) -> date:
    return date.fromisocalendar(iso_year, iso_week, 1)


# ------------------------------------------------------------------------------- Gericht


def dish_to_spec(
    dish: m.Dish,
    *,
    weeks_since_cooked: int | None = None,
    offer_savings: Decimal = Decimal(0),
) -> DishSpec:
    return DishSpec(
        id=dish.id,
        name=dish.name,
        portions=dish.portions,
        packable=dish.packable,
        effort=Effort(dish.effort),
        suitable_for=SuitableFor(dish.suitable_for),
        rating=dish.rating,
        categories=frozenset(
            Category(CategoryAxis(c.axis), c.name) for c in dish.categories
        ),
        weeks_since_cooked=weeks_since_cooked,
        offer_savings_eur=offer_savings,
        article_ids=frozenset(i.article_id for i in dish.ingredients),
    )


def cooked_weeks_ago(session: Session, reference: date) -> dict[int, int]:
    """dish_id -> Wochen seit dem letzten *bestaetigten* Kochen.

    Bewusst `confirmed`: ein ausgefallenes Gericht darf nicht als gekocht zählen
    (general_plan.md §8 Nr. 11). Ohne Bestaetigung zählt der Plan-Eintrag nicht.
    """
    rows = session.execute(
        select(m.CookLog.dish_id, m.CookLog.cooked_at).where(m.CookLog.confirmed.is_(True))
    ).all()
    latest: dict[int, date] = {}
    for dish_id, cooked_at in rows:
        if dish_id not in latest or cooked_at > latest[dish_id]:
            latest[dish_id] = cooked_at
    return {
        dish_id: max(0, (reference - cooked).days // 7) for dish_id, cooked in latest.items()
    }


def ingredients_by_dish(session: Session) -> dict[int, list[IngredientSpec]]:
    rows = session.execute(
        select(
            m.Ingredient.dish_id,
            m.Ingredient.article_id,
            m.Ingredient.quantity,
            m.Ingredient.unit,
        ).order_by(m.Ingredient.dish_id, m.Ingredient.sort_order)
    ).all()
    out: dict[int, list[IngredientSpec]] = {}
    for dish_id, article_id, quantity, unit in rows:
        out.setdefault(dish_id, []).append(
            IngredientSpec(article_id=article_id, quantity=quantity, unit=Unit(unit))
        )
    return out


def article_nutrition_index(session: Session) -> dict[int, ArticleNutrition]:
    """`{article_id: ArticleNutrition}` - Artikel ohne jede Angabe fehlen hier."""
    rows = session.execute(
        select(
            m.Article.id,
            m.Article.unit,
            m.Article.kcal,
            m.Article.protein_g,
            m.Article.carbs_g,
            m.Article.fat_g,
        )
    ).all()
    out: dict[int, ArticleNutrition] = {}
    for article_id, unit, kcal, protein, carbs, fat in rows:
        facts = article_nutrition(
            article_id, Unit(unit), kcal=kcal, protein_g=protein, carbs_g=carbs, fat_g=fat
        )
        if facts is not None:
            out[article_id] = facts
    return out


def article_units(session: Session) -> dict[int, Unit]:
    rows = session.execute(select(m.Article.id, m.Article.unit)).all()
    return {article_id: Unit(unit) for article_id, unit in rows}


# ---------------------------------------------------------------------------------- Slot


def slot_to_spec(slot: m.Slot) -> SlotSpec:
    return SlotSpec(
        key=SlotKey.of(slot.day, Meal(slot.meal)),
        eaters_home=slot.eaters_home,
        packed_portions=slot.packed_portions,
        time_budget=TimeBudget(slot.time_budget),
        special=SlotSpecial(slot.special),
        pinned=slot.pinned,
    )


def plan_from_week(week: m.Week) -> Plan:
    by_id = {slot.id: SlotKey.of(slot.day, Meal(slot.meal)) for slot in week.slots}
    plan = Plan()
    for slot in week.slots:
        assignment = slot.assignment
        if assignment is None:
            continue
        source = (
            by_id.get(assignment.leftover_source_slot_id)
            if assignment.leftover_source_slot_id
            else None
        )
        plan = plan.with_(
            by_id[slot.id],
            Assignment(
                kind=AssignmentKind(assignment.kind),
                dish_id=assignment.dish_id,
                doubled=assignment.doubled,
                leftover_source=source,
                portions_used=assignment.portions_used,
                score=breakdown_from_json(assignment.score_snapshot),
            ),
        )
    return plan


def breakdown_from_json(data: dict | None) -> ScoreBreakdown | None:
    if not data:
        return None
    return ScoreBreakdown(
        total=float(data.get("total", 0.0)),
        contributions=tuple(
            Contribution(c["rule"], float(c["delta"]), c["text"])
            for c in data.get("contributions", [])
        ),
    )


def breakdown_to_json(breakdown: ScoreBreakdown | None) -> dict | None:
    if breakdown is None:
        return None
    return {
        "total": breakdown.total,
        "contributions": [
            {"rule": c.rule, "delta": c.delta, "text": c.text} for c in breakdown.contributions
        ],
    }


# ------------------------------------------------------------------------------ Snapshot


def build_snapshot(
    session: Session,
    week: m.Week,
    *,
    weights: PlannerWeights,
    leftover_shelf_life_days: int = 2,
    offer_savings: dict[int, Decimal] | None = None,
) -> PlanningSnapshot:
    start = week_start(week.iso_year, week.iso_week)
    ages = cooked_weeks_ago(session, start + timedelta(days=6))
    dishes = session.scalars(select(m.Dish).where(m.Dish.archived.is_(False))).all()
    savings = offer_savings or {}
    return PlanningSnapshot(
        slots=tuple(slot_to_spec(slot) for slot in week.slots),
        dishes=tuple(
            dish_to_spec(
                dish,
                weeks_since_cooked=ages.get(dish.id),
                offer_savings=savings.get(dish.id, Decimal(0)),
            )
            for dish in dishes
        ),
        weights=weights,
        week_start=start,
        leftover_shelf_life_days=leftover_shelf_life_days,
    )


def slot_ids_by_key(week: m.Week) -> dict[SlotKey, int]:
    return {SlotKey.of(slot.day, Meal(slot.meal)): slot.id for slot in week.slots}
