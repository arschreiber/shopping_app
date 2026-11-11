"""Nährwerte einer Woche: je Tag für eine Person und Ø je Portion (pure).

Grundannahme: Wer an einer Mahlzeit isst, isst *eine* Portion des Gerichts - zuhause oder
mitgenommen. Ein Tag ist darum für jede Person gleich: Mittag plus Abend, je Portion.
Frühstück und Snacks plant die App nicht, die Tageswerte zeigen also, was die geplanten
Mahlzeiten beitragen.

Was keine Werte hat - auswärts, Vorrat, ungeplant, ausgefallen - zählt nicht mit. Der
Tag sagt dann, wie viele seiner Mahlzeiten erfasst sind, statt eine niedrige Summe als
leichten Tag auszugeben. Der Wochen-Ø zählt jede geplante Mahlzeit einmal, egal für wie
viele Personen gekocht wurde: "so sieht meine Portion im Schnitt aus".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from .enums import Meal
from .micronutrients import MicroValue, sum_micros
from .nutrition import Nutrients

MEALS_PER_DAY = 2
DAYS = range(7)


@dataclass(frozen=True, slots=True)
class MealEntry:
    """Eine geplante Mahlzeit mit den Werten einer Portion ihres Gerichts."""

    day: int
    meal: Meal
    dish_id: int
    nutrients: Nutrients
    micros: tuple[MicroValue, ...]
    complete: bool  # alle Zutaten mit Angaben und Mengen


@dataclass(frozen=True, slots=True)
class NutritionSum:
    nutrients: Nutrients
    micros: tuple[MicroValue, ...]
    meal_count: int
    complete: bool  # jede gezählte Mahlzeit vollständig - sonst "mindestens"


@dataclass(frozen=True, slots=True)
class WeekNutrition:
    meals: tuple[MealEntry, ...]
    days: tuple[NutritionSum, ...]  # Index = Tag (0 = Montag), eine Person
    average: NutritionSum  # Ø je Portion über alle gezählten Mahlzeiten


def combine(entries: Sequence[MealEntry], *, average: bool = False) -> NutritionSum:
    total = Nutrients()
    for entry in entries:
        total = total + entry.nutrients
    divisor = Decimal(len(entries)) if average and entries else Decimal(1)
    return NutritionSum(
        nutrients=total.scaled(Decimal(1) / divisor).rounded(),
        micros=sum_micros((entry.micros for entry in entries), divisor=divisor),
        meal_count=len(entries),
        complete=all(entry.complete for entry in entries),
    )


def week_nutrition(entries: Sequence[MealEntry]) -> WeekNutrition:
    ordered = tuple(sorted(entries, key=lambda e: (e.day, e.meal is not Meal.LUNCH)))
    return WeekNutrition(
        meals=ordered,
        days=tuple(combine([e for e in ordered if e.day == day]) for day in DAYS),
        average=combine(ordered, average=True),
    )
