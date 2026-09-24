"""Der Parser entscheidet ueber Phase 0 - darum ausfuehrlich getestet."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mealplan.domain.enums import Unit
from mealplan.services.ingredient_parsing import parse_line, parse_lines

ARTICLES = {
    1: ["Basmatireis", "Reis"],
    2: ["Hirtenkäse", "Feta", "Schafskäse"],
    3: ["Zucchini"],
    4: ["Olivenöl"],
    5: ["Kichererbsen"],
}


@pytest.mark.parametrize(
    ("line", "quantity", "unit", "name"),
    [
        ("250 g Basmatireis", Decimal("250"), Unit.G, "Basmatireis"),
        ("1,5 kg Kartoffeln", Decimal("1500"), Unit.G, "Kartoffeln"),
        ("500ml Brühe", Decimal("500"), Unit.ML, "Brühe"),
        ("1 l Milch", Decimal("1000"), Unit.ML, "Milch"),
        ("1 Zucchini", Decimal("1"), Unit.STUECK, "Zucchini"),
        ("2 Dosen Kichererbsen", Decimal("2"), Unit.STUECK, "Kichererbsen"),
        ("3 Zehen Knoblauch", Decimal("3"), Unit.STUECK, "Knoblauch"),
        ("2 EL Olivenöl", Decimal("30"), Unit.ML, "Olivenöl"),
        ("1/2 Packung Hirtenkäse", Decimal("0.5"), Unit.STUECK, "Hirtenkäse"),
        ("½ Zitrone", Decimal("0.5"), Unit.STUECK, "Zitrone"),
        ("Hirtenkäse 200g", Decimal("200"), Unit.G, "Hirtenkäse"),
        ("200 gr Feta", Decimal("200"), Unit.G, "Feta"),
    ],
)
def test_parses_common_lines(line, quantity, unit, name):
    parsed = parse_line(line)
    assert parsed.quantity == quantity
    assert parsed.unit is unit
    assert parsed.name == name


@pytest.mark.parametrize(
    "line",
    ["Salz", "Olivenöl nach Bedarf", "Pfeffer nach Geschmack", "etwas Petersilie"],
)
def test_lines_without_a_quantity_stay_open(line):
    """"nach Bedarf" ist eine gueltige Menge (Plan §8 Nr. 10)."""
    parsed = parse_line(line)
    assert parsed.quantity is None


def test_open_marker_is_stripped_from_the_name():
    parsed = parse_line("Olivenöl nach Bedarf")
    assert parsed.name == "Olivenöl"
    assert parsed.note == "nach bedarf"


def test_matches_a_known_article_by_alias():
    parsed = parse_line("200 g Feta", ARTICLES)
    assert parsed.article_id == 2
    assert parsed.article_name == "Hirtenkäse"
    assert parsed.confidence >= 80


def test_unknown_article_is_flagged_for_creation():
    parsed = parse_line("300 g Rinderhack", ARTICLES)
    assert parsed.is_new_article
    assert parsed.name == "Rinderhack"


def test_parses_a_whole_block_and_ignores_bullets():
    block = """
    250 g Basmatireis
    - 200 g Hirtenkäse
    • 1 Zucchini

    Salz
    """
    parsed = parse_lines(block, ARTICLES)
    assert [p.name for p in parsed] == [
        "Basmatireis", "Hirtenkäse", "Zucchini", "Salz"
    ]
    assert [p.article_id for p in parsed] == [1, 2, 3, None]


def test_quick_entry_example_from_the_plan():
    """Die Beispielzeile aus general_plan.md §5 Phase 0."""
    parsed = parse_lines("250 g Basmatireis\n200 g Hirtenkäse\n1 Zucchini", ARTICLES)
    assert [(p.quantity, p.unit.value) for p in parsed] == [
        (Decimal("250"), "G"),
        (Decimal("200"), "G"),
        (Decimal("1"), "STUECK"),
    ]
