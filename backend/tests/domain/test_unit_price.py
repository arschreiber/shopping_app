"""Grundpreise vergleichbar machen - die Grundlage für den Richtpreis pro Artikel."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mealplan.domain.enums import Unit
from mealplan.domain.unit_price import (
    Quantity,
    UnitPrice,
    comparable,
    compare,
    from_pack,
    in_article_unit,
    offer_quantity,
    pack_quantity,
    pack_unit_price,
    parse_base_price,
    pieces,
    unit_price,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5,08 €/kg", UnitPrice(Decimal("5.08"), "kg")),
        ("0,85 €/l", UnitPrice(Decimal("0.85"), "l")),
        ("0,89 €/100 g", UnitPrice(Decimal("8.90"), "kg")),
        ("1,19 € / 100 ml", UnitPrice(Decimal("11.90"), "l")),
        ("0,25 €/Stück", UnitPrice(Decimal("0.25"), "Stück")),
        ("16,23 €/kg", UnitPrice(Decimal("16.23"), "kg")),
    ],
)
def test_the_sources_base_price_is_read(text, expected):
    assert parse_base_price(text) == expected


@pytest.mark.parametrize("text", ["", None, "0,50 €/Portion", "1,20 €/Blatt", "lecker"])
def test_what_says_nothing_about_weight_stays_open(text):
    assert parse_base_price(text) is None


@pytest.mark.parametrize(
    ("price", "pack", "expected"),
    [
        ("1.49", "250 g", UnitPrice(Decimal("5.96"), "kg")),
        ("1.99", "1 kg", UnitPrice(Decimal("1.99"), "kg")),
        ("1.49", "1,75 l", UnitPrice(Decimal("0.85"), "l")),
        ("5.99", "6 × 330 ml", UnitPrice(Decimal("3.03"), "l")),
        ("2.49", "4 x 125 g", UnitPrice(Decimal("4.98"), "kg")),
        ("1.29", "680 g / 650 g", UnitPrice(Decimal("1.90"), "kg")),
        ("1.29", "1,5 Liter", UnitPrice(Decimal("0.86"), "l")),
        ("0.99", "3 Stück", UnitPrice(Decimal("0.33"), "Stück")),
    ],
)
def test_without_a_base_price_it_comes_from_the_pack(price, pack, expected):
    assert from_pack(Decimal(price), pack) == expected


def test_the_sources_figure_wins_over_the_pack():
    """Die Quelle kennt das Abtropfgewicht besser als unsere Packungs-Regel."""
    assert unit_price(Decimal("1.29"), "1,98 €/kg", "680 g / 650 g").value == Decimal("1.98")
    assert unit_price(Decimal("1.49"), "", "250 g").value == Decimal("5.96")
    assert unit_price(Decimal("1.49"), None, None) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2er-Schale", 2),
        ("Genussreif; Klasse 1; Ursprung siehe Etikett · 2er-Schale", 2),
        ("3er Netz", 3),
        ("6er-Packung", 6),
        ("Klasse 1; Deutschland · Stück", 1),
        ("Stück/Packung", 1),
        ("Kl. II , je St.", 1),
        ("Junior, Größe 5 , je 39 St.-Pckg.", 39),
        ("4 Stück", 4),
    ],
)
def test_the_number_of_pieces_is_read(text, expected):
    assert pieces(text) == expected


@pytest.mark.parametrize(
    "text",
    [None, "", "1-kg-Beutel", "ca. 33 cm hoch; 1.000 Teile", "St. Moritz Raclette",
     "verschiedene 2er-Sets", "Stückige Tomaten", "je Topf"],
)
def test_what_names_no_pieces_stays_open(text):
    assert pieces(text) is None


def test_an_offer_of_pieces_has_a_price_per_piece():
    """Aldi: "Avocados 1,29 €", die Schale steht nur im Text -> 0,65 €/Stück, bei
    1 Avocado ≈ 150 g also ≈ 4,33 €/kg."""
    price = unit_price(Decimal("1.29"), None, None, "Klasse 1 · 2er-Schale")
    assert price == UnitPrice(Decimal("0.65"), "Stück")
    assert compare(price, Unit.G, Decimal("150")).value == Decimal("4.33")
    assert unit_price(Decimal("1.11"), None, "Stück") == UnitPrice(Decimal("1.11"), "Stück")


def test_weight_wins_over_pieces_and_the_text_gives_no_weights():
    assert unit_price(Decimal("2.49"), None, "250 g", "3er-Schale").unit == "kg"
    assert unit_price(Decimal("2.49"), None, None, "ca. 250 g") is None


def test_a_price_compares_only_in_the_articles_own_unit():
    per_kg = UnitPrice(Decimal("5.96"), "kg")
    assert comparable(per_kg, Unit.G) == Decimal("5.96")
    assert comparable(per_kg, Unit.ML) is None
    assert comparable(UnitPrice(Decimal("0.25"), "Stück"), Unit.STUECK) == Decimal("0.25")
    assert comparable(None, Unit.G) is None


@pytest.mark.parametrize(
    ("amount", "price", "unit", "expected"),
    [
        ("250", "1.29", Unit.G, "5.16"),  # 250 g für 1,29 € -> 5,16 €/kg
        ("1000", "1.99", Unit.G, "1.99"),
        ("400", "0.99", Unit.ML, "2.48"),  # 400 ml Kokosmilch -> €/l
        ("6", "1.79", Unit.STUECK, "0.30"),  # 6 Eier -> €/Stück
    ],
)
def test_a_pack_becomes_a_unit_price(amount, price, unit, expected):
    assert pack_unit_price(Decimal(amount), Decimal(price), unit) == Decimal(expected)


def test_an_incomplete_pack_has_no_unit_price():
    assert pack_unit_price(None, Decimal("1.29"), Unit.G) is None
    assert pack_unit_price(Decimal("250"), None, Unit.G) is None
    assert pack_unit_price(Decimal("0"), Decimal("1.29"), Unit.G) is None


def test_a_piece_price_becomes_a_kg_price_through_the_piece_size():
    """Avocado 0,99 €/Stück, 1 Stück ≈ 200 g -> 4,95 €/kg - als Schätzung markiert."""
    per_piece = UnitPrice(Decimal("0.99"), "Stück")
    compared = compare(per_piece, Unit.G, Decimal("200"))
    assert (compared.value, compared.via_piece) == (Decimal("4.95"), True)
    assert compare(per_piece, Unit.G) is None, "ohne Stückgewicht wird nicht geraten"
    assert compare(per_piece, Unit.ML, Decimal("400")).value == Decimal("2.48")
    assert compare(UnitPrice(Decimal("4.95"), "kg"), Unit.G, Decimal("200")).via_piece is False


def test_a_normal_price_can_be_entered_per_piece():
    """ "1 Stück für 0,79 €" bei 1 Stück ≈ 200 g -> 3,95 €/kg."""
    assert pack_unit_price(
        Decimal("1"), Decimal("0.79"), Unit.G, in_pieces=True, piece_size=Decimal("200")
    ) == Decimal("3.95")
    assert pack_unit_price(Decimal("1"), Decimal("0.79"), Unit.G, in_pieces=True) is None
    assert pack_unit_price(Decimal("4"), Decimal("2.00"), Unit.STUECK, in_pieces=True) == Decimal(
        "0.50"
    )


@pytest.mark.parametrize(
    ("pack", "expected"),
    [
        ("250 g", Quantity(Decimal("0.250"), "kg")),
        ("6 × 330 ml", Quantity(Decimal("1.980"), "l")),
        ("1,5 kg", Quantity(Decimal("1.5"), "kg")),
        ("3 Stück", Quantity(Decimal("3"), "Stück")),
        ("2er-Schale", None),
        (None, None),
    ],
)
def test_a_pack_has_a_size(pack, expected):
    assert pack_quantity(pack) == expected


def test_an_offer_knows_how_much_it_is():
    """Packung zuerst, dann die Stückzahl, zuletzt Preis durch Grundpreis."""
    assert offer_quantity(Decimal("3.33"), None, "200 g") == Quantity(Decimal("0.200"), "kg")
    assert offer_quantity(Decimal("1.29"), None, None, "Klasse 1 · 2er-Schale") == Quantity(
        Decimal("2"), "Stück"
    )
    per_kg = UnitPrice(Decimal("13.30"), "kg")
    assert offer_quantity(Decimal("3.99"), per_kg, None).amount == Decimal("0.300")
    # Netto: 2,29 € bei 1,53 €/kg - gerundet sind das 1,4967 kg, gemeint 1,5
    assert offer_quantity(Decimal("2.29"), UnitPrice(Decimal("1.53"), "kg"), None).amount == (
        Decimal("1.50")
    )
    assert offer_quantity(Decimal("2.99"), None, None) is None


def test_the_size_is_counted_in_the_articles_unit():
    assert in_article_unit(Quantity(Decimal("0.3"), "kg"), Unit.G) == Decimal("300")
    assert in_article_unit(Quantity(Decimal("1.25"), "l"), Unit.ML) == Decimal("1250")
    two = Quantity(Decimal("2"), "Stück")
    assert in_article_unit(two, Unit.G, Decimal("150")) == Decimal("300")
    assert in_article_unit(two, Unit.G) is None, "ohne Stückgewicht keine Grammzahl"
    assert in_article_unit(two, Unit.STUECK) == Decimal("2")
    assert in_article_unit(Quantity(Decimal("0.3"), "kg"), Unit.ML) is None
