"""Plan -> Einkaufsliste (general_plan.md §5 Phase 1)."""

from __future__ import annotations

from decimal import Decimal

from conftest import dish, full_week, slot, snapshot
from mealplan.domain.enums import Meal, SlotSpecial, Unit
from mealplan.domain.model import Assignment, IngredientSpec, Plan, SlotKey
from mealplan.domain.shopping import build_shopping_list

REIS, KAESE, ZUCCHINI, SALZ = 1, 2, 3, 4

INGREDIENTS = {
    1: [  # Hirtenkäse-Reispfanne
        IngredientSpec(REIS, Decimal("250"), Unit.G),
        IngredientSpec(KAESE, Decimal("200"), Unit.G),
        IngredientSpec(ZUCCHINI, Decimal("1"), Unit.STUECK),
        IngredientSpec(SALZ, None, Unit.G),
    ],
    2: [  # Lachs (2 Portionen)
        IngredientSpec(ZUCCHINI, Decimal("2"), Unit.STUECK),
    ],
    4: [  # Linsencurry
        IngredientSpec(REIS, Decimal("0.2"), Unit.KG),
    ],
}
UNITS = {REIS: Unit.G, KAESE: Unit.G, ZUCCHINI: Unit.STUECK, SALZ: Unit.G}


def build(plan, snap, **kwargs):
    return build_shopping_list(
        plan, snap, ingredients=INGREDIENTS, article_units=UNITS, **kwargs
    )


def lines_by_article(draft):
    return {line.article_id: line for line in draft.lines}


def test_aggregates_across_dishes_and_normalises_units(sample_dishes):
    """250 g + 0,2 kg Reis = 450 g (Plan §8 Nr. 10)."""
    snap = snapshot(full_week(), sample_dishes)
    plan = (
        Plan()
        .with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(1))
        .with_(SlotKey.of(2, Meal.DINNER), Assignment.dish(4))
    )
    reis = lines_by_article(build(plan, snap))[REIS]
    assert reis.quantity == Decimal("450")
    assert reis.unit is Unit.G
    assert set(reis.from_dish_ids) == {1, 4}


def test_doubling_doubles_the_ingredients(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(2, factor=2))
    assert lines_by_article(build(plan, snap))[ZUCCHINI].quantity == Decimal("4")



def test_tripling_a_single_portion_recipe_triples_the_ingredients():
    snap = snapshot(full_week(), [dish(9, "Ramen", portions=1, allow_triple=True)])
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(9, factor=3))
    draft = build_shopping_list(
        plan,
        snap,
        ingredients={9: [IngredientSpec(REIS, Decimal("75"), Unit.G)]},
        article_units=UNITS,
    )
    assert lines_by_article(draft)[REIS].quantity == Decimal("225")


def test_a_dish_where_nobody_eats_needs_no_shopping(sample_dishes):
    slots = list(full_week())
    slots[1] = slot(0, Meal.DINNER, eaters_home=0)
    snap = snapshot(slots, sample_dishes)
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(1))
    assert build(plan, snap).lines == ()

def test_leftover_slots_need_no_shopping(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    cooked = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(1))
    with_leftover = cooked.with_(
        SlotKey.of(1, Meal.LUNCH), Assignment.leftover(SlotKey.of(0, Meal.DINNER), 1, 1)
    )
    assert build(cooked, snap).lines == build(with_leftover, snap).lines


def test_from_pantry_slots_contribute_nothing(sample_dishes):
    """Plan §4: ein Slot "aus Vorhandenem" liefert keine Zutaten."""
    slots = list(full_week())
    slots[1] = slot(0, Meal.DINNER, special=SlotSpecial.FROM_PANTRY)
    snap = snapshot(slots, sample_dishes)
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(1))
    assert build(plan, snap).lines == ()


def test_staples_are_hidden_but_reported(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(1))
    draft = build(plan, snap, staples=frozenset({SALZ}))
    assert SALZ not in lines_by_article(draft)
    assert draft.skipped_staples == (SALZ,)


def test_a_staple_can_be_pulled_back_in(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(1))
    draft = build(plan, snap, staples=frozenset({SALZ}), include_staples=frozenset({SALZ}))
    assert lines_by_article(draft)[SALZ].quantity is None  # "nach Bedarf"


def test_open_quantities_survive_aggregation(sample_dishes):
    snap = snapshot(full_week(), sample_dishes)
    plan = Plan().with_(SlotKey.of(0, Meal.DINNER), Assignment.dish(1))
    draft = build(plan, snap, include_staples=frozenset({SALZ}))
    assert lines_by_article(draft)[SALZ].quantity is None
