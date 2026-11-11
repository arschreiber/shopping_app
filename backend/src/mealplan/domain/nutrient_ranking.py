"""Welche Artikel tragen am meisten von einem Nährstoff? (pure)

Verglichen wird auf einer gemeinsamen Basis, sonst wäre die Liste sinnlos:

- **je 100 g / 100 ml** (Standard): wie viel steckt in der Menge. Stück-Artikel werden
  über ihr Stückgewicht umgerechnet; ohne Stückgewicht fehlen sie in der Liste.
- **je 100 kcal**: Nährstoffdichte - was bekomme ich für meine Kalorien. Artikel ohne
  Kalorien (Salz, Wasser) haben hier keinen Wert, statt durch null zu teilen.

Was keine Quelle kennt, steht nicht mit null in der Rangliste, sondern getrennt als
"ohne Angabe" - eine Null würde wie "enthält nichts" aussehen.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from .enums import Unit
from .micronutrients import MICRONUTRIENTS, NutrientDef

Basis = Literal["mass", "kcal"]
Source = Literal["label", "bls"]

HUNDRED = Decimal(100)
GROUP_MACROS = "Energie & Makros"

# Makros haben keinen DGE-Tageswert in der App - die Balken sind dort relativ zum
# Spitzenreiter (das macht das Frontend, wenn `share` fehlt).
MACROS: tuple[NutrientDef, ...] = (
    NutrientDef("kcal", "Energie", "kcal", GROUP_MACROS, places=0),
    NutrientDef("carbs_g", "Kohlenhydrate", "g", GROUP_MACROS),
    NutrientDef("fat_g", "Fett", "g", GROUP_MACROS),
    NutrientDef("protein_g", "Eiweiß", "g", GROUP_MACROS),
)
NUTRIENTS: dict[str, NutrientDef] = {n.code: n for n in (*MACROS, *MICRONUTRIENTS)}


@dataclass(frozen=True, slots=True)
class ArticleValues:
    """Ein Artikel mit seinen Werten je Bezugsgröße (100 g / 100 ml / Stück)."""

    article_id: int
    name: str
    unit: Unit
    values: Mapping[str, tuple[Decimal, Source]] = field(default_factory=dict)
    piece_grams: Decimal | None = None  # nur bei STUECK: Gramm je Stück

    @property
    def kcal(self) -> Decimal | None:
        entry = self.values.get("kcal")
        return entry[0] if entry else None


@dataclass(frozen=True, slots=True)
class RankedArticle:
    article_id: int
    name: str
    amount: Decimal  # in der Anzeigeeinheit des Nährstoffs, je `per`
    per: str  # "100 g", "100 ml", "100 kcal"
    share: Decimal | None  # % vom Tageswert, sofern es einen gibt
    source: Source


@dataclass(frozen=True, slots=True)
class Unranked:
    article_id: int
    name: str
    reason: str


@dataclass(frozen=True, slots=True)
class Ranking:
    nutrient: NutrientDef
    basis: Basis
    entries: tuple[RankedArticle, ...]
    missing: tuple[Unranked, ...]


def _per_mass(article: ArticleValues, amount: Decimal) -> tuple[Decimal, str] | None:
    if article.unit is Unit.G:
        return amount, "100 g"
    if article.unit is Unit.ML:
        return amount, "100 ml"
    if not article.piece_grams:
        return None
    return amount / article.piece_grams * HUNDRED, "100 g"


def rank(code: str, articles: Iterable[ArticleValues], basis: Basis = "mass") -> Ranking:
    nutrient = NUTRIENTS[code]
    if basis == "kcal" and code == "kcal":
        basis = "mass"  # kcal je kcal ist immer 100
    step = Decimal(1).scaleb(-(nutrient.places + (1 if basis == "kcal" else 0)))
    entries: list[RankedArticle] = []
    missing: list[Unranked] = []
    for article in articles:
        value = article.values.get(code)
        if value is None:
            missing.append(Unranked(article.article_id, article.name, "keine Angabe"))
            continue
        amount, source = value
        if basis == "kcal":
            kcal = article.kcal
            if not kcal:
                missing.append(Unranked(article.article_id, article.name, "ohne Kalorien"))
                continue
            scaled, per = amount / kcal * HUNDRED, "100 kcal"
        else:
            converted = _per_mass(article, amount)
            if converted is None:
                missing.append(Unranked(article.article_id, article.name, "ohne Stückgewicht"))
                continue
            scaled, per = converted
        share = (
            (scaled / nutrient.reference * HUNDRED).quantize(Decimal(1))
            if nutrient.reference
            else None
        )
        entries.append(
            RankedArticle(
                article_id=article.article_id,
                name=article.name,
                amount=scaled.quantize(step),
                per=per,
                share=share,
                source=source,
            )
        )
    entries.sort(key=lambda entry: (-entry.amount, entry.name.casefold()))
    missing.sort(key=lambda entry: entry.name.casefold())
    return Ranking(nutrient, basis, tuple(entries), tuple(missing))
