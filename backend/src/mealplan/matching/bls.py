"""Artikel -> BLS-Lebensmittel vorschlagen.

Die BLS-Namen sind anders gebaut als unsere Artikel: Singular, Zustand hinten dran
("Kichererbse Konserve, abgetropft", "Reis poliert, roh"), dazu gut 2000 fertige
Gerichte ("Reis mit gedünsteten Tomaten"). Ein reiner Fuzzy-Score bevorzugt die kurzen
Gerichte. Darum zählt hier zuerst das **Kopfwort**: der BLS-Name muss mit dem Wort des
Artikels anfangen (Plural und Fugen-s egal), danach entscheiden Zustand und Länge.

Vorgeschlagen wird nur. Übernommen wird von Hand (`mealplan nutrients link` oder in der
Artikel-Seite) - die Wahl zwischen roh, Konserve und gekocht ist eine fachliche.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from rapidfuzz import fuzz

from .normalize import normalize as _normalize

# 7000 BLS-Namen, bei jedem Vorschlag neu normalisiert, kosten Sekunden.
normalize = lru_cache(maxsize=20_000)(_normalize)

# BLS-Codes X und Y sind zusammengesetzte Gerichte und Rezepte.
DISH_PREFIXES = ("X", "Y")

RAW_WORDS = ("roh", "frisch")
PREPARED_WORDS = (
    "gekocht", "gebraten", "geduenstet", "gebacken", "frittiert", "geschmort", "gegart",
    "gedaempft", "gegrillt", "ueberbacken", "paniert", "gezuckert", "kandiert", "mariniert",
    "gargezogen", "pochiert",
)
# Wo der BLS ein anderes Wort benutzt. Nur Fälle, die der Kopfwort-Vergleich nicht
# finden kann - normalisierte Schreibweise, Wert ist ein zusätzlicher Suchname.
SYNONYMS: dict[str, str] = {
    "brokkoli": "broccoli",
    "jogurt": "joghurt",
    "nudeln": "teigwaren eifrei",
    "spaghetti": "teigwaren eifrei",
    "lasagneplatten": "teigwaren eifrei",
    "mie nudeln": "eierteigwaren",
    "mandelmilch": "mandeldrink",
    "hafermilch": "haferdrink",
    "sojamilch": "sojadrink",
    "saure sahne": "sauerrahm saure sahne",
    "schmand": "sauerrahm schmand",
    "stangensellerie": "bleichsellerie",
    "oel": "rapsoel",
    "hirtenkaese": "salzlakenkaese hirtenkaese",
    "cola": "colagetraenk",
    "wraps": "weizentortilla",
    "burger buns": "weizenbroetchen",
    "moehren": "karotte moehre",
}
SUGGEST_LIMIT = 6
MIN_SCORE = 55.0


@dataclass(frozen=True, slots=True)
class FoodName:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class BlsSuggestion:
    code: str
    name: str
    score: float


def _stem(word: str) -> str:
    """Grobe Grundform: "bananen" -> "banan", "moehren" -> "moehr", "tomaten" -> "tomat"."""
    for suffix in ("en", "n", "e", "s"):
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


@lru_cache(maxsize=20_000)
def _heads(name: str) -> tuple[str, ...]:
    """Die Kopfwörter eines BLS-Namens: "Karotte/Möhre, roh" -> [karotte, moehre]."""
    words = name.split(",", 1)[0].split()
    if not words:
        return ()
    heads = [normalize(part) for part in words[0].split("/")]
    if len(words) > 1:  # "Hafer Flocken" ist "haferflocken"
        heads.append(normalize(words[0] + words[1]))
    return tuple(h.replace(" ", "") for h in heads if h)


def _head_match(needle_words: list[str], heads: tuple[str, ...]) -> float:
    """Wie gut trifft der Artikel den *Anfang* des BLS-Namens? 0 bis 1."""
    if not needle_words or not heads:
        return 0.0
    stems = [_stem(w) for w in needle_words] + [_stem("".join(needle_words))]
    best = 0.0
    for head in heads:
        first = _stem(head)
        for stem in stems:
            if first == stem:
                return 1.0
            if len(stem) < 4 or len(first) < 4:
                continue
            if first.endswith(stem):  # Speise|zwiebel, Gemüse|paprika
                best = max(best, 0.85)
            elif stem.endswith(first):  # Räucher|tofu
                best = max(best, 0.8)
            elif first.startswith(stem):  # Kichererbsen|mehl - meist ein Produkt daraus
                best = max(best, 0.55)
    return best


def score(needle: str, food: FoodName) -> float:
    candidate = normalize(food.name)
    if not needle or not candidate:
        return 0.0
    needle_words = needle.split()
    food_words = candidate.split()
    head = _head_match(needle_words, _heads(food.name))
    base = float(fuzz.token_set_ratio(needle, candidate))
    value = 0.5 * base + 45 * head
    if any(w in RAW_WORDS for w in food_words):
        value += 6
    if any(w in PREPARED_WORDS for w in food_words):
        value -= 8
    if food.code.startswith(DISH_PREFIXES):
        value -= 25
    if "mit" in food_words:
        value -= 6
    # Kürzere Namen sind meist das Grundlebensmittel, nicht eine Variante davon.
    value -= 0.8 * max(0, len(food_words) - len(needle_words) - 1)
    return round(value, 1)


def suggest(
    names: Iterable[str], foods: Iterable[FoodName], *, limit: int = SUGGEST_LIMIT
) -> list[BlsSuggestion]:
    """Beste BLS-Einträge für einen Artikel (Name plus Aliasse)."""
    needles = [n for n in (normalize(name) for name in names) if n]
    needles += [SYNONYMS[n] for n in needles if n in SYNONYMS]
    best: dict[str, BlsSuggestion] = {}
    for food in foods:
        top = max((score(needle, food) for needle in needles), default=0.0)
        if top < MIN_SCORE:
            continue
        best[food.code] = BlsSuggestion(food.code, food.name, top)
    ordered = sorted(best.values(), key=lambda s: (-s.score, len(s.name)))
    return ordered[:limit]


def search(query: str, foods: Iterable[FoodName], *, limit: int = 30) -> list[BlsSuggestion]:
    """Freitextsuche für die Artikel-Seite: alle Wörter müssen vorkommen, dann Score."""
    needle = normalize(query)
    words = needle.split()
    if not words:
        return ()
    hits = []
    for food in foods:
        candidate = normalize(food.name)
        if all(word in candidate for word in words):
            hits.append(BlsSuggestion(food.code, food.name, score(needle, food)))
    hits.sort(key=lambda s: (-s.score, len(s.name)))
    return hits[:limit]
