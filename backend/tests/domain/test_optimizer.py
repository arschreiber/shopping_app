"""Der Optimierer plant die Woche als Ganzes (domain/optimizer.py).

Zwei Fragen: Findet er auf kleinen Wochen wirklich den besten Plan - gemessen an
derselben Gesamtpunktzahl, die die App anzeigt? Und tut er dabei, was der Haushalt will:
wer allein isst, isst Reste statt zwei Portionen zu kochen; bei "keine Zeit" gibt es Reste.
"""

from __future__ import annotations

import pytest

from conftest import dish, full_week, slot, snapshot
from mealplan.domain.eligibility import eligible
from mealplan.domain.enums import AssignmentKind, Effort, Meal, SlotSpecial, TimeBudget
from mealplan.domain.leftovers import PortionLedger
from mealplan.domain.model import Assignment, Plan, PlanningSnapshot, SlotKey
from mealplan.domain.optimizer import optimize
from mealplan.domain.planner import propose_greedy, rescore
from mealplan.domain.weights import PlannerWeights

NO_RANDOMNESS = PlannerWeights(randomness=0.0)
MO_D, DI_L, DI_D = SlotKey.of(0, Meal.DINNER), SlotKey.of(1, Meal.LUNCH), SlotKey.of(1, Meal.DINNER)
MI_L, MI_D = SlotKey.of(2, Meal.LUNCH), SlotKey.of(2, Meal.DINNER)


def only(**meals) -> tuple:
    """Eine Woche, in der nur die genannten Mahlzeiten gegessen werden."""
    nobody = {
        f"{day}{m}": slot(day, Meal.LUNCH if m == "L" else Meal.DINNER, eaters_home=0)
        for day in range(7)
        for m in "LD"
    }
    return full_week(**{**nobody, **meals})


def best_plan(snap: PlanningSnapshot) -> Plan:
    """Optimierer ohne Zufall, bewertet wie in der App."""
    found = optimize(snap, {}, seed=0)
    assert found is not None
    return rescore(found, snap)


# ------------------------------------------------------------- gegen Durchprobieren


def _every_plan(snap: PlanningSnapshot):
    """Jeder Plan, den die Regeln des Vorschlags erlauben - für kleine Wochen zählbar."""
    slots = [s for s in snap.slots if s.needs_cooking]

    def options(plan: Plan, s):
        yield Assignment.empty()
        if s.time_budget is not TimeBudget.NONE and s.special is not SlotSpecial.FROM_PANTRY:
            for d in snap.dishes:
                if d.id in plan.dish_ids():
                    continue
                for factor in d.factors:
                    if eligible(d, s, Plan(), factor=factor).ok:
                        yield Assignment.dish(d.id, factor=factor)
        if s.fresh_only:
            return
        for pool in PortionLedger.of(plan, snap).available_at(s.key):
            if pool.source.day == s.key.day and s.time_budget is not TimeBudget.NONE:
                continue
            if pool.portions < s.demand:
                continue
            if s.packed_portions and not snap.dish(pool.dish_id).packable:
                continue
            yield Assignment.leftover(pool.source, pool.dish_id, s.demand)

    def walk(i: int, plan: Plan):
        if i == len(slots):
            yield plan
            return
        for assignment in options(plan, slots[i]):
            yield from walk(i + 1, plan.with_(slots[i].key, assignment))

    yield from walk(0, Plan())


def _rank(plan: Plan) -> tuple[int, float]:
    """Erst so viele Mahlzeiten wie möglich füllen, dann die Punkte."""
    filled = sum(1 for _, a in plan.items() if not a.is_empty)
    return filled, plan.total_score()


