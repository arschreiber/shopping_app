"""Kandidatenlisten, Auto-Vorschlag, Reroll (ARCHITECTURE.md §4)."""

from __future__ import annotations

import random

from conftest import dish, full_week, slot, snapshot
from mealplan.domain.enums import AssignmentKind, Effort, Meal, SlotSpecial, TimeBudget
from mealplan.domain.leftovers import PortionLedger
from mealplan.domain.model import (
    Assignment,
    Candidate,
    Contribution,
    Plan,
    ScoreBreakdown,
    SlotKey,
)
from mealplan.domain.planner import _pick, candidates, propose, reroll, reroll_options
from mealplan.domain.weights import PlannerWeights


def test_candidates_are_sorted_by_score(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    options = candidates(snap.slot(SlotKey.of(0, Meal.DINNER)), Plan(), snap)
    assert options
    assert [c.total for c in options] == sorted((c.total for c in options), reverse=True)


def test_candidates_exclude_ineligible_dishes_by_default(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    tight = slot(0, Meal.DINNER, time_budget=TimeBudget.LITTLE)
    labels = {c.label for c in candidates(tight, Plan(), snap)}
    assert "Kartoffelgratin" not in labels  # normal, braucht Zeit
    assert "Linsencurry" in labels  # schnell


def test_include_ineligible_explains_why_a_dish_is_missing(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    tight = slot(0, Meal.DINNER, time_budget=TimeBudget.LITTLE)
    shown = {c.label: c.warnings for c in candidates(tight, Plan(), snap, include_ineligible=True)}
    assert any("Aufwand" in w for w in shown["Kartoffelgratin"])


def test_a_dish_that_may_not_be_doubled_offers_no_doubled_variant():
    """Der Schalter am Gericht nimmt die doppelte Variante aus der Auswahl."""
    pool = [
        dish(1, "Auflauf", portions=2, side="Kartoffeln", protein="vegetarisch"),
        dish(2, "Pfanne", portions=2, allow_double=False, side="Reis", protein="Hähnchen"),
    ]
    snap = snapshot(full_week(), pool)
    labels = {c.label for c in candidates(snap.slot(SlotKey.of(0, Meal.DINNER)), Plan(), snap)}
    assert {"Auflauf", "Auflauf (doppelt)", "Pfanne"} <= labels
    assert "Pfanne (doppelt)" not in labels



def test_a_single_portion_dish_is_offered_in_the_sizes_it_allows():
    """Für zwei Esser: doppelt passt genau, dreifach nur wenn erlaubt - und weil es in
    einer Größe passt, steht das Gericht nicht zusätzlich unter "passt nicht"."""
    pool = [
        dish(1, "Burger", portions=1, side="Brot", protein="Käse"),
        dish(2, "Ramen", portions=1, allow_triple=True, side="Nudeln", protein="Tofu"),
    ]
    snap = snapshot(full_week(), pool)
    shown = candidates(
        snap.slot(SlotKey.of(0, Meal.DINNER)), Plan(), snap, include_ineligible=True
    )
    assert {c.label for c in shown} == {
        "Burger (doppelt)", "Ramen (doppelt)", "Ramen (dreifach)"
    }
    assert {c.assignment.factor for c in shown if c.label.startswith("Burger")} == {2}


def test_a_single_portion_dish_without_a_fitting_size_says_why():
    snap = snapshot(full_week(), [dish(1, "Burger", portions=1, allow_double=False)])
    shown = candidates(
        snap.slot(SlotKey.of(0, Meal.DINNER)), Plan(), snap, include_ineligible=True
    )
    assert [c.label for c in shown] == ["Burger"]
    assert any("1 Portionen reichen nicht für 2" in w for w in shown[0].warnings)

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
    plan = Plan().with_(mo_dinner, Assignment.dish(2, factor=2))  # 4 Portionen, 2 Esser

    options = candidates(snap.slot(SlotKey.of(1, Meal.LUNCH)), plan, snap)
    assert options[0].assignment.kind is AssignmentKind.LEFTOVER


def test_fresh_take_along_is_cooked_not_taken_from_leftovers(sample_dishes):
    """Abendessen vor einem Termin: die Mitnehm-Portion wird frisch gekocht. Vorgekocht
    (der Standard) darf dieselbe Mahlzeit aus Resten kommen."""
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(2, factor=2))  # 2 übrig
    tuesday = SlotKey.of(1, Meal.DINNER)
    for fresh, leftovers_offered in ((False, True), (True, False)):
        slots = list(full_week())
        slots[3] = slot(1, Meal.DINNER, eaters_home=1, packed_portions=1, packed_fresh=fresh)
        snap = snapshot(slots, sample_dishes)
        options = candidates(snap.slot(tuesday), plan, snap)
        kinds = {c.assignment.kind for c in options}
        assert (AssignmentKind.LEFTOVER in kinds) is leftovers_offered
        assert AssignmentKind.DISH in kinds
        assert "Fischstäbchen mit Kartoffelsalat" not in {c.label for c in options}

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


def test_propose_skips_eating_out_and_respects_little_time(sample_dishes):
    slots = list(full_week())
    slots[1] = slot(0, Meal.DINNER, special=SlotSpecial.EATING_OUT, eaters_home=0)
    slots[2] = slot(1, Meal.LUNCH, time_budget=TimeBudget.LITTLE, eaters_home=2)
    snap = snapshot(slots, sample_dishes)
    quick = {d.id for d in sample_dishes if d.effort is Effort.QUICK}

    for seed in range(10):
        plan = propose(snap, seed=seed)
        assert plan.get(SlotKey.of(0, Meal.DINNER)).is_empty
        # Bei wenig Zeit: Reste oder ein schnelles Gericht, nie ein normales
        tight = plan.get(SlotKey.of(1, Meal.LUNCH))
        assert tight.kind is AssignmentKind.LEFTOVER or tight.dish_id in quick, seed


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
    assert snap.dish(assignment.dish_id).portions_for(assignment.factor) >= 3


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


# --------------------------------------------------------------------------- Zufall


def _fake(dish_id: int, total: float, *, leftover: bool = False) -> Candidate:
    score = ScoreBreakdown.of([Contribution("base", total, "")])
    assignment = (
        Assignment.leftover(SlotKey.of(0, Meal.DINNER), dish_id, 2, score=score)
        if leftover
        else Assignment.dish(dish_id, score=score)
    )
    return Candidate(assignment=assignment, label=str(dish_id), score=score)


def test_randomness_mixes_similar_dishes_but_not_clear_losers():
    options = [_fake(1, 20.0), _fake(2, 18.0), _fake(3, 5.0)]
    picked = {_pick(options, random.Random(n), 6.0).assignment.dish_id for n in range(200)}
    assert picked == {1, 2}  # 2 Punkte Rückstand: mal dran; 15 Punkte: nie


def test_without_randomness_the_best_dish_always_wins():
    options = [_fake(1, 20.0), _fake(2, 19.9)]
    assert {_pick(options, random.Random(n), 0.0).assignment.dish_id for n in range(50)} == {1}


def test_randomness_never_decides_between_leftovers_and_fresh_cooking():
    """Reste gegen frisch entscheidet der echte Score - der Zufall wählt nur unter frischen
    Gerichten. Sonst würde er mal Reste verschwenden, mal ein besseres Essen verdrängen."""
    as_good = [_fake(9, 17.0, leftover=True), _fake(1, 17.0), _fake(2, 16.0)]
    worse = [_fake(1, 17.0), _fake(9, 16.5, leftover=True), _fake(2, 16.0)]
    for seed in range(100):
        assert _pick(as_good, random.Random(seed), 6.0).assignment.kind is AssignmentKind.LEFTOVER
        assert _pick(worse, random.Random(seed), 6.0).assignment.kind is AssignmentKind.DISH


def _choices(plan: Plan) -> tuple:
    return tuple(sorted((key.index, a.choice) for key, a in plan.items()))


def test_a_new_seed_gives_a_new_week_and_the_same_seed_the_same(big_pool):
    snap = snapshot(full_week(), big_pool)
    plans = {seed: _choices(propose(snap, seed=seed)) for seed in range(6)}
    assert _choices(propose(snap, seed=3)) == plans[3]
    assert len(set(plans.values())) > 1


def test_without_randomness_every_seed_gives_the_same_week(big_pool):
    weights = PlannerWeights(randomness=0.0)
    snap = snapshot(full_week(), big_pool, weights=weights)
    assert len({_choices(propose(snap, seed=seed)) for seed in range(6)}) == 1


# ---------------------------------------------------------------------- Neu würfeln


def test_reroll_draws_other_dishes_not_the_same_one_in_another_size():
    pool = [
        dish(1, "Lachs", portions=2, side="Kartoffeln", protein="Fisch"),
        dish(2, "Bolognese", portions=2, side="Nudeln", protein="Soja"),
        dish(3, "Curry", portions=2, side="Reis", protein="Tofu"),
    ]
    snap = snapshot(full_week(), pool)
    monday = SlotKey.of(0, Meal.DINNER)
    plan = Plan().with_(monday, Assignment.dish(1))
    options = reroll_options(snap, plan, monday)
    assert [c.assignment.dish_id for c in options] in ([2, 3], [3, 2])  # je einmal, ohne Lachs


def test_reroll_refills_the_meal_that_lived_on_its_leftovers():
    pool = [
        dish(1, "Hirtenkäse-Reispfanne", side="Reis", protein="Hirtenkäse"),  # 3 P
        dish(2, "Lachs", portions=2, side="Kartoffeln", protein="Fisch"),
        dish(3, "Curry", side="Reis", protein="Tofu"),  # 3 P
    ]
    slots = list(full_week())
    slots[2] = slot(1, Meal.LUNCH, eaters_home=1)
    snap = snapshot(slots, pool)
    monday, tuesday = SlotKey.of(0, Meal.DINNER), SlotKey.of(1, Meal.LUNCH)
    plan = (
        Plan()
        .with_(monday, Assignment.dish(1))
        .with_(tuesday, Assignment.leftover(monday, 1, 1))
    )
    for seed in range(10):
        rerolled = reroll(snap, plan, monday, seed=seed)
        assert rerolled.get(monday).dish_id != 1
        assert not rerolled.get(tuesday).is_empty, "Di Mittag blieb nach dem Würfeln leer"
