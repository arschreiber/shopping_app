"""Weiche Kriterien. Geprueft wird nicht die Zahl, sondern *welche Regel* feuert."""

from __future__ import annotations

from decimal import Decimal

from conftest import dish, full_week, slot, snapshot
from mealplan.domain.enums import Effort, Meal, TimeBudget
from mealplan.domain.model import Assignment, Plan, replace
from mealplan.domain.scoring import score


def rules(breakdown) -> dict[str, float]:
    return {c.rule: c.delta for c in breakdown.contributions if c.rule != "base"}


def snap_with(*dishes):
    return snapshot(full_week(), dishes)


def test_score_is_a_list_of_named_contributions():
    """ARCHITECTURE.md §4 Nr. 1: Die Begründung *ist* der Score."""
    snap = snap_with(dish(1, "Curry", rating=5, weeks_since_cooked=6))
    breakdown = score(snap.dishes[0], slot(0, Meal.DINNER), Plan(), snap)
    assert breakdown.total == round(sum(c.delta for c in breakdown.contributions), 3)
    assert "rotation" in rules(breakdown)
    assert any("seit 6 Wochen nicht gekocht" in text for text in breakdown.reasons())


def test_same_protein_on_adjacent_days_is_penalised_more_than_same_week():
    a = dish(1, "Lachs", protein="Fisch")
    b = dish(2, "Fischcurry", protein="Fisch")
    snap = snap_with(a, b)

    adjacent = Plan().with_(slot(0, Meal.DINNER).key, Assignment.dish(1))
    near = score(b, slot(1, Meal.LUNCH), adjacent, snap)

    distant = Plan().with_(slot(0, Meal.DINNER).key, Assignment.dish(1))
    far = score(b, slot(5, Meal.DINNER), distant, snap)

    assert rules(near)["variety_protein"] < rules(far)["variety_protein"] < 0


def test_never_cooked_gets_a_bonus():
    snap = snap_with(dish(1, "Neu", weeks_since_cooked=None))
    breakdown = score(snap.dishes[0], slot(0, Meal.DINNER), Plan(), snap)
    assert rules(breakdown)["never_cooked"] > 0
    assert "noch nie gekocht" in breakdown.reasons()


def test_recently_cooked_is_penalised():
    snap = snap_with(dish(1, "Curry", weeks_since_cooked=1))
    breakdown = score(snap.dishes[0], slot(0, Meal.DINNER), Plan(), snap)
    assert rules(breakdown)["cooked_recently"] < 0


def test_rating_is_neutral_at_three_stars():
    snap = snap_with(dish(1, "Ok", rating=3))
    assert "rating" not in rules(score(snap.dishes[0], slot(0, Meal.DINNER), Plan(), snap))


def test_offer_bonus_is_capped():
    generous = replace(dish(1, "Lachs"), offer_savings_eur=Decimal("99"))
    snap = snap_with(generous)
    breakdown = score(generous, slot(0, Meal.DINNER), Plan(), snap)
    assert rules(breakdown)["offers"] == snap.weights.offer_cap
    assert any("Angebot" in text for text in breakdown.reasons())


def test_exact_portions_beat_leftovers_when_nothing_can_use_them():
    """Zwei Esser, nichts danach: das 2-Portionen-Gericht gewinnt."""
    exact = dish(1, "Lachs", portions=2)
    surplus = dish(2, "Curry", portions=3)
    snap = snapshot(
        [slot(6, Meal.DINNER)],  # Sonntagabend, danach kommt nichts
        [exact, surplus],
    )
    a = score(exact, slot(6, Meal.DINNER), Plan(), snap)
    b = score(surplus, slot(6, Meal.DINNER), Plan(), snap)
    assert rules(a)["exact_portions"] > 0
    assert rules(b)["waste"] < 0
    assert a.total > b.total


def test_surplus_that_covers_a_later_slot_is_a_bonus_not_waste():
    """Die Rest-Portion deckt den Home-Office-Mittag am nächsten Tag."""
    surplus = dish(2, "Curry", portions=3)
    snap = snapshot([slot(0, Meal.DINNER), slot(1, Meal.LUNCH, eaters_home=1)], [surplus])
    breakdown = score(surplus, slot(0, Meal.DINNER), Plan(), snap)
    assert rules(breakdown)["surplus_usable"] > 0
    assert "waste" not in rules(breakdown)


def test_a_repeated_category_costs_more_every_time():
    """Das dritte Brot muss teurer sein als das zweite - sonst warnt nur `diagnose`."""
    a = dish(1, "Brot A", side="Brot")
    b = dish(2, "Brot B", side="Brot")
    c = dish(3, "Brot C", side="Brot")
    snap = snap_with(a, b, c)

    one = Plan().with_(slot(0, Meal.DINNER).key, Assignment.dish(1))
    two = one.with_(slot(2, Meal.DINNER).key, Assignment.dish(2))

    second = rules(score(c, slot(5, Meal.DINNER), one, snap))["variety_side"]
    third = rules(score(c, slot(5, Meal.DINNER), two, snap))["variety_side"]
    assert third < second < 0


def test_time_is_a_rule_not_a_bonus():
    """Bei wenig Zeit darf nur Schnelles hin - ein Bonus dafür bekäme dort jedes frische
    Gericht und würde nur die Reste zurücksetzen."""
    quick = dish(1, "Reispfanne", effort=Effort.QUICK)
    snap = snap_with(quick)
    tight = score(quick, slot(0, Meal.DINNER, time_budget=TimeBudget.LITTLE), Plan(), snap)
    normal = score(quick, slot(0, Meal.DINNER), Plan(), snap)
    assert tight.total == normal.total


def test_doubling_costs_a_little()  :
    two = dish(1, "Lachs", portions=2)
    snap = snap_with(two)
    single = score(two, slot(0, Meal.DINNER), Plan(), snap)
    doubled = score(two, slot(0, Meal.DINNER), Plan(), snap, factor=2)
    assert rules(doubled)["doubling"] < 0
    assert doubled.total < single.total  # ohne Mitnehm-Bedarf lohnt Verdoppeln nicht


def test_cooking_a_single_portion_recipe_twice_is_no_extra_effort():
    """Doppelt ist der normale Gebrauch eines 1er-Rezepts, kein großer Topf."""
    burger = dish(1, "Burger", portions=1)
    snap = snap_with(burger)
    twice = score(burger, slot(0, Meal.DINNER), Plan(), snap, factor=2)
    assert "doubling" not in rules(twice)
    assert rules(twice)["exact_portions"] > 0
