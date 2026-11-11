"""Beilage und Protein aus den Zutaten (domain/dish_roles.py).

Die Fälle stammen aus dem echten Gerichtebestand - genau die, an denen eine naive Regel
("nimm die Zutat mit dem meisten Protein") falsch läge.
"""

from __future__ import annotations

from decimal import Decimal as D

from mealplan.domain.dish_roles import (
    LearnDish,
    RoleLine,
    detect_roles,
    learn_roles,
    name_matches,
    proposed_category,
)
from mealplan.domain.enums import CategoryAxis

SIDE, PROTEIN = CategoryAxis.SIDE, CategoryAxis.PROTEIN


def line(article_id, name, carbs, protein, carbs_density=None, protein_density=None):
    """Gramm im Gericht; Dichte je 100 g (None = Stück-Artikel)."""
    return RoleLine(
        article_id=article_id,
        name=name,
        carbs_g=D(str(carbs)),
        protein_g=D(str(protein)),
        carbs_density=None if carbs_density is None else D(str(carbs_density)),
        protein_density=None if protein_density is None else D(str(protein_density)),
    )


REIS = line(1, "Reis", 203, 18.5, 81.3, 7.4)
LINSEN = line(2, "Rote Linsen", 57, 24, 57, 24)  # 100 g
HIRTEN = line(3, "Hirtenkäse Light", 1.5, 55, 0.6, 22)
RAEUCHERTOFU = line(4, "Räuchertofu", 3.5, 31.5, 2, 18)
WRAPS = line(5, "Proteinwraps", 46, 22, 38.5, 18.4)
KIDNEY = line(6, "Kidneybohnen", 39, 19, 15.3, 7.5)
TOMATEN = line(7, "Passierte Tomaten", 40, 13, 4, 1.3)
SOJA = line(8, "Sojaschnetzel", 40, 73.5, 27, 49)
LACHS = line(9, "Wildlachs", 0, 100, 0, 20)
LASAGNE = line(10, "Lasagneplatten", 107, 20, 71.3, 13.3)
HIRSE = line(11, "Hirse", 173, 26, 69, 10.5)
ZUCCHINI = line(12, "Zucchini", 6, 4, 2, 1.3)

HISTORY = [
    LearnDish({SIDE: "Reis", PROTEIN: "Hirtenkäse"}, (REIS, HIRTEN, RAEUCHERTOFU)),
    LearnDish({SIDE: "Wraps", PROTEIN: "Bohnen"}, (WRAPS, KIDNEY)),
    LearnDish({PROTEIN: "Sojaschnetzel"}, (SOJA, KIDNEY, TOMATEN)),
    LearnDish({SIDE: "Reis", PROTEIN: "Fisch"}, (REIS, LACHS)),
    LearnDish({SIDE: "Nudeln", PROTEIN: "Linsen"}, (LASAGNE, LINSEN, TOMATEN)),
]
EXISTING = {
    SIDE: ["Reis", "Wraps", "Nudeln", "Couscous"],
    PROTEIN: ["Hirtenkäse", "Bohnen", "Sojaschnetzel", "Fisch", "Linsen", "Tofu"],
}


def test_learns_by_name_first_then_by_amount():
    roles = learn_roles(HISTORY)
    assert roles[SIDE] == {1: "Reis", 5: "Wraps", 10: "Nudeln"}
    # Hirtenkäse Light über den Namen, Wildlachs über die Menge, Räuchertofu gar nicht:
    # im Reisgericht war Hirtenkäse das Protein.
    assert roles[PROTEIN][3] == "Hirtenkäse"
    assert roles[PROTEIN][9] == "Fisch"
    assert roles[PROTEIN][2] == "Linsen"
    assert 4 not in roles[PROTEIN]


def test_side_ingredient_never_counts_as_protein():
    """Burritos: der Proteinwrap hat mehr Protein als die Bohnen, ist aber die Beilage."""
    roles = learn_roles(HISTORY)
    assert roles[PROTEIN][6] == "Bohnen"
    assert 5 not in roles[PROTEIN]

    result = detect_roles([WRAPS, KIDNEY], roles, EXISTING)
    assert result[SIDE].category == "Wraps"
    assert result[PROTEIN].category == "Bohnen"
    assert next(c for c in result[PROTEIN].candidates if c.article_id == 5).is_side


def test_largest_known_role_wins():
    """Spinat-Hirtenkäse: Hirtenkäse (55 g) schlägt Räuchertofu (31,5 g)."""
    roles = {SIDE: {1: "Reis"}, PROTEIN: {3: "Hirtenkäse", 4: "Tofu"}}
    result = detect_roles([RAEUCHERTOFU, HIRTEN, REIS], roles, EXISTING)
    assert result[SIDE].category == "Reis"
    assert result[SIDE].source.grams == D("203")
    assert result[PROTEIN].category == "Hirtenkäse"
    assert [c.name for c in result[PROTEIN].candidates][:2] == ["Hirtenkäse Light", "Räuchertofu"]


def test_dish_without_side_stays_without_side():
    """Chili: keine Zutat ist Beilage, und Tomaten oder Bohnen werden auch keine."""
    roles = learn_roles(HISTORY)
    result = detect_roles([SOJA, KIDNEY, TOMATEN], roles, EXISTING)
    assert result[SIDE].category is None
    assert result[SIDE].suggestion is None
    assert result[PROTEIN].category == "Sojaschnetzel"


def test_unknown_starch_is_suggested_not_set():
    roles = learn_roles(HISTORY)
    result = detect_roles([HIRSE, HIRTEN, ZUCCHINI], roles, EXISTING)
    assert result[SIDE].category is None
    assert result[SIDE].suggestion is not None
    assert result[SIDE].suggestion.name == "Hirse"
    assert result[SIDE].suggestion.category == "Hirse"
    # Hirse ist (vorgeschlagene) Beilage - ihr Protein zählt nicht gegen den Hirtenkäse.
    assert result[PROTEIN].category == "Hirtenkäse"


def test_role_on_other_axis_is_not_suggested():
    """Rote Linsen sind Protein - ohne Lasagneplatten werden sie nicht zur Beilage."""
    roles = learn_roles(HISTORY)
    result = detect_roles([LINSEN, TOMATEN], roles, EXISTING)
    assert result[SIDE].suggestion is None
    assert result[PROTEIN].category == "Linsen"


def test_known_role_counts_without_nutrition():
    """Ein Artikel ohne Nährwerte behält seine gelernte Rolle."""
    bare_rice = line(1, "Reis", 0, 0)
    result = detect_roles([bare_rice, HIRTEN], {SIDE: {1: "Reis"}, PROTEIN: {}}, EXISTING)
    assert result[SIDE].category == "Reis"


def test_proposed_names_reuse_existing_categories():
    assert proposed_category("Rote Linsen", EXISTING[PROTEIN]) == "Linsen"
    assert proposed_category("Hirtenkäse Light", EXISTING[PROTEIN]) == "Hirtenkäse"
    assert proposed_category("Vollkornnudeln", ["Nudeln", "Mie-Nudeln"]) == "Nudeln"
    assert proposed_category("Nudeln", ["Mie-Nudeln", "Nudeln"]) == "Nudeln"
    assert proposed_category("Hirse", EXISTING[SIDE]) == "Hirse"


def test_short_names_only_match_exactly():
    assert not name_matches("Ei", "Weizenmehl")
    assert name_matches("Kartoffeln", "Kartoffel")
    assert not name_matches("Proteinpulver", "Protein Grillkäse")
