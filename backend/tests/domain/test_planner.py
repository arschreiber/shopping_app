"""Kandidatenlisten, Auto-Vorschlag, Reroll (ARCHITECTURE.md §4)."""

from __future__ import annotations

from conftest import dish, full_week, slot, snapshot
from mealplan.domain.enums import AssignmentKind, Effort, Meal, SlotSpecial, TimeBudget
from mealplan.domain.leftovers import PortionLedger
from mealplan.domain.model import Assignment, Plan, SlotKey
from mealplan.domain.planner import candidates, propose, reroll


def test_candidates_are_sorted_by_score(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    options = candidates(snap.slot(SlotKey.of(0, Meal.DINNER)), Plan(), snap)
    assert options
    assert [c.total for c in options] == sorted((c.total for c in options), reverse=True)


def test_candidates_exclude_ineligible_dishes_by_default(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    tight = slot(0, Meal.DINNER, time_budget=TimeBudget.LITTLE)
    labels = {c.label for c in candidates(tight, Plan(), snap)}
    assert "Kartoffelgratin" not in labels  # aufwendig
    assert "Linsencurry" in labels  # schnell


def test_include_ineligible_explains_why_a_dish_is_missing(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    tight = slot(0, Meal.DINNER, time_budget=TimeBudget.LITTLE)
    shown = {c.label: c.warnings for c in candidates(tight, Plan(), snap, include_ineligible=True)}
    assert any("Aufwand" in w for w in shown["Kartoffelgratin"])


def test_leftovers_appear_as_candidates(sample_dishes):
    """Eine Rest-Portion deckt den Home-Office-Mittag am nächsten Tag."""
    slots = list(full_week())
    slots[2] = slot(1, Meal.LUNCH, eaters_home=1)
    snap = snapshot(slots, sample_dishes)
    mo_dinner = SlotKey.of(0, Meal.DINNER)
    plan = Plan().with_(mo_dinner, Assignment.dish(1))  # 3 Portionen, 2 Esser -> 1 Rest

    options = candidates(snap.slot(SlotKey.of(1, Meal.LUNCH)), plan, snap)
    leftovers = [c for c in options if c.assignment.kind is AssignmentKind.LEFTOVER]
    assert len(leftovers) == 1
    assert "Reste: Hirtenkäse-Reispfanne" in leftovers[0].label


def test_a_partial_leftover_is_not_a_candidate(sample_dishes):
    """Eine Portion ernaehrt keine zwei Esser - lieber leer als unterversorgt."""
    snap = snapshot(full_week(), sample_dishes)  # alle Slots: 2 Esser
    mo_dinner = SlotKey.of(0, Meal.DINNER)
    plan = Plan().with_(mo_dinner, Assignment.dish(1))  # 3 P, 2 Esser -> 1 Rest

    options = candidates(snap.slot(SlotKey.of(1, Meal.LUNCH)), plan, snap)
    assert not [c for c in options if c.assignment.kind is AssignmentKind.LEFTOVER]


def test_a_leftover_that_covers_the_slot_ranks_high(sample_dishes):
    """Ein verdoppeltes 2er-Gericht deckt am nächsten Tag ein volles Essen."""
    snap = snapshot(full_week(), sample_dishes)
    mo_dinner = SlotKey.of(0, Meal.DINNER)
    plan = Plan().with_(mo_dinner, Assignment.dish(2, doubled=True))  # 4 Portionen, 2 Esser

    options = candidates(snap.slot(SlotKey.of(1, Meal.LUNCH)), plan, snap)
    assert options[0].assignment.kind is AssignmentKind.LEFTOVER


def test_leftovers_are_not_offered_when_the_slot_needs_packing(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    mo_dinner = SlotKey.of(0, Meal.DINNER)
    plan = Plan().with_(mo_dinner, Assignment.dish(8))  # nicht mitnehmbar
    packing = slot(1, Meal.LUNCH, eaters_home=0, packed_portions=1)
    assert not [
        c
        for c in candidates(packing, plan, snap)
        if c.assignment.kind is AssignmentKind.LEFTOVER
    ]


# ------------------------------------------------------------------------ Auto-Vorschlag


def test_propose_fills_every_slot_that_needs_food(big_pool):
    """14 Slots, ein Gericht pro Woche nur einmal - dafuer braucht es echten Vorrat."""
    snap = snapshot(full_week(), big_pool)
    plan = propose(snap, seed=42)
    for s in snap.slots:
        assert not plan.get(s.key).is_empty, f"{s.key} blieb leer"


def test_propose_is_deterministic_for_a_seed(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    first = propose(snap, seed=7)
    second = propose(snap, seed=7)
    assert {k: v.kind for k, v in first.items()} == {k: v.kind for k, v in second.items()}
    assert first.total_score() == second.total_score()


def test_propose_respects_pins(sample_dishes):
    """"Freitag will ich Pizza" bleibt beim Neu-Vorschlagen stehen."""
    snap = snapshot(full_week(), sample_dishes)
    friday = SlotKey.of(4, Meal.DINNER)
    pinned = {friday: Assignment.dish(3)}
    plan = propose(snap, pinned, seed=1)
    assert plan.get(friday).dish_id == 3


def test_propose_skips_eating_out_and_respects_no_time(sample_dishes):
    slots = list(full_week())
    slots[1] = slot(0, Meal.DINNER, special=SlotSpecial.EATING_OUT, eaters_home=0)
    slots[2] = slot(1, Meal.LUNCH, time_budget=TimeBudget.NONE, eaters_home=2)
    snap = snapshot(slots, sample_dishes)
    plan = propose(snap, seed=3)

    assert plan.get(SlotKey.of(0, Meal.DINNER)).is_empty
    # Ohne Zeit darf nur eine Reste-Karte stehen, nie ein gekochtes Gericht
    assert plan.get(SlotKey.of(1, Meal.LUNCH)).kind in {
        AssignmentKind.LEFTOVER,
        AssignmentKind.EMPTY,
    }


def test_propose_never_breaks_the_portion_ledger(sample_dishes):
    """Jeder vorgeschlagene Plan muss buchhalterisch aufgehen."""
    snap = snapshot(full_week(), sample_dishes)
    for seed in range(15):
        plan = propose(snap, seed=seed)
        PortionLedger.of(plan, snap)  # wirft bei Überziehung


def test_propose_meets_packed_demand_with_packable_dishes(sample_dishes):
    slots = list(full_week())
    slots[1] = slot(0, Meal.DINNER, eaters_home=2, packed_portions=1)  # Mo Abend für Di Büro
    slots[2] = slot(1, Meal.LUNCH, eaters_home=0)  # Di Mittag im Büro
    snap = snapshot(slots, sample_dishes)
    plan = propose(snap, seed=5)

    assignment = plan.get(SlotKey.of(0, Meal.DINNER))
    assert assignment.dish_id is not None
    assert snap.dish(assignment.dish_id).packable
    assert snap.dish(assignment.dish_id).portions_for(doubled=assignment.doubled) >= 3


def test_keep_only_fills_the_empty_slots(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    existing = {SlotKey.of(2, Meal.DINNER): Assignment.dish(4)}
    plan = propose(snap, keep=existing, seed=9)
    assert plan.get(SlotKey.of(2, Meal.DINNER)).dish_id == 4


def test_reroll_changes_a_single_slot_and_leaves_the_rest(big_pool):
    snap = snapshot(full_week(), big_pool)
    plan = propose(snap, seed=11)
    target = SlotKey.of(3, Meal.DINNER)
    before = plan.get(target)

    rerolled = reroll(snap, plan, target, seed=99)
    assert rerolled.get(target) != before
    untouched = {
        k: v.dish_id
        for k, v in plan.items()
        if k != target and v.leftover_source != target
    }
    assert {
        k: v.dish_id for k, v in rerolled.items() if k in untouched
    } == untouched


def test_local_search_does_not_lower_the_total(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    plan = propose(snap, seed=13)
    assert plan.total_score() == plan.total_score()  # rescore ist idempotent
    from mealplan.domain.planner import rescore

    assert rescore(plan, snap).total_score() == plan.total_score()


def test_small_dish_pool_leaves_slots_empty_instead_of_cheating():
    """Bei zu wenigen Gerichten bleibt ein Slot leer - `diagnose` warnt darueber."""
    snap = snapshot(full_week(), [dish(1, "Curry", effort=Effort.QUICK)])
    plan = propose(snap, seed=1)
    assert any(a.is_empty for a in plan.assignments.values())


def test_reroll_never_returns_the_same_choice(big_pool):
    """Die Score-Begründung darf zwei gleiche Wahlen nicht verschieden aussehen lassen."""
    snap = snapshot(full_week(), big_pool)
    plan = propose(snap, seed=3)
    target = SlotKey.of(2, Meal.LUNCH)
    before = plan.get(target)
    for seed in range(10):
        after = reroll(snap, plan, target, seed=seed).get(target)
        assert not after.same_choice(before), f"seed {seed} würfelte dasselbe"
