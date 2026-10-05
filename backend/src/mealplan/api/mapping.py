"""Domäne/ORM -> DTO. Eine Stelle, damit die Router duenn bleiben."""

from __future__ import annotations

from datetime import timedelta

from ..db import mappers
from ..db import models as m
from ..domain.enums import AssignmentKind, Meal, Unit
from ..domain.model import (
    Assignment,
    Candidate,
    Plan,
    PlanningSnapshot,
    PlanWarning,
    ScoreBreakdown,
    SlotKey,
    dish_factors,
)
from ..domain.nutrition import DishNutrition
from ..domain.units import Quantity, format_quantity, trim
from .schemas.common import (
    AssignmentOut,
    CandidateOut,
    CategoryOut,
    ContributionOut,
    DishNutritionOut,
    DishOut,
    DishSummary,
    IngredientOut,
    NutrientsOut,
    ScoreOut,
    SlotOut,
    WarningOut,
    WeekOut,
)


def _slot_order(slot: m.Slot) -> tuple[int, int]:
    """Tag, dann Mittag vor Abend - nicht alphabetisch nach der Enum-Spalte."""
    return (slot.day, 0 if Meal(slot.meal) is Meal.LUNCH else 1)


def score_out(breakdown: ScoreBreakdown | None) -> ScoreOut | None:
    if breakdown is None:
        return None
    return ScoreOut(
        total=breakdown.total,
        contributions=[
            ContributionOut(rule=c.rule, delta=c.delta, text=c.text)
            for c in breakdown.contributions
            if c.rule != "base"
        ],
        reasons=list(breakdown.reasons()),
    )


def assignment_out(
    assignment: Assignment, snapshot: PlanningSnapshot, *, cancelled: bool = False
) -> AssignmentOut | None:
    if assignment.is_empty:
        return None
    dish = snapshot.dish_or_none(assignment.dish_id)
    source = assignment.leftover_source
    return AssignmentOut(
        kind=assignment.kind,
        dish_id=assignment.dish_id,
        dish_name=dish.name if dish else None,
        factor=assignment.factor,
        portions=dish.portions_for(assignment.factor) if dish else None,
        leftover_source_day=source.day if source else None,
        leftover_source_meal=source.meal if source else None,
        leftover_source_label=str(source) if source else None,
        portions_used=assignment.portions_used,
        score=score_out(assignment.score),
        cancelled=cancelled,
    )


def warning_out(warning: PlanWarning) -> WarningOut:
    return WarningOut(
        level=warning.level,
        code=warning.code,
        text=warning.text,
        day=warning.slot.day if warning.slot else None,
        meal=warning.slot.meal if warning.slot else None,
    )


def week_out(
    week: m.Week,
    plan: Plan,
    snapshot: PlanningSnapshot,
    warnings: list[PlanWarning],
) -> WeekOut:
    from ..services.weeks import format_iso, week_summary

    start = mappers.week_start(week.iso_year, week.iso_week)
    slots = []
    for slot in sorted(week.slots, key=_slot_order):
        key = SlotKey.of(slot.day, Meal(slot.meal))
        spec = snapshot.slot(key)
        slots.append(
            SlotOut(
                day=slot.day,
                meal=Meal(slot.meal),
                date=start + timedelta(days=slot.day),
                eaters_home=slot.eaters_home,
                packed_portions=slot.packed_portions,
                packed_fresh=spec.fresh_only,
                time_budget=spec.time_budget,
                special=spec.special,
                pinned=slot.pinned,
                demand=spec.demand,
                assignment=assignment_out(
                    plan.get(key), snapshot, cancelled=mappers.is_cancelled(slot)
                ),
            )
        )
    summary = week_summary(week)
    return WeekOut(
        iso=format_iso(week.iso_year, week.iso_week),
        iso_year=week.iso_year,
        iso_week=week.iso_week,
        start_date=start,
        version=week.version,
        planner_seed=week.planner_seed,
        primary_store_id=week.primary_store_id,
        secondary_store_id=week.secondary_store_id,
        slots=slots,
        warnings=[warning_out(w) for w in warnings],
        planned_count=summary["planned"],
        needed_count=summary["needed"],
    )