WEEKS = {
    "allein, wenig Zeit, keine Zeit": only(
        **{
            "0D": slot(0, Meal.DINNER),
            "1L": slot(1, Meal.LUNCH, eaters_home=1, time_budget=TimeBudget.LITTLE),
            "1D": slot(1, Meal.DINNER, eaters_home=1, packed_portions=1, packed_fresh=True),
            "2L": slot(2, Meal.LUNCH, time_budget=TimeBudget.NONE),
        }
    ),
    "Abwechslung und Mitnehmen": only(
        **{
            "0L": slot(0, Meal.LUNCH),
            "0D": slot(0, Meal.DINNER, eaters_home=1, packed_portions=1),
            "1L": slot(1, Meal.LUNCH, eaters_home=0, packed_portions=1),
            "1D": slot(1, Meal.DINNER),
        }
    ),
}
POOL = [
    dish(1, "Chili", portions=2, side="Reis", protein="Bohnen"),
    dish(2, "Ratatouille", side="Reis", protein="Gemüse", weeks_since_cooked=4),
    dish(3, "Wraps", portions=2, allow_double=False, side="Brot", protein="Bohnen",
         effort=Effort.QUICK),
    dish(4, "Fischstäbchen", portions=1, allow_triple=True, side="Kartoffeln",
         protein="Fisch", packable=False, rating=4),
]


@pytest.mark.parametrize("name", list(WEEKS))
def test_the_optimizer_finds_the_best_plan_there_is(name):
    """Kein Plan, den die Regeln erlauben, hat mehr Punkte - und die Punkte des
    Optimierers sind dieselben wie die der App (`rescore`)."""
    snap = snapshot(WEEKS[name], POOL, weights=NO_RANDOMNESS)
    brute = max((rescore(plan, snap) for plan in _every_plan(snap)), key=_rank)
    assert _rank(best_plan(snap)) == _rank(brute)


# ---------------------------------------------------------------- was der Haushalt will


def test_who_eats_alone_eats_leftovers_instead_of_cooking_two_portions():
    """Der Fall aus KW 42: Montagabend zu zweit, Dienstagmittag allein. Statt am Dienstag
    ein 2er-Gericht für eine Person: Montag das 3er-Gericht, Dienstag die Reste."""
    pool = [
        dish(1, "Chili", portions=2, allow_double=False),
        dish(2, "Ratatouille", portions=3),
        dish(3, "Wraps", portions=2, allow_double=False),
    ]
    week = only(**{"0D": slot(0, Meal.DINNER), "1L": slot(1, Meal.LUNCH, eaters_home=1)})
    plan = best_plan(snapshot(week, pool, weights=NO_RANDOMNESS))

    assert plan.get(MO_D).dish_id == 2
    tuesday = plan.get(DI_L)
    assert (tuesday.kind, tuesday.leftover_source) == (AssignmentKind.LEFTOVER, MO_D)
    assert "einer isst allein" in tuesday.score.reasons()


def test_without_time_there_are_leftovers_even_if_it_takes_cooking_double():
    """"keine Zeit": dort wird nicht gekocht. Der Greedy-Planer ließ so eine Mahlzeit leer,
    weil er sie vor dem Vorabend füllte; der Optimierer kocht am Vorabend doppelt."""
    pool = [dish(1, "Chili", portions=2), dish(2, "Ratatouille", portions=3)]
    week = only(
        **{"0D": slot(0, Meal.DINNER), "1L": slot(1, Meal.LUNCH, time_budget=TimeBudget.NONE)}
    )
    snap = snapshot(week, pool, weights=NO_RANDOMNESS)

    assert propose_greedy(snap, {}).get(DI_L).is_empty
    plan = best_plan(snap)
    assert (plan.get(MO_D).dish_id, plan.get(MO_D).factor) == (1, 2)
    assert plan.get(DI_L).kind is AssignmentKind.LEFTOVER


