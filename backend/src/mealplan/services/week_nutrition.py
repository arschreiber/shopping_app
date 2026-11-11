"""Nährwerte der Woche aus dem Plan (Logik: domain/week_nutrition.py)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import mappers
from ..db import models as m
from ..domain.enums import AssignmentKind, Meal
from ..domain.micronutrients import dish_micronutrients
from ..domain.model import SlotKey
from ..domain.nutrition import dish_nutrition
from ..domain.week_nutrition import MealEntry, WeekNutrition, week_nutrition
from . import planning
from .nutrients import micro_index
from .weeks import get_or_create_week

COUNTED = (AssignmentKind.DISH, AssignmentKind.LEFTOVER)


def for_week(session: Session, iso: str) -> tuple[m.Week, WeekNutrition, dict[int, str]]:
    """Woche, ihre Nährwerte und die Namen der gezählten Gerichte."""
    week = get_or_create_week(session, iso)
    snapshot, plan = planning.build_context(session, week)
    facts = mappers.article_nutrition_index(session)
    lines = mappers.ingredients_by_dish(session)
    micro_facts, skipped = micro_index(session)
    dishes = {
        dish_id: (name, portions)
        for dish_id, name, portions in session.execute(
            select(m.Dish.id, m.Dish.name, m.Dish.portions)
        ).all()
    }

    cache: dict[int, tuple] = {}
    entries: list[MealEntry] = []
    for slot in week.slots:
        if mappers.is_cancelled(slot):
            continue  # ausgefallen: nicht gegessen
        key = SlotKey.of(slot.day, Meal(slot.meal))
        if snapshot.slot(key).demand <= 0:
            continue
        assignment = plan.get(key)
        if (
            assignment is None
            or assignment.kind not in COUNTED
            or assignment.dish_id is None
            or assignment.dish_id not in dishes
        ):
            continue
        dish_id = assignment.dish_id
        if dish_id not in cache:
            portions = dishes[dish_id][1]
            rows = lines.get(dish_id, [])
            cache[dish_id] = (
                dish_nutrition(rows, facts, portions=portions),
                dish_micronutrients(rows, micro_facts, skipped=skipped, portions=portions),
            )
        nutrition, micros = cache[dish_id]
        if not nutrition.has_any:
            continue  # ohne jede Angabe gibt es nichts zu zählen
        entries.append(
            MealEntry(
                day=slot.day,
                meal=Meal(slot.meal),
                dish_id=dish_id,
                nutrients=nutrition.per_portion,
                micros=micros.per_portion,
                complete=nutrition.is_complete and micros.is_complete,
            )
        )
    names = {dish_id: dishes[dish_id][0] for dish_id in {e.dish_id for e in entries}}
    return week, week_nutrition(entries), names
