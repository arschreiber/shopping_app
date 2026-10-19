"""Angebot -> Artikel: was der Abgleich erkennen soll und was gerade nicht.

Die Fälle stammen aus den Prospekten vom 13.10.2026 (Aldi, Combi, Netto, Rewe).
"""

from __future__ import annotations

import pytest

from mealplan.matching.normalize import FUZZY_THRESHOLD, best_match

ARTICLES = {
    1: ["Kartoffeln"],
    2: ["Süßkartoffeln"],
    3: ["Möhren"],
    4: ["Zwiebeln"],
    5: ["Frühlingszwiebeln"],
    6: ["Tomaten"],
    7: ["Passierte Tomaten"],
    8: ["Zucker"],
    9: ["Orangen"],
    10: ["Lauch"],
    11: ["Öl"],
}
NAMES = {key: names[0] for key, names in ARTICLES.items()}


def matched(offer: str) -> str | None:
    hit = best_match(offer, ARTICLES, threshold=FUZZY_THRESHOLD)
    return NAMES[hit[0]] if hit else None


@pytest.mark.parametrize(
    ("offer", "article"),
    [
        ("Speisekartoffeln", "Kartoffeln"),
        ("Heimat Speisekartoffeln XXL", "Kartoffeln"),
        ("NaturWert Bio Speisemöhren", "Möhren"),
        ("Gelbe Bio Speisezwiebeln", "Zwiebeln"),
        ("Strauchtomaten", "Tomaten"),
        ("Rispentomaten", "Tomaten"),
        ("Saftorangen", "Orangen"),
        ("Speiseöl", "Öl"),
    ],
)
def test_a_variety_prefix_does_not_hide_the_article(offer, article):
    """Speise|kartoffeln sind Kartoffeln, Strauch|tomaten sind Tomaten."""
    assert matched(offer) == article


@pytest.mark.parametrize(
    ("offer", "article"),
    [
        ("Süßkartoffeln", "Süßkartoffeln"),
        ("Frühlingszwiebeln", "Frühlingszwiebeln"),
        ("Passierte Tomaten", "Passierte Tomaten"),
    ],
)
def test_the_more_specific_article_still_wins(offer, article):
    assert matched(offer) == article


@pytest.mark.parametrize(
    "offer",
    [
        "ja! Bratkartoffeln",  # zubereitet - und "Brat" steht nicht auf der Liste
        "Star-Q LED Lichtschlauch",  # endet auf "lauch", ist aber keiner
        "Alpro Barista Haferdrink oder Soyadrink ohne Zucker",
        "Müsli mit 30 % weniger Zucker",
    ],
)
def test_what_only_looks_like_an_article_is_left_alone(offer):
    assert matched(offer) is None
