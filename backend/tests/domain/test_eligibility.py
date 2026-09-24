"""Harte Kriterien (general_plan.md §4)."""

from __future__ import annotations

from conftest import dish, slot
from mealplan.domain.eligibility import eligible
from mealplan.domain.enums import Effort, Meal, SlotSpecial, SuitableFor, TimeBudget
from mealplan.domain.model import Assignment, Plan


def test_accepts_a_fitting_dish():
    assert eligible(dish(1, "Curry"), slot(0, Meal.DINNER), Plan()).ok


def test_effort_must_fit_the_time_budget():
    verdict = eligible(
        dish(1, "Gratin", effort=Effort.ELABORATE),
        slot(0, Meal.DINNER, time_budget=TimeBudget.LITTLE),
        Plan(),
    )
    assert not verdict.ok
    assert "Aufwand 'aufwendig' passt nicht zu 'wenig Zeit'" in verdict.reasons


def test_no_time_means_no_cooking_at_all():
    for effort in Effort:
        verdict = eligible(
            dish(1, "X", effort=effort),
            slot(0, Meal.DINNER, time_budget=TimeBudget.NONE),
            Plan(),
        )
        assert not verdict.ok


def test_packed_portions_require_a_packable_dish():
    verdict = eligible(
        dish(1, "Fischstäbchen", packable=False),
        slot(0, Meal.DINNER, packed_portions=1),
        Plan(),
    )
    assert not verdict.ok
    assert "nicht mitnehmbar, Slot braucht Mitnehm-Portionen" in verdict.reasons


def test_portions_must_cover_eaters_plus_packed():
    verdict = eligible(
        dish(1, "Lachs", portions=2),
        slot(0, Meal.DINNER, eaters_home=2, packed_portions=1),
        Plan(),
    )
    assert not verdict.ok
    assert any("reichen nicht für 3" in r for r in verdict.reasons)


def test_doubling_makes_a_two_portion_dish_fit():
    assert eligible(
        dish(1, "Lachs", portions=2),
        slot(0, Meal.DINNER, eaters_home=2, packed_portions=1),
        Plan(),
        doubled=True,
    ).ok


def test_three_portion_dishes_cannot_be_doubled():
    verdict = eligible(dish(1, "Curry", portions=3), slot(0, Meal.DINNER), Plan(), doubled=True)
    assert not verdict.ok
    assert "nur 2-Portionen-Gerichte sind verdoppelbar" in verdict.reasons


def test_suitability_for_lunch_or_dinner():
    verdict = eligible(
        dish(1, "Braten", suitable_for=SuitableFor.DINNER), slot(0, Meal.LUNCH), Plan()
    )
    assert not verdict.ok
    assert "nicht für Mittag vorgesehen" in verdict.reasons


def test_eating_out_takes_no_dish():
    verdict = eligible(
        dish(1, "Curry"), slot(0, Meal.DINNER, special=SlotSpecial.EATING_OUT), Plan()
    )
    assert not verdict.ok


def test_from_pantry_still_accepts_a_dish():
    """FROM_PANTRY heisst nur: die Zutaten landen nicht auf der Liste (Plan §4)."""
    assert eligible(
        dish(1, "Curry"), slot(0, Meal.DINNER, special=SlotSpecial.FROM_PANTRY), Plan()
    ).ok


def test_a_dish_is_cooked_at_most_once_per_week():
    plan = Plan().with_(slot(0, Meal.DINNER).key, Assignment.dish(1))
    verdict = eligible(dish(1, "Curry"), slot(2, Meal.DINNER), plan)
    assert not verdict.ok
    assert "diese Woche schon eingeplant" in verdict.reasons


def test_a_leftover_assignment_does_not_block_the_dish():
    """Reste sind kein zweites Kochen."""
    source = slot(0, Meal.DINNER).key
    plan = Plan().with_(slot(1, Meal.LUNCH).key, Assignment.leftover(source, 1, 1))
    assert eligible(dish(1, "Curry"), slot(3, Meal.DINNER), plan).ok


def test_all_reasons_are_reported_not_just_the_first():
    verdict = eligible(
        dish(1, "Gratin", portions=2, packable=False, effort=Effort.ELABORATE),
        slot(0, Meal.DINNER, eaters_home=2, packed_portions=2, time_budget=TimeBudget.LITTLE),
        Plan(),
    )
    assert len(verdict.reasons) == 3
