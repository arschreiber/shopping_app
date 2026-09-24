"""Domänen-Datentypen (ARCHITECTURE.md §4).

Alles frozen und ohne I/O. Ein `PlanningSnapshot` ist das eingefrorene Wissen, das der
Planer braucht: Gerichte inklusive der *für diese Woche* abgeleiteten Fakten
(`weeks_since_cooked`, `offer_savings_eur`), das Wochenraster und die Gewichte. Die
Ableitung passiert im Mapper (`db/mappers.py`), damit die Domäne keine Uhr und keine
Session braucht.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal
from typing import Self

from .enums import (
    AssignmentKind,
    CategoryAxis,
    Effort,
    Meal,
    SlotSpecial,
    SuitableFor,
    TimeBudget,
    Unit,
    WarningLevel,
)

# --------------------------------------------------------------------------- Identität


@dataclass(frozen=True, slots=True, order=True)
class SlotKey:
    """Identität eines Slots *innerhalb einer Woche*: Tag (0=Mo) + Mahlzeit.

    Bewusst nicht die DB-ID: der Planer braucht Ordnung ("welcher Slot kommt danach?")
    und Abstände in Tagen. `db/mappers.py` übersetzt zwischen SlotKey und `slot.id`.
    """

    day: int  # 0 = Montag ... 6 = Sonntag
    meal_order: int  # 0 = Mittag, 1 = Abend

    @classmethod
    def of(cls, day: int, meal: Meal) -> Self:
        if not 0 <= day <= 6:
            raise ValueError(f"Tag ausserhalb 0..6: {day}")
        return cls(day, 0 if meal is Meal.LUNCH else 1)

    @property
    def meal(self) -> Meal:
        return Meal.LUNCH if self.meal_order == 0 else Meal.DINNER

    @property
    def index(self) -> int:
        """Laufende Nummer 0..13 - für "kommt danach"-Vergleiche."""
        return self.day * 2 + self.meal_order

    def __str__(self) -> str:
        days = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
        return f"{days[self.day]} {'Mittag' if self.meal_order == 0 else 'Abend'}"


# ------------------------------------------------------------------------------ Gericht


@dataclass(frozen=True, slots=True)
class Category:
    axis: CategoryAxis
    name: str


@dataclass(frozen=True, slots=True)
class DishSpec:
    """Ein Gericht, angereichert um die für die geplante Woche relevanten Fakten."""

    id: int
    name: str
    portions: int  # 2 oder 3
    packable: bool
    effort: Effort
    suitable_for: SuitableFor
    rating: int | None = None  # 1..5
    categories: frozenset[Category] = frozenset()
    weeks_since_cooked: int | None = None  # None = noch nie gekocht
    offer_savings_eur: Decimal = Decimal(0)  # Ersparnis durch Angebote diese Woche
    article_ids: frozenset[int] = frozenset()

    @property
    def can_double(self) -> bool:
        """Nur 2-Portionen-Gerichte sind verdoppelbar (general_plan.md §2)."""
        return self.portions == 2

    def portions_for(self, *, doubled: bool) -> int:
        return self.portions * 2 if doubled else self.portions

    def category(self, axis: CategoryAxis) -> frozenset[str]:
        return frozenset(c.name for c in self.categories if c.axis is axis)

    def suits(self, meal: Meal) -> bool:
        if self.suitable_for is SuitableFor.BOTH:
            return True
        return self.suitable_for.value == meal.value


# --------------------------------------------------------------------------------- Slot


@dataclass(frozen=True, slots=True)
class SlotSpec:
    """Ein Slot des Wochenrasters: der Bedarf, den ein Gericht decken muss."""

    key: SlotKey
    eaters_home: int = 2  # 0..2
    packed_portions: int = 0  # 0..2, wird hier gekocht und mitgenommen
    time_budget: TimeBudget = TimeBudget.PLENTY
    special: SlotSpecial = SlotSpecial.NONE
    pinned: bool = False

    @property
    def demand(self) -> int:
        """Portionen, die dieser Slot braucht."""
        return self.eaters_home + self.packed_portions

    @property
    def needs_cooking(self) -> bool:
        if self.special is SlotSpecial.EATING_OUT:
            return False
        return self.demand > 0

    @property
    def counts_for_shopping(self) -> bool:
        """FROM_PANTRY-Slots liefern keine Zutaten für die Einkaufsliste (Plan §4)."""
        return self.special is SlotSpecial.NONE


# --------------------------------------------------------------------------- Zuweisung


@dataclass(frozen=True, slots=True)
class Assignment:
    """Tagged Union: was steht in diesem Slot?"""

    kind: AssignmentKind = AssignmentKind.EMPTY
    dish_id: int | None = None
    doubled: bool = False
    leftover_source: SlotKey | None = None
    portions_used: int | None = None
    score: ScoreBreakdown | None = None

    @classmethod
    def dish(
        cls, dish_id: int, *, doubled: bool = False, score: ScoreBreakdown | None = None
    ) -> Self:
        return cls(AssignmentKind.DISH, dish_id=dish_id, doubled=doubled, score=score)

    @classmethod
    def leftover(
        cls,
        source: SlotKey,
        dish_id: int,
        portions: int,
        *,
        score: ScoreBreakdown | None = None,
    ) -> Self:
        return cls(
            AssignmentKind.LEFTOVER,
            dish_id=dish_id,
            leftover_source=source,
            portions_used=portions,
            score=score,
        )

    @classmethod
    def pantry(cls) -> Self:
        return cls(AssignmentKind.PANTRY)

    @classmethod
    def empty(cls) -> Self:
        return cls(AssignmentKind.EMPTY)

    @property
    def is_empty(self) -> bool:
        return self.kind is AssignmentKind.EMPTY

    @property
    def cooks(self) -> bool:
        """True, wenn hier gekocht wird - nur dann fallen Zutaten an."""
        return self.kind is AssignmentKind.DISH

    @property
    def choice(self) -> tuple:
        """Die *Wahl* ohne ihre Begründung.

        Zwei Zuweisungen auf dasselbe Gericht sind dieselbe Wahl, auch wenn ihre
        Score-Begruendungen aus verschiedenen Planungslaeufen stammen. Ohne diese
        Unterscheidung würde "neu würfeln" dasselbe Gericht zurückwürfeln.
        """
        return (
            self.kind,
            self.dish_id,
            self.doubled,
            self.leftover_source,
            self.portions_used,
        )

    def same_choice(self, other: Assignment) -> bool:
        return self.choice == other.choice


# --------------------------------------------------------------------------------- Score


@dataclass(frozen=True, slots=True)
class Contribution:
    """Ein benannter Score-Beitrag. Die Begründung *ist* der Score (ARCHITECTURE §4)."""

    rule: str
    delta: float
    text: str


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    total: float
    contributions: tuple[Contribution, ...] = ()

    @classmethod
    def of(cls, contributions: list[Contribution]) -> Self:
        kept = tuple(c for c in contributions if c.delta != 0 or c.rule == "base")
        return cls(round(sum(c.delta for c in kept), 3), kept)

    def reasons(self) -> tuple[str, ...]:
        """Die Begründung, positive Beiträge zuerst - für UI und CLI."""
        ordered = sorted(self.contributions, key=lambda c: -c.delta)
        return tuple(c.text for c in ordered if c.rule != "base")


@dataclass(frozen=True, slots=True)
class Eligibility:
    ok: bool
    reasons: tuple[str, ...] = ()

    @classmethod
    def yes(cls) -> Self:
        return cls(True)

    @classmethod
    def no(cls, *reasons: str) -> Self:
        return cls(False, tuple(reasons))


@dataclass(frozen=True, slots=True)
class Candidate:
    """Ein Vorschlag für einen Slot - Gericht, verdoppeltes Gericht oder Reste."""

    assignment: Assignment
    label: str
    score: ScoreBreakdown
    warnings: tuple[str, ...] = ()

    @property
    def total(self) -> float:
        return self.score.total


# --------------------------------------------------------------------------------- Plan


@dataclass(frozen=True, slots=True)
class Plan:
    """Zuweisungen einer Woche. Unveränderlich; `with_` gibt einen neuen Plan zurück."""

    assignments: dict[SlotKey, Assignment] = field(default_factory=dict)

    def get(self, key: SlotKey) -> Assignment:
        return self.assignments.get(key, Assignment.empty())

    def with_(self, key: SlotKey, assignment: Assignment) -> Plan:
        merged = dict(self.assignments)
        merged[key] = assignment
        return Plan(merged)

    def without(self, key: SlotKey) -> Plan:
        """Entfernt einen Slot - *und* Reste-Karten, die aus ihm ziehen.

        Ohne diese Kaskade würde ein Reroll von "Do Abend" eine Reste-Karte am Freitag
        stehen lassen, deren Quelle es nicht mehr gibt: der PortionLedger würde das
        (korrekt) als Überziehung ablehnen.
        """
        merged = {
            k: v
            for k, v in self.assignments.items()
            if k != key and v.leftover_source != key
        }
        return Plan(merged)

    def dish_ids(self) -> set[int]:
        """Gerichte, die diese Woche *gekocht* werden (Reste zählen nicht doppelt)."""
        return {a.dish_id for a in self.assignments.values() if a.cooks and a.dish_id}

    def total_score(self) -> float:
        return round(
            sum(a.score.total for a in self.assignments.values() if a.score is not None), 3
        )

    def items(self):
        return sorted(self.assignments.items(), key=lambda kv: kv[0].index)


@dataclass(frozen=True, slots=True)
class PlanWarning:
    level: WarningLevel
    code: str
    text: str
    slot: SlotKey | None = None


# ----------------------------------------------------------------------------- Snapshot


@dataclass(frozen=True, slots=True)
class PlanningSnapshot:
    """Alles, was der Planer wissen muss - eingefroren, ohne DB und ohne Uhr."""

    slots: tuple[SlotSpec, ...]
    dishes: tuple[DishSpec, ...]
    weights: PlannerWeights
    week_start: date
    leftover_shelf_life_days: int = 2

    def __post_init__(self) -> None:
        if len({s.key for s in self.slots}) != len(self.slots):
            raise ValueError("Doppelte Slots im Snapshot")

    def slot(self, key: SlotKey) -> SlotSpec:
        for s in self.slots:
            if s.key == key:
                return s
        raise KeyError(key)

    def dish(self, dish_id: int) -> DishSpec:
        for d in self.dishes:
            if d.id == dish_id:
                return d
        raise KeyError(dish_id)

    def dish_or_none(self, dish_id: int | None) -> DishSpec | None:
        if dish_id is None:
            return None
        try:
            return self.dish(dish_id)
        except KeyError:
            return None

    def date_of(self, key: SlotKey) -> date:
        from datetime import timedelta

        return self.week_start + timedelta(days=key.day)


# ------------------------------------------------------------------------ Einkaufsliste


@dataclass(frozen=True, slots=True)
class IngredientSpec:
    article_id: int
    quantity: Decimal | None
    unit: Unit


@dataclass(frozen=True, slots=True)
class ShoppingLine:
    article_id: int
    quantity: Decimal | None
    unit: Unit
    from_dish_ids: tuple[int, ...]
    is_staple: bool


@dataclass(frozen=True, slots=True)
class ShoppingListDraft:
    lines: tuple[ShoppingLine, ...]
    skipped_staples: tuple[int, ...] = ()


# Import am Dateiende, weil `PlannerWeights` `Contribution` nicht braucht, `DishSpec`
# aber `PlannerWeights` in der Signatur von `PlanningSnapshot` referenziert.
from .weights import PlannerWeights  # noqa: E402

__all__ = [
    "Assignment",
    "Candidate",
    "Category",
    "Contribution",
    "DishSpec",
    "Eligibility",
    "IngredientSpec",
    "Plan",
    "PlanWarning",
    "PlannerWeights",
    "PlanningSnapshot",
    "ScoreBreakdown",
    "ShoppingLine",
    "ShoppingListDraft",
    "SlotKey",
    "SlotSpec",
    "replace",
]
