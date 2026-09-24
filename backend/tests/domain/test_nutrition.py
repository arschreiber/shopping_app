"""Nährwerte je Portion - und vor allem: Lücken werden gemeldet."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mealplan.domain.enums import Unit
from mealplan.domain.model import IngredientSpec
from mealplan.domain.nutrition import (
    ArticleNutrition,
    Nutrients,
    article_nutrition,
    dish_nutrition,
)

REIS, OEL, ZUCCHINI, SALZ, UNBEKANNT = 1, 2, 3, 4, 5

# je 100 g / 100 ml / Stück
def facts(article_id: int, unit: Unit, *values: int) -> ArticleNutrition:
    return ArticleNutrition(article_id, unit, Nutrients(*(Decimal(v) for v in values)))


FACTS = {
    REIS: facts(REIS, Unit.G, 350, 7, 78, 1),
    OEL: facts(OEL, Unit.ML, 900, 0, 0, 100),
    ZUCCHINI: facts(ZUCCHINI, Unit.STUECK, 40, 3, 6, 1),
    SALZ: ArticleNutrition(SALZ, Unit.G, Nutrients()),
}


def line(article_id: int, quantity, unit: Unit) -> IngredientSpec:
    return IngredientSpec(
        article_id=article_id,
        quantity=None if quantity is None else Decimal(str(quantity)),
        unit=unit,
    )


def test_sums_ingredients_and_divides_by_portions():
    result = dish_nutrition(
        [line(REIS, 200, Unit.G), line(OEL, 20, Unit.ML)], FACTS, portions=2
    )
    # 200 g Reis = 700 kcal, 20 ml Öl = 180 kcal -> 880 gesamt, 440 je Portion
    assert result.total.kcal == Decimal(880)
    assert result.per_portion.kcal == Decimal(440)
    assert result.per_portion.protein_g == Decimal("7.0")
    assert result.is_complete


def test_piece_articles_use_a_per_piece_basis():
    """Kein Umweg über ein Stückgewicht - eine Zucchini trägt ihre Werte je Stück."""
    result = dish_nutrition([line(ZUCCHINI, 2, Unit.STUECK)], FACTS, portions=2)
    assert result.total.kcal == Decimal(80)


def test_kilograms_are_converted_before_counting():
    result = dish_nutrition([line(REIS, 1, Unit.KG)], FACTS, portions=2)
    assert result.total.kcal == Decimal(3500)


def test_a_missing_article_is_a_reported_gap_not_a_zero():
    result = dish_nutrition(
        [line(REIS, 100, Unit.G), line(UNBEKANNT, 200, Unit.G)], FACTS, portions=2
    )
    assert result.missing_data_ids == (UNBEKANNT,)
    assert not result.is_complete
    assert result.total.kcal == Decimal(350), "das Bekannte wird trotzdem gezählt"


def test_an_open_quantity_is_a_gap_when_the_article_has_calories():
    """"Olivenöl nach Bedarf" heißt: die Kalorien sind unbekannt."""
    result = dish_nutrition(
        [line(REIS, 100, Unit.G), line(OEL, None, Unit.ML)], FACTS, portions=2
    )
    assert result.open_quantity_ids == (OEL,)
    assert not result.is_complete


def test_an_open_quantity_of_a_zero_article_is_no_gap():
    """Salz ohne Menge ändert an der Summe nichts - das ist keine Lücke."""
    result = dish_nutrition(
        [line(REIS, 100, Unit.G), line(SALZ, None, Unit.G)], FACTS, portions=2
    )
    assert result.open_quantity_ids == ()
    assert result.is_complete


def test_doubling_does_not_change_the_value_per_portion():
    """Doppelte Menge auf doppelte Portionen - je Portion bleibt es gleich."""
    single = dish_nutrition([line(REIS, 200, Unit.G)], FACTS, portions=2)
    doubled = dish_nutrition([line(REIS, 400, Unit.G)], FACTS, portions=4)
    assert single.per_portion == doubled.per_portion


def test_a_dish_without_ingredients_is_not_complete():
    result = dish_nutrition([], FACTS, portions=2)
    assert not result.has_any
    assert not result.is_complete
    assert result.per_portion.kcal == Decimal(0)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ((None, None, None, None), None),
        ((Decimal(350), None, None, None), Decimal(350)),
    ],
)
def test_article_without_any_value_stays_unknown(values, expected):
    facts = article_nutrition(
        REIS, Unit.G, kcal=values[0], protein_g=values[1], carbs_g=values[2], fat_g=values[3]
    )
    if expected is None:
        assert facts is None
    else:
        assert facts is not None
        assert facts.per_basis.kcal == expected
        assert facts.per_basis.protein_g == Decimal(0)


@given(
    grams=st.decimals(min_value=0, max_value=5000, places=1, allow_nan=False),
    portions=st.integers(min_value=2, max_value=3),
)
def test_property_per_portion_times_portions_is_the_total(grams, portions):
    result = dish_nutrition([line(REIS, grams, Unit.G)], FACTS, portions=portions)
    reconstructed = result.per_portion.kcal * portions
    # Rundung je Portion erlaubt eine kleine Abweichung, aber keine systematische.
    assert abs(reconstructed - result.total.kcal) <= portions


@given(grams=st.decimals(min_value=0, max_value=5000, places=1, allow_nan=False))
def test_property_scaling_is_linear(grams):
    """Doppelte Menge, doppelter Wert - bis auf die Anzeige-Rundung auf ganze kcal.

    Die Summe wird für die Anzeige gerundet; bei 0,1 g Reis (0,35 kcal) entscheidet
    dann die Rundung, nicht die Rechnung. Die Invariante gilt also mit genau dieser
    Toleranz, und das ist die ehrliche Formulierung.
    """
    single = dish_nutrition([line(REIS, grams, Unit.G)], FACTS, portions=2)
    double = dish_nutrition([line(REIS, grams * 2, Unit.G)], FACTS, portions=2)
    assert abs(double.total.kcal - single.total.kcal * 2) <= 1
