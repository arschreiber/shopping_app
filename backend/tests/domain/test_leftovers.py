"""PortionLedger: Produktion, Haltbarkeit, Reste-Ketten (ARCHITECTURE.md §4)."""

from __future__ import annotations

import contextlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from conftest import dish, full_week, slot, snapshot
from mealplan.domain.enums import Meal
from mealplan.domain.leftovers import PortionLedger
from mealplan.domain.model import Assignment, Plan, SlotKey

MO_DINNER = SlotKey.of(0, Meal.DINNER)
DI_LUNCH = SlotKey.of(1, Meal.LUNCH)
DO_LUNCH = SlotKey.of(3, Meal.LUNCH)


def base_snap(**kwargs):
    return snapshot(full_week(), [dish(1, "Reispfanne"), dish(2, "Curry", portions=2)], **kwargs)


def test_three_portions_for_two_eaters_leaves_one():
    """Der Kernfall aus general_plan.md §4."""
    snap = base_snap()
    ledger = PortionLedger(snap)
    ledger.record_cook(MO_DINNER, 1, produced=3, needed=2)
    assert ledger.remaining(MO_DINNER) == 1

    pools = ledger.available_at(DI_LUNCH)
    assert [p.dish_id for p in pools] == [1]
    assert pools[0].portions == 1


def test_leftover_expires_after_shelf_life():
    snap = base_snap(leftover_shelf_life_days=2)
    ledger = PortionLedger(snap)
    ledger.record_cook(MO_DINNER, 1, produced=3, needed=2)
    assert ledger.available_at(DI_LUNCH)  # Tag +1: ok
    assert not ledger.available_at(DO_LUNCH)  # Tag +3: verfallen


def test_leftover_not_usable_in_the_same_or_an_earlier_slot():
    snap = base_snap()
    ledger = PortionLedger(snap)
    ledger.record_cook(MO_DINNER, 1, produced=3, needed=2)
    assert not ledger.available_at(MO_DINNER)
    assert not ledger.available_at(SlotKey.of(0, Meal.LUNCH))


def test_cannot_overdraw():
    snap = base_snap()
    ledger = PortionLedger(snap)
    ledger.record_cook(MO_DINNER, 1, produced=3, needed=2)
    ledger.record_leftover_use(MO_DINNER, 1)
    with pytest.raises(ValueError, match="nur 0 da"):
        ledger.record_leftover_use(MO_DINNER, 1)


def test_cooking_less_than_needed_is_an_error():
    snap = base_snap()
    ledger = PortionLedger(snap)
    with pytest.raises(ValueError, match="gebraucht"):
        ledger.record_cook(MO_DINNER, 2, produced=2, needed=3)


def test_doubled_two_portion_dish_covers_two_meals():
    """4 Portionen = zwei Esser heute + zwei Mitnehm-Portionen morgen."""
    snap = base_snap()
    ledger = PortionLedger(snap)
    ledger.record_cook(MO_DINNER, 2, produced=4, needed=2)
    pools = ledger.available_at(DI_LUNCH)
    assert pools[0].portions == 2


def test_of_reconstructs_a_finished_plan():
    snap = base_snap()
    plan = Plan().with_(MO_DINNER, Assignment.dish(1)).with_(
        DI_LUNCH, Assignment.leftover(MO_DINNER, 1, portions=1)
    )
    ledger = PortionLedger.of(plan, snap)
    assert ledger.remaining(MO_DINNER) == 0
    assert not ledger.wasted()


def test_a_single_portion_cannot_feed_a_two_eater_slot():
    """Eine Rest-Portion deckt keinen Slot mit zwei Essern - sie bleibt übrig."""
    snap = base_snap()  # alle Slots: 2 Esser
    assert PortionLedger(snap).would_waste(MO_DINNER, surplus=1) == 1


def test_a_single_portion_is_usable_when_a_later_slot_needs_exactly_one():
    """Home-Office-Mittag alleine: genau der Fall aus general_plan.md §4."""
    snap = snapshot(
        [slot(0, Meal.DINNER), slot(1, Meal.LUNCH, eaters_home=1)],
        [dish(1, "Reispfanne")],
    )
    assert PortionLedger(snap).would_waste(MO_DINNER, surplus=1) == 0


def test_surplus_beyond_the_shelf_life_is_waste():
    snap = snapshot(
        [slot(0, Meal.DINNER), slot(5, Meal.LUNCH, eaters_home=1)],  # Sa, zu spaet
        [dish(1, "Reispfanne")],
        leftover_shelf_life_days=2,
    )
    assert PortionLedger(snap).would_waste(MO_DINNER, surplus=1) == 1


@settings(max_examples=200)
@given(
    produced=st.integers(min_value=2, max_value=6),
    needed=st.integers(min_value=0, max_value=2),
    draws=st.lists(st.integers(min_value=1, max_value=3), max_size=4),
)
def test_ledger_never_goes_negative(produced, needed, draws):
    """Property: Entnahmen können den Bestand nie unter Null druecken."""
    snap = base_snap()
    ledger = PortionLedger(snap)
    if produced < needed:
        return
    ledger.record_cook(MO_DINNER, 1, produced=produced, needed=needed)
    for amount in draws:
        with contextlib.suppress(ValueError):
            ledger.record_leftover_use(MO_DINNER, amount)
        assert ledger.remaining(MO_DINNER) >= 0
    assert ledger.remaining(MO_DINNER) <= produced - needed


@given(shelf_life=st.integers(min_value=0, max_value=6), day=st.integers(min_value=0, max_value=6))
def test_availability_respects_shelf_life(shelf_life, day):
    """Property: nie ueber die Haltbarkeit hinaus, nie rueckwaerts in der Zeit."""
    snap = base_snap(leftover_shelf_life_days=shelf_life)
    ledger = PortionLedger(snap)
    source = SlotKey.of(0, Meal.LUNCH)
    ledger.record_cook(source, 1, produced=3, needed=0)
    for meal in (Meal.LUNCH, Meal.DINNER):
        target = SlotKey.of(day, meal)
        available = any(p.source == source for p in ledger.available_at(target))
        expected = target.index > source.index and day <= shelf_life
        assert available is expected
