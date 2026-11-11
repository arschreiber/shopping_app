"""Mikronährstoffe eines Gerichts aus BLS-Werten (domain/micronutrients.py)."""

from __future__ import annotations

from decimal import Decimal

from mealplan.domain.enums import Unit
from mealplan.domain.micronutrients import (
    ArticleMicros,
    dish_micronutrients,
    macros_from_bls,
)
from mealplan.domain.model import IngredientSpec

D = Decimal

# je 100 g, grob wie im BLS
SPINACH = {"FE": D("3.6"), "VITC": D(50), "CA": D(117), "ENERCC": D(23)}
RICE = {"FE": D("0.8"), "VITC": D(0), "CA": D(6), "ENERCC": D(351), "PROT625": D(8)}
OIL = {"VITE": D(17), "ENERCC": D(900), "FAT": D(100)}


def line(article_id: int, quantity: str | None, unit: Unit = Unit.G) -> IngredientSpec:
    return IngredientSpec(article_id, D(quantity) if quantity else None, unit)


def test_sums_per_portion_and_shares_of_the_daily_value():
    facts = {
        1: ArticleMicros(1, Unit.G, SPINACH),
        2: ArticleMicros(2, Unit.G, RICE),
    }
    result = dish_micronutrients(
        [line(1, "300"), line(2, "200")], facts, portions=2
    )
    iron = result.get("FE")
    # (3,6·3 + 0,8·2) / 2 = 6,2 mg je Portion; Referenz 11 mg -> 56 %
    assert iron.amount == D("6.2")
    assert iron.share == D(56)
    assert result.get("VITC").amount == D(75)
    assert result.is_complete


def test_kilograms_are_converted_through_the_article_unit():
    facts = {1: ArticleMicros(1, Unit.G, SPINACH)}
    result = dish_micronutrients([line(1, "0.5", Unit.KG)], facts, portions=1)
    assert result.get("FE").amount == D(18)


def test_millilitres_use_the_density_and_default_to_one():
    oil = {1: ArticleMicros(1, Unit.ML, OIL, grams_per_unit=D("0.92"))}
    result = dish_micronutrients([line(1, "100", Unit.ML)], oil, portions=1)
    assert result.get("VITE").amount == D("15.6")  # 17 · 0,92

    milk = {1: ArticleMicros(1, Unit.ML, {"CA": D(120)})}
    assert dish_micronutrients([line(1, "250", Unit.ML)], milk, portions=1).get(
        "CA"
    ).amount == D(300)


def test_pieces_need_a_piece_weight_or_they_are_a_gap():
    without = {1: ArticleMicros(1, Unit.STUECK, SPINACH)}
    result = dish_micronutrients([line(1, "2", Unit.STUECK)], without, portions=1)
    assert result.open_quantity_ids == (1,)
    assert not result.has_any

    with_weight = {1: ArticleMicros(1, Unit.STUECK, SPINACH, grams_per_unit=D(50))}
    result = dish_micronutrients([line(1, "2", Unit.STUECK)], with_weight, portions=1)
    assert result.get("FE").amount == D("3.6")


def test_gaps_are_listed_separately():
    facts = {1: ArticleMicros(1, Unit.G, SPINACH)}
    result = dish_micronutrients(
        [line(1, "100"), line(2, "50"), line(3, "30"), line(1, None)],
        facts,
        skipped={3},
        portions=1,
    )
    assert result.counted_ids == (1,)
    assert result.missing_ids == (2,)
    assert result.skipped_ids == (3,)
    assert result.open_quantity_ids == (1,)
    assert not result.is_complete


def test_unknown_values_mark_the_nutrient_as_partial():
    facts = {
        1: ArticleMicros(1, Unit.G, SPINACH),
        2: ArticleMicros(2, Unit.G, OIL),  # kein Eisen-Wert
    }
    result = dish_micronutrients([line(1, "100"), line(2, "10")], facts, portions=1)
    assert result.get("FE").partial is True
    assert result.get("VITE").partial is True  # Spinat ohne Vitamin-E-Wert
    assert result.get("FE").amount == D("3.6")


def test_nothing_counted_means_no_values():
    result = dish_micronutrients([line(9, "100")], {}, portions=1)
    assert result.per_portion == ()
    assert result.get("FE") is None


def test_macros_from_bls_follow_the_article_basis():
    grams = macros_from_bls(ArticleMicros(1, Unit.G, RICE))
    assert grams.kcal == D(351)
    assert grams.protein_g == D(8)

    oil = macros_from_bls(ArticleMicros(1, Unit.ML, OIL, grams_per_unit=D("0.92")))
    assert oil.fat_g == D("92.00")

    piece = macros_from_bls(ArticleMicros(1, Unit.STUECK, RICE, grams_per_unit=D(60)))
    assert piece.kcal == D("210.6")
    assert macros_from_bls(ArticleMicros(1, Unit.STUECK, RICE)) is None


# ------------------------------------------------------------------ Etikett vor BLS


def test_label_values_win_per_nutrient_and_fill_the_rest_from_bls():
    # Spinat mit "Etikett": nur Eisen genannt, Vitamin C kommt weiter aus dem BLS
    facts = {1: ArticleMicros(1, Unit.G, SPINACH, label={"FE": D(10)})}
    result = dish_micronutrients([line(1, "200")], facts, portions=1)
    assert result.get("FE").amount == D(20)
    assert result.get("VITC").amount == D(100)


def test_label_alone_counts_without_bls_reference():
    whey = {"CA": D(1000), "VITB6": D(2), "MG": D(313)}  # je 100 g, Anzeigeeinheit
    facts = {1: ArticleMicros(1, Unit.G, {}, label=whey)}
    result = dish_micronutrients([line(1, "30")], facts, skipped={1}, portions=1)
    assert result.counted_ids == (1,)
    assert result.skipped_ids == ()
    assert result.get("CA").amount == D(300)
    assert result.get("VITB6").amount == D("0.60")  # mg, nicht durch die BLS-Skala
    assert result.get("FE").partial is True  # nicht auf dem Etikett, kein BLS


def test_label_on_pieces_needs_no_piece_weight():
    facts = {1: ArticleMicros(1, Unit.STUECK, SPINACH, label={"VITC": D(30)})}
    result = dish_micronutrients([line(1, "2", Unit.STUECK)], facts, portions=1)
    assert result.get("VITC").amount == D(60)
    assert result.get("FE").partial is True  # BLS-Wert ohne Stückgewicht nicht nutzbar


def test_folic_acid_becomes_folate_equivalents():
    from mealplan.domain.micronutrients import effective_label

    assert effective_label({"FOLAC": D(200)}) == {"FOL": D("340.0")}
    assert effective_label({"FOL": D(10), "FOLAC": D(100)}) == {"FOL": D("180.0")}


def test_article_profile_per_basis_with_sources():
    from mealplan.domain.micronutrients import article_profile

    oil = ArticleMicros(1, Unit.ML, OIL, grams_per_unit=D("0.92"), label={"VITC": D(5)})
    profile = {v.code: v for v in article_profile(oil)}
    assert profile["VITE"].amount == D("15.6")  # je 100 ml = 92 g
    assert profile["VITE"].source == "bls"
    assert profile["VITC"].source == "label"
    assert "FE" not in profile  # keine Quelle kennt ihn

    piece = ArticleMicros(2, Unit.STUECK, SPINACH, label={"CA": D(40)})
    assert [v.code for v in article_profile(piece)] == ["CA"]  # BLS braucht Stückgewicht
