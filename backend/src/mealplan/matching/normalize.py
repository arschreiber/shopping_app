"""Normalisierung + Fuzzy-Matching (ARCHITECTURE.md §5, general_plan.md §8 Nr. 4).

Wird zweimal gebraucht: für den Zutaten-Parser (Zeile -> Artikel) und für das
Angebots-Matching (Angebotsname -> Artikel). Beides teilt dieselbe Normalisierung,
damit "Hirtenkäse" und "HIRTENKAESE 200g" derselbe Schluessel sind.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

FUZZY_THRESHOLD = 85  # general_plan.md §7: token_set_ratio ~85
SUGGEST_THRESHOLD = 60  # darunter lohnt kein Vorschlag in der Combobox

# Komposita-Erkennung: ein deutsches Kompositum teilt seinen Kopf am Ende
# (Basmati|reis, Vollkorn|reis) oder seinen Modifikator am Anfang (Hähnchen|brust).
# Kürzer als vier Zeichen wird nicht verglichen (Öl, Ei), und der Rest muss mindestens
# zwei Zeichen lang sein - sonst gilt "Reise" als Kompositum von "Reis".
COMPOUND_MIN_LEN = 4
COMPOUND_MIN_EXTRA = 2
COMPOUND_SCORE = 95.0

_UMLAUT = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

# Mengenangaben, Packungsgroessen und Eigenmarken-Token, die den Namen verrauschen.
_QUANTITY = re.compile(
    r"\b\d+[.,]?\d*\s*(?:g|gr|gramm|kg|ml|l|liter|stk|stück|st|x|er|%|pkg|packung|dose|"
    r"glas|becher|beutel|bund|scheiben?)\b",
    re.IGNORECASE,
)
_LEADING_NUMBER = re.compile(r"^\s*\d+[.,]?\d*\s*")
_PRIVATE_LABELS = (
    "gut & günstig", "gut und günstig", "gut&günstig", "g&g",
    "ja!", "rewe beste wahl", "rewe bio", "edeka bio",
    "milsani", "milfina", "bio sonne", "netto", "aldi", "edeka", "rewe",
)
_NOISE = re.compile(r"[^a-z0-9\s]+")
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Kleinschreibung, Umlaut-Faltung, Mengen und Eigenmarken heraus."""
    lowered = unicodedata.normalize("NFC", text).strip().lower()
    for label in _PRIVATE_LABELS:
        lowered = lowered.replace(label, " ")
    lowered = _QUANTITY.sub(" ", lowered)
    lowered = _LEADING_NUMBER.sub("", lowered)
    lowered = lowered.translate(_UMLAUT)
    lowered = _NOISE.sub(" ", lowered)
    return _SPACES.sub(" ", lowered).strip()


def _pair_score(needle: str, candidate: str) -> tuple[float, float]:
    """(token_set_ratio, token_sort_ratio).

    `token_set_ratio` allein gibt "Tomaten" und "Passierte Tomaten" für die Anfrage
    "Passierte Tomaten" beide 100 - fehlende Tokens kosten dort nichts. Erst
    `token_sort_ratio` als Stichentscheid waehlt den vollstaendigeren Treffer. Ohne das
    landen 500 ml passierte Tomaten beim Artikel "Tomaten" (Einheit g).
    """
    return (
        float(fuzz.token_set_ratio(needle, candidate)),
        float(fuzz.token_sort_ratio(needle, candidate)),
    )


def best_match(
    query: str, choices: dict[int, list[str]], *, threshold: int = FUZZY_THRESHOLD
) -> tuple[int, float] | None:
    """Bester Treffer aus `{id: [name, alias, ...]}` oder None."""
    needle = normalize(query)
    if not needle:
        return None
    best: tuple[int, tuple[float, float]] | None = None
    for key, names in choices.items():
        for name in names:
            candidate = normalize(name)
            if not candidate:
                continue
            score = _pair_score(needle, candidate)
            if score[0] >= threshold and (best is None or score > best[1]):
                best = (key, score)
    return (best[0], best[1][0]) if best else None


@dataclass(frozen=True, slots=True)
class Suggestion:
    """Ein Vorschlag mit seiner Begründung - `kind` sagt, *warum* er kommt."""

    key: int
    score: float
    kind: str  # "COMPOUND" | "FUZZY"
    matched_name: str


