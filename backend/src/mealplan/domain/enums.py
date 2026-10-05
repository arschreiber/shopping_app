"""Fachliche Enums. Werden vom ORM (als String-Spalten) und von der API geteilt.

Liegt in `domain/`, weil die Werte fachlich sind - nicht technisch. Der Rest von `domain/`
importiert nichts anderes aus dem Projekt (siehe tests/domain/test_architecture.py).
"""

from __future__ import annotations

from enum import StrEnum


class Meal(StrEnum):
    LUNCH = "LUNCH"
    DINNER = "DINNER"


class Effort(StrEnum):
    """Aufwand eines Gerichts (general_plan.md §3). Zwei Stufen reichen: passt es in einen
    Tag mit wenig Zeit oder nicht. "aufwendig" hat im Alltag nichts unterschieden."""

    QUICK = "QUICK"  # schnell, < 20 min
    NORMAL = "NORMAL"


class TimeBudget(StrEnum):
    """Zeit für eine Mahlzeit. Bei `LITTLE` kommen nur schnelle Gerichte oder Reste."""

    NORMAL = "NORMAL"
    LITTLE = "LITTLE"


class SuitableFor(StrEnum):
    LUNCH = "LUNCH"
    DINNER = "DINNER"
    BOTH = "BOTH"


class SlotSpecial(StrEnum):
    NONE = "NONE"
    EATING_OUT = "EATING_OUT"
    FROM_PANTRY = "FROM_PANTRY"


class AssignmentKind(StrEnum):
    DISH = "DISH"
    LEFTOVER = "LEFTOVER"
    PANTRY = "PANTRY"
    EMPTY = "EMPTY"


class CategoryAxis(StrEnum):
    """Achsen für die Abwechslungsregeln (general_plan.md §4)."""

    SIDE = "SIDE"  # Sättigungsbeilage: Reis, Nudeln, Kartoffeln, Brot
    PROTEIN = "PROTEIN"  # Fisch, Hähnchen, Hirtenkäse, Hülsenfrüchte
    CUISINE = "CUISINE"  # italienisch, asiatisch, ...


class Unit(StrEnum):
    STUECK = "STUECK"
    G = "G"
    KG = "KG"
    ML = "ML"
    L = "L"


class Dimension(StrEnum):
    COUNT = "COUNT"
    MASS = "MASS"
    VOLUME = "VOLUME"


class WarningLevel(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class ItemSource(StrEnum):
    RECIPE = "RECIPE"
    MANUAL = "MANUAL"
    WATCHLIST = "WATCHLIST"


class ListStatus(StrEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"


class SyncKind(StrEnum):
    BRING_PUSH = "BRING_PUSH"
    OFFER_FETCH = "OFFER_FETCH"
    CATALOG_FETCH = "CATALOG_FETCH"


class SyncStatus(StrEnum):
    OK = "OK"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class AliasKind(StrEnum):
    ALIAS = "ALIAS"
    EIGENMARKE = "EIGENMARKE"


class MatchDecider(StrEnum):
    FUZZY = "FUZZY"
    USER = "USER"
    LLM = "LLM"


class Chain(StrEnum):
    EDEKA = "EDEKA"
    ALDI_NORD = "ALDI_NORD"
    NETTO_MD = "NETTO_MD"
    REWE = "REWE"
