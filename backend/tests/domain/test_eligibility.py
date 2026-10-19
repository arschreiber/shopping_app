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
        dish(1, "Gratin", effort=Effort.NORMAL),
        slot(0, Meal.DINNER, time_budget=TimeBudget.LITTLE),
        Plan(),
    )
    assert not verdict.ok
    assert "Aufwand 'normal' passt nicht zu 'wenig Zeit'" in verdict.reasons


def test_little_time_takes_only_quick_dishes():
    tight = slot(0, Meal.DINNER, time_budget=TimeBudget.LITTLE)
    assert eligible(dish(1, "Reispfanne", effort=Effort.QUICK), tight, Plan()).ok
    assert not eligible(dish(1, "Gratin", effort=Effort.NORMAL), tight, Plan()).ok


def test_normal_time_takes_every_dish():
    for effort in Effort:
        assert eligible(dish(1, "X", effort=effort), slot(0, Meal.DINNER), Plan()).ok


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
        factor=2,
    ).ok


def test_three_portion_dishes_cannot_be_doubled():
    verdict = eligible(dish(1, "Curry", portions=3), slot(0, Meal.DINNER), Plan(), factor=2)
    assert not verdict.ok
    assert "3-Portionen-Gerichte werden nicht vervielfacht" in verdict.reasons


def test_two_portion_dishes_are_at_most_doubled():
    verdict = eligible(dish(1, "Lachs", portions=2), slot(0, Meal.DINNER), Plan(), factor=3)
    assert "2-Portionen-Gerichte werden höchstens verdoppelt" in verdict.reasons


def test_a_single_portion_dish_cooked_twice_covers_two_eaters():
    burger = dish(1, "Burger", portions=1)
    assert not eligible(burger, slot(0, Meal.DINNER), Plan()).ok
    assert eligible(burger, slot(0, Meal.DINNER), Plan(), factor=2).ok


def test_tripling_a_single_portion_dish_must_be_allowed():
    """Dreifach ist eigens freizugeben - doppelt (zwei Esser) ist der Normalfall."""
    hungry = slot(0, Meal.DINNER, eaters_home=2, packed_portions=1)
    verdict = eligible(dish(1, "Ramen", portions=1), hungry, Plan(), factor=3)
    assert "verdreifachen ist bei diesem Gericht nicht vorgesehen" in verdict.reasons
    assert eligible(dish(1, "Ramen", portions=1, allow_triple=True), hungry, Plan(), factor=3).ok


def test_doubling_can_be_switched_off_per_dish():
    """Passt nicht in die Pfanne: dann hilft auch die Portionszahl nicht."""
    verdict = eligible(
        dish(1, "Auflauf", portions=2, allow_double=False),
        slot(0, Meal.DINNER, eaters_home=2, packed_portions=1),
        Plan(),
        factor=2,
    )
    assert not verdict.ok
    assert "verdoppeln ist bei diesem Gericht nicht vorgesehen" in verdict.reasons


def test_fresh_take_along_still_needs_a_packable_dish():
    verdict = eligible(
        dish(1, "Fischstäbchen", packable=False),
        slot(0, Meal.DINNER, eaters_home=1, packed_portions=1, packed_fresh=True),
        Plan(),
    )
    assert "nicht mitnehmbar, Slot braucht Mitnehm-Portionen" in verdict.reasons

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
        dish(1, "Gratin", portions=2, packable=False, effort=Effort.NORMAL),
        slot(0, Meal.DINNER, eaters_home=2, packed_portions=2, time_budget=TimeBudget.LITTLE),
        Plan(),
    )
    assert len(verdict.reasons) == 3


def test_what_cannot_be_reheated_must_come_out_even():
    """Nicht aufwärmbar: Reste taugen nichts, also nur eine Größe, die genau aufgeht."""
    crispy = dish(1, "Knusper-Tofu", portions=3, reheatable=False)
    three_for_two = eligible(crispy, slot(0, Meal.DINNER), Plan())
    assert not three_for_two.ok
    assert "nicht aufwärmbar - 1 Portion bliebe übrig" in three_for_two.reasons
    assert eligible(crispy, slot(0, Meal.DINNER, packed_portions=1), Plan()).ok

    bowl = dish(2, "Bowl", portions=2, reheatable=False)
    assert eligible(bowl, slot(0, Meal.DINNER), Plan()).ok
    assert not eligible(bowl, slot(0, Meal.DINNER), Plan(), factor=2).ok
    assert not eligible(bowl, slot(1, Meal.LUNCH, eaters_home=1), Plan()).ok
