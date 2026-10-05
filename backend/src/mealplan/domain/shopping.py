"""Plan -> aggregierte Einkaufsliste (general_plan.md §5 Phase 1, §8 Nr. 10).

Nur gekochte Gerichte erzeugen Bedarf: Reste-Karten nicht (schon eingekauft),
FROM_PANTRY-Slots nicht (ausdruecklich "aus Vorhandenem"), EATING_OUT nicht.

Verdoppelte Gerichte verdoppeln die Zutatenmengen. Grundvorrat-Artikel (Salz, Oel,
Gewuerze) werden herausgefiltert und separat gemeldet, damit die UI sie auf Wunsch
nachtraeglich anbieten kann.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from .enums import Unit
from .model import (
    IngredientSpec,
    Plan,
    PlanningSnapshot,
    ShoppingLine,
    ShoppingListDraft,
    SlotKey,
)
from .units import Quantity, aggregate


def build_shopping_list(
    plan: Plan,
    snap: PlanningSnapshot,
    *,
    ingredients: dict[int, list[IngredientSpec]],
    article_units: dict[int, Unit],
    staples: frozenset[int] = frozenset(),
    include_staples: frozenset[int] = frozenset(),
) -> ShoppingListDraft:
    """`ingredients` ist dish_id -> Zutaten, `article_units` die kanonische Einheit.

    `staples` sind Grundvorrat-Artikel; `include_staples` überschreibt das pro Artikel
    ("Salz ist leer, bitte doch mit drauf").
    """
    collected: dict[int, list[Quantity]] = defaultdict(list)
    origins: dict[int, list[int]] = defaultdict(list)

    for key, assignment in plan.items():
        if not assignment.cooks or assignment.dish_id is None:
            continue
        if not _counts(key, snap):
            continue
        for ingredient in ingredients.get(assignment.dish_id, []):
            unit = article_units.get(ingredient.article_id, ingredient.unit)
            quantity = Quantity(ingredient.quantity, ingredient.unit).to(unit)
            collected[ingredient.article_id].append(quantity.scaled(assignment.factor))
            if assignment.dish_id not in origins[ingredient.article_id]:
                origins[ingredient.article_id].append(assignment.dish_id)

    lines: list[ShoppingLine] = []
    skipped: list[int] = []
    for article_id, quantities in collected.items():
        is_staple = article_id in staples
        if is_staple and article_id not in include_staples:
            skipped.append(article_id)
            continue
        unit = article_units.get(article_id, quantities[0].unit)
        total = aggregate(quantities, unit)
        lines.append(
            ShoppingLine(
                article_id=article_id,
                quantity=total.amount,
                unit=unit,
                from_dish_ids=tuple(origins[article_id]),
                is_staple=is_staple,
            )
        )

    lines.sort(key=lambda line: (not line.is_staple, line.article_id))
    return ShoppingListDraft(tuple(lines), tuple(sorted(skipped)))


def _counts(key: SlotKey, snap: PlanningSnapshot) -> bool:
    try:
        return snap.slot(key).counts_for_shopping
    except KeyError:
        return False


def portions_cooked(plan: Plan, snap: PlanningSnapshot) -> int:
    total = 0
    for _key, assignment in plan.items():
        if assignment.cooks and assignment.dish_id is not None:
            dish = snap.dish(assignment.dish_id)
            total += dish.portions_for(assignment.factor)
    return total


def estimated_savings(plan: Plan, snap: PlanningSnapshot) -> Decimal:
    """Summe der Angebots-Ersparnis der geplanten Gerichte (Phase 2)."""
    total = Decimal(0)
    for _key, assignment in plan.items():
        if assignment.cooks and assignment.dish_id is not None:
            total += snap.dish(assignment.dish_id).offer_savings_eur
    return total
