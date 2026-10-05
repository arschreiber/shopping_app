"""Nährwerte eines Gerichts aus den Nährwerten seiner Zutaten (pure).

Zwei Entscheidungen tragen den Rest:

1. **Die Bezugsgröße steckt schon in der Einheit.** Jeder Artikel hat genau eine
   kanonische Einheit, also gilt je 100 g, je 100 ml oder je 1 Stück - ohne ein
   zusätzliches Feld und ohne `piece_weight_g`: eine Zucchini trägt ihre Werte je Stück.

2. **Lücken werden gemeldet, nicht verschwiegen.** Fehlt bei einer Zutat die Angabe oder
   hat die Zeile keine Menge ("Olivenöl nach Bedarf"), ist die Summe unvollständig. Eine
   stillschweigend zu niedrige Kalorienzahl wäre schlechter als gar keine - dieselbe
   Haltung wie bei den Einheiten, die lieber abgelehnt als geraten werden.

Ausnahme zu (2): trägt ein Artikel überall Nullen (Salz, Pfeffer), ändert auch eine
unbekannte Menge nichts an der Summe. Solche Zeilen sind keine Lücke.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .enums import Unit
from .model import IngredientSpec
from .units import Quantity

# Worauf sich die Angaben beziehen, je kanonischer Einheit.
BASIS_AMOUNT: dict[Unit, Decimal] = {
    Unit.G: Decimal(100),
    Unit.ML: Decimal(100),
    Unit.STUECK: Decimal(1),
}

BASIS_LABEL: dict[Unit, str] = {
    Unit.G: "je 100 g",
    Unit.ML: "je 100 ml",
    Unit.STUECK: "je Stück",
}


@dataclass(frozen=True, slots=True)
class Nutrients:
    kcal: Decimal = Decimal(0)
    carbs_g: Decimal = Decimal(0)
    fat_g: Decimal = Decimal(0)
    protein_g: Decimal = Decimal(0)

    def __add__(self, other: Nutrients) -> Nutrients:
        return Nutrients(
            self.kcal + other.kcal,
            self.carbs_g + other.carbs_g,
            self.fat_g + other.fat_g,
            self.protein_g + other.protein_g,
        )

    def scaled(self, factor: Decimal) -> Nutrients:
        return Nutrients(
            self.kcal * factor,
            self.carbs_g * factor,
            self.fat_g * factor,
            self.protein_g * factor,
        )

    def rounded(self) -> Nutrients:
        """Auf ganze kcal und eine Nachkommastelle bei den Makros."""
        return Nutrients(
            self.kcal.quantize(Decimal(1)),
            self.carbs_g.quantize(Decimal("0.1")),
            self.fat_g.quantize(Decimal("0.1")),
            self.protein_g.quantize(Decimal("0.1")),
        )

    @property
    def is_zero(self) -> bool:
        return not (self.kcal or self.carbs_g or self.fat_g or self.protein_g)


@dataclass(frozen=True, slots=True)
class ArticleNutrition:
    """Die Angaben eines Artikels, bezogen auf seine kanonische Einheit."""

    article_id: int
    unit: Unit
    per_basis: Nutrients


@dataclass(frozen=True, slots=True)
class DishNutrition:
    total: Nutrients
    per_portion: Nutrients
    ingredient_count: int
    counted_ids: tuple[int, ...] = ()
    missing_data_ids: tuple[int, ...] = ()  # Artikel ohne Nährwerte
    open_quantity_ids: tuple[int, ...] = ()  # Zeile ohne Menge, Werte nicht alle null

    @property
    def gap_count(self) -> int:
        return len(self.missing_data_ids) + len(self.open_quantity_ids)

    @property
    def is_complete(self) -> bool:
        return self.ingredient_count > 0 and self.gap_count == 0

    @property
    def has_any(self) -> bool:
        """Lohnt sich die Anzeige überhaupt?"""
        return bool(self.counted_ids)


def dish_nutrition(
    ingredients: list[IngredientSpec],
    articles: dict[int, ArticleNutrition],
    *,
    portions: int,
) -> DishNutrition:
    """Summiert die Zutaten und teilt durch die Portionen.

    Verdoppeln ändert nichts: doppelte Mengen auf doppelte Portionen ergibt denselben
    Wert je Portion. Darum rechnet diese Funktion bewusst mit dem Grundrezept.
    """
    total = Nutrients()
    counted: list[int] = []
    missing: list[int] = []
    open_quantity: list[int] = []

    for line in ingredients:
        facts = articles.get(line.article_id)
        if facts is None:
            missing.append(line.article_id)
            continue
        if line.quantity is None:
            # Ohne Menge trägt nur bei, was ohnehin null ist (Salz, Pfeffer).
            if not facts.per_basis.is_zero:
                open_quantity.append(line.article_id)
            else:
                counted.append(line.article_id)
            continue

        amount = Quantity(line.quantity, line.unit).to(facts.unit).amount
        assert amount is not None  # Menge ist gesetzt, `to` erhält das
        total = total + facts.per_basis.scaled(amount / BASIS_AMOUNT[facts.unit])
        counted.append(line.article_id)

    divisor = Decimal(portions if portions > 0 else 1)
    return DishNutrition(
        total=total.rounded(),
        per_portion=total.scaled(Decimal(1) / divisor).rounded(),
        ingredient_count=len(ingredients),
        counted_ids=tuple(counted),
        missing_data_ids=tuple(missing),
        open_quantity_ids=tuple(open_quantity),
    )


def article_nutrition(
    article_id: int,
    unit: Unit,
    *,
    kcal: Decimal | None,
    carbs_g: Decimal | None,
    fat_g: Decimal | None,
    protein_g: Decimal | None,
) -> ArticleNutrition | None:
    """`None`, solange nichts erfasst ist - fehlende Werte zählen nicht als Null."""
    values = (kcal, carbs_g, fat_g, protein_g)
    if all(value is None for value in values):
        return None
    return ArticleNutrition(
        article_id=article_id,
        unit=unit,
        per_basis=Nutrients(
            kcal=kcal or Decimal(0),
            carbs_g=carbs_g or Decimal(0),
            fat_g=fat_g or Decimal(0),
            protein_g=protein_g or Decimal(0),
        ),
    )
