"""Einheiten und Mengen-Aggregation (ARCHITECTURE.md §3, general_plan.md §8 Nr. 10).

Kernentscheidung: Jeder Artikel hat *genau eine* kanonische Einheit. Innerhalb einer
Dimension wird gerechnet (g <-> kg, ml <-> l), ein Dimensionswechsel (2 Zwiebeln vs.
150 g Zwiebeln) wird abgelehnt - nicht stillschweigend geraten.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .enums import Dimension, Unit

DIMENSION_OF: dict[Unit, Dimension] = {
    Unit.STUECK: Dimension.COUNT,
    Unit.G: Dimension.MASS,
    Unit.KG: Dimension.MASS,
    Unit.ML: Dimension.VOLUME,
    Unit.L: Dimension.VOLUME,
}

# Faktor auf die Basiseinheit der jeweiligen Dimension (STUECK, G, ML).
_TO_BASE: dict[Unit, Decimal] = {
    Unit.STUECK: Decimal(1),
    Unit.G: Decimal(1),
    Unit.KG: Decimal(1000),
    Unit.ML: Decimal(1),
    Unit.L: Decimal(1000),
}

BASE_UNIT: dict[Dimension, Unit] = {
    Dimension.COUNT: Unit.STUECK,
    Dimension.MASS: Unit.G,
    Dimension.VOLUME: Unit.ML,
}

# Einheiten, in denen ein Artikel kanonisch gefuehrt werden darf. Nur Basiseinheiten -
# damit gibt es pro Artikel nur eine Zahlenwelt und die Liste ist vergleichbar.
CANONICAL_UNITS: tuple[Unit, ...] = (Unit.STUECK, Unit.G, Unit.ML)


class UnitError(ValueError):
    """Dimensionswechsel oder unbekannte Einheit. Wird zu HTTP 422."""


@dataclass(frozen=True, slots=True, order=True)
class Quantity:
    """Eine Menge. `amount is None` heisst bewusst "nach Bedarf" (Plan §8 Nr. 10)."""

    amount: Decimal | None
    unit: Unit

    def __post_init__(self) -> None:
        if self.amount is not None and self.amount < 0:
            raise UnitError("Menge darf nicht negativ sein")

    @property
    def dimension(self) -> Dimension:
        return DIMENSION_OF[self.unit]

    @property
    def is_open(self) -> bool:
        """True bei "nach Bedarf" - solche Mengen werden nie aufsummiert."""
        return self.amount is None

    def to(self, unit: Unit) -> Quantity:
        if unit == self.unit:
            return self
        if DIMENSION_OF[unit] != self.dimension:
            raise UnitError(
                f"{self.unit.value} und {unit.value} sind verschiedene Dimensionen "
                f"({self.dimension.value} vs. {DIMENSION_OF[unit].value})"
            )
        if self.amount is None:
            return Quantity(None, unit)
        base = self.amount * _TO_BASE[self.unit]
        return Quantity(base / _TO_BASE[unit], unit)

    def scaled(self, factor: int | Decimal) -> Quantity:
        if self.amount is None:
            return self
        return Quantity(self.amount * Decimal(factor), self.unit)

    def __add__(self, other: Quantity) -> Quantity:
        if self.amount is None or other.amount is None:
            # Eine offene Menge "verschluckt" die andere: 500 g + nach Bedarf = nach Bedarf
            # wäre falsch (500 g gehen verloren). Darum: offen + Zahl = Zahl, offen bleibt
            # nur, wenn beide offen sind.
            if self.amount is None and other.amount is None:
                if other.dimension != self.dimension:
                    raise UnitError("Dimensionen passen nicht zusammen")
                return Quantity(None, self.unit)
            return self if other.amount is None else other.to(self.unit)
        return Quantity(self.amount + other.to(self.unit).amount, self.unit)


def trim(value: Decimal | None) -> Decimal | None:
    """`250.000` -> `250`, `0.500` -> `0.5`, `None` bleibt `None`.

    Ohne das stehen im Formular "250.000" und "350.00" - die Nachkommastellen stammen
    aus der Spaltendefinition, nicht aus der Eingabe. `Decimal.normalize()` allein
    reicht nicht: es macht aus 250 die Darstellung `2.5E+2`.
    """
    if value is None:
        return None
    normalized = value.normalize()
    exponent = normalized.as_tuple().exponent
    if isinstance(exponent, int) and exponent > 0:
        return normalized.quantize(Decimal(1))
    return normalized


def canonical_unit_for(unit: Unit) -> Unit:
    """Basiseinheit der Dimension - was in `article.unit` stehen darf."""
    return BASE_UNIT[DIMENSION_OF[unit]]


def aggregate(quantities: list[Quantity], target: Unit) -> Quantity:
    """Summiert Mengen in `target`. Leer -> "nach Bedarf" in `target`."""
    if not quantities:
        return Quantity(None, target)
    total: Decimal | None = None
    for q in quantities:
        converted = q.to(target)
        if converted.amount is None:
            continue
        total = converted.amount if total is None else total + converted.amount
    return Quantity(total, target)


def _trim(value: Decimal) -> str:
    """Dezimalzahl ohne Nullschwanz, deutsches Komma."""
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
    text = format(quantized, "f")
    return text.replace(".", ",")


def format_quantity(q: Quantity) -> str:
    """Menschenlesbare Menge für UI und Bring!-Spezifikation.

    Skaliert nach oben, wo es natuerlicher ist (1500 g -> 1,5 kg), weil die
    Spezifikation in Bring! ein Freitextfeld ist und im Laden gelesen wird.
    """
    if q.amount is None:
        return "nach Bedarf"
    amount, unit = q.amount, q.unit
    if unit == Unit.G and amount >= 1000:
        amount, unit = amount / Decimal(1000), Unit.KG
    elif unit == Unit.ML and amount >= 1000:
        amount, unit = amount / Decimal(1000), Unit.L
    label = {
        Unit.STUECK: "Stk",
        Unit.G: "g",
        Unit.KG: "kg",
        Unit.ML: "ml",
        Unit.L: "l",
    }[unit]
    if unit == Unit.STUECK:
        return f"{_trim(amount)} {label}"
    return f"{_trim(amount)} {label}"
