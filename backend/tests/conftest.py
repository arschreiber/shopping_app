from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mealplan.domain.enums import (
    CategoryAxis,
    Effort,
    Meal,
    SuitableFor,
    TimeBudget,
)
from mealplan.domain.model import (
    Category,
    DishSpec,
    PlanningSnapshot,
    SlotKey,
    SlotSpec,
)
from mealplan.domain.weights import DEFAULT_WEIGHTS

MONDAY = date(2026, 9, 7)


@pytest.fixture(autouse=True)
def _isolate_settings():
    """`get_settings` ist gecacht - sonst zeigt ein Test auf das echte ./data."""
    from mealplan.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def dish(
    dish_id: int,
    name: str,
    *,
    portions: int = 3,
    packable: bool = True,
    effort: Effort = Effort.NORMAL,
    suitable_for: SuitableFor = SuitableFor.BOTH,
    rating: int | None = None,
    side: str | None = None,
    protein: str | None = None,
    cuisine: str | None = None,
    weeks_since_cooked: int | None = 10,
) -> DishSpec:
    categories = set()
    if side:
        categories.add(Category(CategoryAxis.SIDE, side))
    if protein:
        categories.add(Category(CategoryAxis.PROTEIN, protein))
    if cuisine:
        categories.add(Category(CategoryAxis.CUISINE, cuisine))
    return DishSpec(
        id=dish_id,
        name=name,
        portions=portions,
        packable=packable,
        effort=effort,
        suitable_for=suitable_for,
        rating=rating,
        categories=frozenset(categories),
        weeks_since_cooked=weeks_since_cooked,
    )


def slot(
    day: int,
    meal: Meal,
    *,
    eaters_home: int = 2,
    packed_portions: int = 0,
    time_budget: TimeBudget = TimeBudget.PLENTY,
    **kwargs,
) -> SlotSpec:
    return SlotSpec(
        key=SlotKey.of(day, meal),
        eaters_home=eaters_home,
        packed_portions=packed_portions,
        time_budget=time_budget,
        **kwargs,
    )


def full_week(**overrides: SlotSpec) -> tuple[SlotSpec, ...]:
    """Standardraster: beide Mahlzeiten, zwei Esser, viel Zeit."""
    slots = []
    for day in range(7):
        for meal in (Meal.LUNCH, Meal.DINNER):
            key = f"{day}{'L' if meal is Meal.LUNCH else 'D'}"
            slots.append(overrides.get(key, slot(day, meal)))
    return tuple(slots)


def snapshot(slots, dishes, **kwargs) -> PlanningSnapshot:
    return PlanningSnapshot(
        slots=tuple(slots),
        dishes=tuple(dishes),
        weights=kwargs.pop("weights", DEFAULT_WEIGHTS),
        week_start=kwargs.pop("week_start", MONDAY),
        **kwargs,
    )


@pytest.fixture
def sample_dishes() -> list[DishSpec]:
    return [
        dish(1, "Hirtenkäse-Reispfanne", side="Reis", protein="Hirtenkäse", effort=Effort.QUICK),
        dish(2, "Lachs mit Ofengemüse", portions=2, side="Kartoffeln", protein="Fisch"),
        dish(3, "Spaghetti Bolognese", side="Nudeln", protein="Rind", cuisine="italienisch"),
        dish(4, "Linsencurry", side="Reis", protein="Hülsenfrüchte", effort=Effort.QUICK),
        dish(5, "Hähnchen-Gemüse-Pfanne", side="Reis", protein="Hähnchen"),
        dish(6, "Kartoffelgratin", portions=2, side="Kartoffeln", protein="vegetarisch",
             effort=Effort.ELABORATE),
        dish(7, "Nudelauflauf", side="Nudeln", protein="Hirtenkäse"),
        dish(8, "Fischstäbchen mit Kartoffelsalat", portions=2, side="Kartoffeln",
             protein="Fisch", effort=Effort.QUICK, packable=False),
    ]


@pytest.fixture
def big_pool() -> list[DishSpec]:
    """Realistischer Vorrat (~24 Gerichte) - so viele braucht eine ganze Woche."""
    sides = ["Reis", "Nudeln", "Kartoffeln", "Brot", "Couscous", "Polenta"]
    proteins = ["Hähnchen", "Fisch", "Hirtenkäse", "Hülsenfrüchte", "Rind", "vegetarisch"]
    out: list[DishSpec] = []
    for i in range(24):
        out.append(
            dish(
                100 + i,
                f"Gericht {i + 1}",
                portions=2 if i % 3 == 0 else 3,
                packable=i % 7 != 0,
                effort=(Effort.QUICK, Effort.NORMAL, Effort.ELABORATE)[i % 3],
                side=sides[i % len(sides)],
                protein=proteins[(i // 2) % len(proteins)],
                weeks_since_cooked=3 + (i % 9),
            )
        )
    return out