def test_lunch_is_not_dinner_again_unless_there_is_no_time():
    pool = [dish(1, "Ratatouille", portions=3), dish(2, "Chili", portions=2)]
    lunch_alone = slot(2, Meal.LUNCH, eaters_home=1)

    normal = only(**{"2L": lunch_alone, "2D": slot(2, Meal.DINNER)})
    plan = best_plan(snapshot(normal, pool, weights=NO_RANDOMNESS))
    assert plan.get(MI_D).kind is AssignmentKind.DISH

    no_time = only(**{"2L": lunch_alone, "2D": slot(2, Meal.DINNER, time_budget=TimeBudget.NONE)})
    plan = best_plan(snapshot(no_time, pool, weights=NO_RANDOMNESS))
    assert plan.get(MI_D).leftover_source == MI_L


def test_one_pot_may_feed_two_leftover_meals_but_it_costs():
    """Verdoppelt: zu zweit am Montag, dann zweimal allein. Darf sein - die zweite
    Reste-Mahlzeit trägt aber einen Abzug, damit es nicht die Regel wird."""
    pool = [dish(1, "Chili", portions=2)]
    week = only(
        **{
            "0D": slot(0, Meal.DINNER),
            "1L": slot(1, Meal.LUNCH, eaters_home=1),
            "2L": slot(2, Meal.LUNCH, eaters_home=1),
        }
    )
    plan = best_plan(snapshot(week, pool, weights=NO_RANDOMNESS))

    assert plan.get(MO_D).factor == 2
    assert plan.get(DI_L).leftover_source == MO_D
    second = plan.get(MI_L)
    assert second.leftover_source == MO_D
    assert any(c.rule == "leftover_second_meal" for c in second.score.contributions)
    assert not any(c.rule == "leftover_second_meal" for c in plan.get(DI_L).score.contributions)


def test_pinned_meals_stay_and_others_plan_around_them():
    pool = [dish(1, "Chili", portions=2), dish(2, "Ratatouille", portions=3)]
    week = only(**{"0D": slot(0, Meal.DINNER), "1L": slot(1, Meal.LUNCH, eaters_home=1)})
    snap = snapshot(week, pool, weights=NO_RANDOMNESS)
    found = optimize(snap, {MO_D: Assignment.dish(1)}, seed=0)
    assert found is not None
    assert found.get(MO_D).dish_id == 1
    assert found.get(DI_L).dish_id == 2  # Chili ist schon da: Ratatouille, nicht doppelt


def test_contradicting_pins_give_no_plan_instead_of_a_wrong_one():
    """Reste aus einer Mahlzeit, in der nicht gekocht wird - der Planer nimmt dann den
    Greedy-Plan (planner.propose), statt einen kaputten zu liefern."""
    pool = [dish(1, "Chili", portions=2)]
    week = only(
        **{"0D": slot(0, Meal.DINNER, time_budget=TimeBudget.NONE), "1L": slot(1, Meal.LUNCH)}
    )
    snap = snapshot(week, pool, weights=NO_RANDOMNESS)
    assert optimize(snap, {DI_L: Assignment.leftover(MO_D, 1, 2)}, seed=0) is None



def test_what_cannot_be_reheated_is_cooked_where_it_comes_out_even():
    """Das Lieblingsgericht ist nicht aufwärmbar: es landet dort, wo drei Portionen
    gebraucht werden - nicht dort, wo eine übrig bliebe."""
    pool = [
        dish(1, "Knusper-Tofu", portions=3, reheatable=False, rating=5),
        dish(2, "Chili", portions=2),
        dish(3, "Ratatouille", portions=3),
    ]
    week = only(
        **{
            "0D": slot(0, Meal.DINNER),
            "1L": slot(1, Meal.LUNCH, eaters_home=1),
            "1D": slot(1, Meal.DINNER, packed_portions=1, packed_fresh=True),
        }
    )
    snap = snapshot(week, pool, weights=NO_RANDOMNESS)
    plan = best_plan(snap)
    assert plan.get(DI_D).dish_id == 1
    assert not [p for p in PortionLedger.of(plan, snap).wasted() if p.dish_id == 1]