def compound_overlap(query: str, candidate: str) -> str | None:
    """Teilen die beiden Wörter einen Wortbestandteil? Gibt ihn zurück, sonst None.

    `token_set_ratio` hilft hier nicht: "Basmatireis" und "Reis" kommen auf 53, weit
    unter jeder sinnvollen Schwelle. `partial_ratio` hilft auch nicht, denn es gibt
    "Preiselbeeren" gegen "Reis" glatte 100. Was trägt, ist die Bauweise deutscher
    Komposita - der gemeinsame Teil steht am Wortanfang oder am Wortende, nicht
    irgendwo mitten drin.
    """
    left, right = normalize(query), normalize(candidate)
    if not left or not right:
        return None
    for token in left.split():
        for other in right.split():
            shorter, longer = sorted((token, other), key=len)
            if len(shorter) < COMPOUND_MIN_LEN:
                continue
            if len(longer) < len(shorter) + COMPOUND_MIN_EXTRA:
                continue
            if longer.endswith(shorter) or longer.startswith(shorter):
                return shorter
    return None


def suggest(
    query: str, choices: dict[int, list[str]], *, limit: int = 6
) -> list[Suggestion]:
    """Vorschläge für eine Zutatenzeile, die keinen sicheren Treffer hat.

    Erst Komposita ("Basmatireis" -> vorhandenes "Reis"), dann normale Fuzzy-Treffer.
    Der Parser entscheidet nichts davon selbst: er schlägt vor, gewählt wird von Hand -
    dieselbe Regel wie bei den Einheiten (general_plan.md §8 Nr. 10).
    """
    needle = normalize(query)
    if not needle:
        return []
    best: dict[int, Suggestion] = {}
    for key, names in choices.items():
        for name in names:
            candidate = normalize(name)
            if not candidate:
                continue
            if candidate == needle:
                continue
            shared = compound_overlap(needle, candidate)
            if shared is not None:
                score, kind = COMPOUND_SCORE, "COMPOUND"
            else:
                score, kind = float(fuzz.token_set_ratio(needle, candidate)), "FUZZY"
                if score < SUGGEST_THRESHOLD:
                    continue
            previous = best.get(key)
            if previous is None or score > previous.score:
                best[key] = Suggestion(key, score, kind, name)
    ordered = sorted(best.values(), key=lambda s: (-s.score, len(s.matched_name)))
    return ordered[:limit]


def search(
    query: str, choices: dict[int, str], *, limit: int = 50
) -> list[tuple[int, str]]:
    """Namenssuche für die Zutaten-Combobox: erst Präfix, dann Teilstring.

    Bewusst ohne Ähnlichkeitsmaß und ohne Schwelle. Fuzzy-Scores brauchen erst ein
    halbes Wort, bevor sie über die Schwelle kommen - beim Tippen fühlt sich das an,
    als gäbe es den Artikel nicht. Zwei Buchstaben sollen reichen: "re" zeigt "Reis"
    und "Reibekäse", danach alles, was "re" irgendwo enthält. Die Reihenfolge ist die
    ganze Aussage, eine Grenze zwischen den Gruppen gibt es nicht.

    Fuzzy-Treffer bleiben dem Parser vorbehalten (`suggest`): dort kommt der Name aus
    einem eingefügten Rezept und niemand kann nachtippen.
    """
    needle = normalize(query)
    if not needle:
        return []
    prefix: list[tuple[str, int]] = []
    contains: list[tuple[str, int]] = []
    for key, value in choices.items():
        candidate = normalize(value)
        if not candidate:
            continue
        if candidate.startswith(needle):
            prefix.append((candidate, key))
        elif needle in candidate:
            contains.append((candidate, key))
    prefix.sort()
    contains.sort()
    hits = [(key, "PREFIX") for _, key in prefix] + [(key, "CONTAINS") for _, key in contains]
    return hits[:limit]


def rank(query: str, choices: dict[int, str], *, limit: int = 8) -> list[tuple[int, float]]:
    """Sortierte Vorschläge für die Combobox - toleranter als `best_match`."""
    needle = normalize(query)
    if not needle:
        return []
    scored: list[tuple[int, tuple[float, float]]] = []
    for key, value in choices.items():
        candidate = normalize(value)
        if not candidate:
            continue
        score = _pair_score(needle, candidate)
        if score[0] >= SUGGEST_THRESHOLD:
            scored.append((key, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [(key, score[0]) for key, score in scored[:limit]]
