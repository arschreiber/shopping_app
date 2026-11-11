"""Artikel -> BLS-Vorschläge (matching/bls.py).

Die Namen sind echte BLS-4.0-Einträge - die Fälle, an denen ein reiner Fuzzy-Score
scheitert: andere Wörter (Broccoli, Porree), Komposita (Speisezwiebel), und die
kurzen Gerichtnamen, die sonst vorne landen.
"""

from __future__ import annotations

from mealplan.matching.bls import FoodName, search, suggest

FOODS = [
    FoodName("G312100", "Broccoli roh"),
    FoodName("G312132", "Broccoli gekocht"),
    FoodName("G470100", "Porree/Lauch, roh"),
    FoodName("X547053", "Lauch/Porree, gedünstet, mit Bechamelsauce"),
    FoodName("G480100", "Speisezwiebel roh"),
    FoodName("X548443", "Zwiebeln überbacken"),
    FoodName("G620100", "Karotte/Möhre, roh"),
    FoodName("D4A8400", "Möhren-Nuss-Kuchen (Rührmasse)"),
    FoodName("C133000", "Hafer Flocken"),
    FoodName("D701700", "Haferflocken-Nussplätzchen"),
    FoodName("H861000", "Tofu"),
    FoodName("C352000", "Reis poliert, roh"),
    FoodName("X820162", "Reis gekocht"),
    FoodName("H800000", "Mandeldrink ungesüßt"),
]


def top(*names: str) -> str:
    return suggest(list(names), FOODS)[0].code


def test_synonyms_and_slash_names():
    assert top("Brokkoli") == "G312100"
    assert top("Lauch") == "G470100"
    assert top("Möhren") == "G620100"
    assert top("Mandelmilch") == "H800000"


def test_raw_beats_prepared_and_dishes():
    assert top("Reis") == "C352000"
    assert top("Zwiebeln") == "G480100"


def test_compounds_on_either_side():
    assert top("Räuchertofu") == "H861000"
    codes = [s.code for s in suggest(["Haferflocken"], FOODS)]
    assert "C133000" in codes[:2]


def test_aliases_count_too():
    assert top("Grünzeug", "Brokkoli") == "G312100"


def test_search_needs_every_word():
    assert [hit.code for hit in search("lauch roh", FOODS)] == ["G470100"]
    assert search("xyz", FOODS) == []