def candidate_out(candidate: Candidate, snapshot: PlanningSnapshot) -> CandidateOut:
    return CandidateOut(
        label=candidate.label,
        assignment=assignment_out(candidate.assignment, snapshot)
        or AssignmentOut(kind=AssignmentKind.EMPTY),
        score=score_out(candidate.score) or ScoreOut(total=0, contributions=[], reasons=[]),
        warnings=list(candidate.warnings),
        eligible=candidate.assignment.score is not None,
    )


def nutrition_out(nutrition: DishNutrition | None) -> DishNutritionOut | None:
    if nutrition is None:
        return None
    return DishNutritionOut(
        per_portion=NutrientsOut(
            kcal=nutrition.per_portion.kcal,
            carbs_g=nutrition.per_portion.carbs_g,
            fat_g=nutrition.per_portion.fat_g,
            protein_g=nutrition.per_portion.protein_g,
        ),
        total=NutrientsOut(
            kcal=nutrition.total.kcal,
            carbs_g=nutrition.total.carbs_g,
            fat_g=nutrition.total.fat_g,
            protein_g=nutrition.total.protein_g,
        ),
        is_complete=nutrition.is_complete,
        has_any=nutrition.has_any,
        counted=len(nutrition.counted_ids),
        ingredient_count=nutrition.ingredient_count,
        missing_article_ids=list(nutrition.missing_data_ids),
        open_quantity_article_ids=list(nutrition.open_quantity_ids),
    )


def category_out(category: m.Category, usage: int = 0) -> CategoryOut:
    from ..domain.enums import CategoryAxis

    return CategoryOut(
        id=category.id, axis=CategoryAxis(category.axis), name=category.name, usage=usage
    )


def ingredient_out(ingredient: m.Ingredient) -> IngredientOut:
    unit = Unit(ingredient.unit)
    return IngredientOut(
        article_id=ingredient.article_id,
        article_name=ingredient.article.canonical_name,
        quantity=trim(ingredient.quantity),
        unit=unit,
        spec_text=format_quantity(Quantity(ingredient.quantity, unit)),
        note=ingredient.note,
    )


def dish_out(
    dish: m.Dish,
    *,
    weeks_since: int | None = None,
    last_cooked=None,
    nutrition: DishNutrition | None = None,
) -> DishOut:
    from ..domain.enums import Effort, SuitableFor

    return DishOut(
        id=dish.id,
        name=dish.name,
        portions=dish.portions,
        packable=dish.packable,
        effort=Effort(dish.effort),
        suitable_for=SuitableFor(dish.suitable_for),
        rating=dish.rating,
        prep_text=dish.prep_text,
        note=dish.note,
        archived=dish.archived,
        allow_double=dish.allow_double,
        allow_triple=dish.allow_triple,
        factors=list(dish_factors(dish.portions, dish.allow_double, dish.allow_triple)),
        categories=[category_out(c) for c in dish.categories],
        ingredients=[ingredient_out(i) for i in dish.ingredients],
        weeks_since_cooked=weeks_since,
        last_cooked=last_cooked,
        nutrition=nutrition_out(nutrition),
    )


def dish_summary(
    dish: m.Dish,
    *,
    weeks_since: int | None = None,
    last_cooked=None,
    nutrition: DishNutrition | None = None,
) -> DishSummary:
    from ..domain.enums import Effort, SuitableFor

    return DishSummary(
        id=dish.id,
        name=dish.name,
        portions=dish.portions,
        packable=dish.packable,
        allow_double=dish.allow_double,
        allow_triple=dish.allow_triple,
        factors=list(dish_factors(dish.portions, dish.allow_double, dish.allow_triple)),
        effort=Effort(dish.effort),
        suitable_for=SuitableFor(dish.suitable_for),
        rating=dish.rating,
        categories=[category_out(c) for c in dish.categories],
        ingredient_count=len(dish.ingredients),
        weeks_since_cooked=weeks_since,
        last_cooked=last_cooked,
        nutrition=nutrition_out(nutrition),
    )
