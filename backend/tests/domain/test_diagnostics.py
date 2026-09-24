"""Plan-Warnungen (general_plan.md §5 Phase 1)."""

from __future__ import annotations

from conftest import dish, full_week, slot, snapshot
from mealplan.domain.diagnostics import diagnose
from mealplan.domain.enums import Meal, TimeBudget, WarningLevel
from mealplan.domain.model import Assignment, Plan, SlotKey


def codes(warnings) -> set[str]:
    return {w.code for w in warnings}


def test_warns_about_an_empty_slot(sample_dishes):
    """Halbfertiger Plan: die Lücken sind eine Warnung wert."""
    snap = snapshot(full_week(), sample_dishes)
    started = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(1))
    assert "slot_empty" in codes(diagnose(started, snap))


def test_an_untouched_week_is_not_a_list_of_warnings(sample_dishes):
    """Vierzehn Mal "noch nichts geplant" verdeckt die echten Probleme."""
    snap = snapshot(full_week(), sample_dishes)
    assert "slot_empty" not in codes(diagnose(Plan(), snap))


def test_warns_when_packed_portions_have_no_dish(sample_dishes):
    slots = list(full_week())
    slots[1] = slot(0, Meal.DINNER, packed_portions=1)
    snap = snapshot(slots, sample_dishes)
    warnings = [w for w in diagnose(Plan(), snap) if w.code == "packed_missing"]
    assert warnings and warnings[0].level is WarningLevel.ERROR


def test_warns_about_a_non_packable_dish_in_a_packing_slot(sample_dishes):
    slots = list(full_week())
    slots[1] = slot(0, Meal.DINNER, eaters_home=1, packed_portions=1)
    snap = snapshot(slots, sample_dishes)
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(8))  # nicht mitnehmbar
    assert "not_packable" in codes(diagnose(plan, snap))


def test_warns_three_times_rice(sample_dishes):
    """Der namensgebende Fall aus general_plan.md §5."""
    snap = snapshot(full_week(), sample_dishes)
    plan = (
        Plan()
        .with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(1))  # Reis
        .with_(SlotKey.of(2, Meal.DINNER), Assignment.dish(4))  # Reis
        .with_(SlotKey.of(4, Meal.DINNER), Assignment.dish(5))  # Reis
    )
    warnings = [w for w in diagnose(plan, snap) if w.code == "repetition"]
    assert any("3× Reis" in w.text for w in warnings)


def test_warns_when_effort_no_longer_fits(sample_dishes):
    """Zeitbudget nachtraeglich gekuerzt -> der Plan meldet sich."""
    slots = list(full_week())
    slots[1] = slot(0, Meal.DINNER, time_budget=TimeBudget.LITTLE)
    snap = snapshot(slots, sample_dishes)
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(6))  # aufwendig
    warnings = [w for w in diagnose(plan, snap) if w.code == "not_eligible"]
    assert warnings and "Aufwand" in warnings[0].text


def test_reports_unused_leftovers(sample_dishes):
    snap = snapshot([slot(6, Meal.DINNER)], sample_dishes)  # Sonntagabend, danach nichts
    plan = Plan().with_(SlotKey.of(6, Meal.DINNER), Assignment.dish(1))  # 3 P, 2 Esser
    warnings = [w for w in diagnose(plan, snap) if w.code == "leftover_unused"]
    assert warnings and "1 Portion(en)" in warnings[0].text


def test_warns_about_a_tiny_candidate_pool():
    snap = snapshot(full_week(), [dish(1, "Curry")])
    assert "small_pool" in codes(diagnose(Plan(), snap))


def test_a_good_plan_has_no_errors(big_pool):
    from mealplan.domain.planner import propose

    snap = snapshot(full_week(), big_pool)
    plan = propose(snap, seed=42)
    errors = [w for w in diagnose(plan, snap) if w.level is WarningLevel.ERROR]
    assert not errors, [w.text for w in errors]
