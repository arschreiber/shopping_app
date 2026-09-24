from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mealplan.domain.enums import Unit
from mealplan.domain.units import (
    Quantity,
    UnitError,
    aggregate,
    canonical_unit_for,
    format_quantity,
)


def q(amount, unit=Unit.G) -> Quantity:
    return Quantity(None if amount is None else Decimal(str(amount)), unit)


def test_converts_within_dimension():
    assert q(1.5, Unit.KG).to(Unit.G).amount == Decimal("1500")
    assert q(250, Unit.ML).to(Unit.L).amount == Decimal("0.25")


def test_rejects_dimension_change():
    """2 Zwiebeln vs. 150 g Zwiebeln wird abgelehnt, nicht geraten (Plan §8 Nr. 10)."""
    with pytest.raises(UnitError, match="verschiedene Dimensionen"):
        q(2, Unit.STUECK).to(Unit.G)


def test_open_quantity_stays_open():
    assert q(None).is_open
    assert (q(None) + q(None)).is_open


def test_open_plus_number_keeps_the_number():
    """"nach Bedarf" darf keine echte Menge verschlucken."""
    assert (q(None) + q(500)).amount == Decimal("500")
    assert (q(500) + q(None)).amount == Decimal("500")


def test_aggregate_normalises_units():
    total = aggregate([q(500, Unit.G), q(1, Unit.KG)], Unit.G)
    assert total.amount == Decimal("1500")


def test_canonical_unit_is_a_base_unit():
    assert canonical_unit_for(Unit.KG) is Unit.G
    assert canonical_unit_for(Unit.L) is Unit.ML
    assert canonical_unit_for(Unit.STUECK) is Unit.STUECK


@pytest.mark.parametrize(
    ("amount", "unit", "expected"),
    [
        (None, Unit.G, "nach Bedarf"),
        (500, Unit.G, "500 g"),
        (1500, Unit.G, "1,5 kg"),
        (2, Unit.STUECK, "2 Stk"),
        (1250, Unit.ML, "1,25 l"),
        ("0.5", Unit.KG, "0,5 kg"),
    ],
)
def test_format_quantity(amount, unit, expected):
    assert format_quantity(q(amount, unit)) == expected


@given(
    values=st.lists(
        st.decimals(min_value=0, max_value=10_000, places=2, allow_nan=False),
        min_size=1,
        max_size=20,
    )
)
def test_aggregation_is_order_independent(values):
    """Property: Aggregation ist kommutativ und verliert keine Menge."""
    quantities = [Quantity(v, Unit.G) for v in values]
    forward = aggregate(quantities, Unit.G)
    backward = aggregate(list(reversed(quantities)), Unit.G)
    assert forward.amount == backward.amount == sum(values)


@given(
    amount=st.decimals(min_value=0, max_value=10_000, places=3, allow_nan=False),
)
def test_conversion_roundtrips(amount):
    """Property: g -> kg -> g verliert nichts."""
    original = Quantity(amount, Unit.G)
    assert original.to(Unit.KG).to(Unit.G).amount == amount


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("250.000", "250"),
        ("0.500", "0.5"),
        ("350.00", "350"),
        ("1.250", "1.25"),
        ("0", "0"),
    ],
)
def test_trim_removes_trailing_zeros_without_exponents(value, expected):
    """Ohne das stehen "250.000" und "350.00" in den Eingabefeldern."""
    from mealplan.domain.units import trim

    assert str(trim(Decimal(value))) == expected


def test_trim_passes_none_through():
    from mealplan.domain.units import trim

    assert trim(None) is None
