"""Nährwerte der Woche: Tagessumme je Person und Ø je Portion (domain/week_nutrition.py)."""

from __future__ import annotations

from decimal import Decimal as D

from mealplan.domain.enums import Meal
from mealplan.domain.micronutrients import MicroValue, sum_micros
from mealplan.domain.nutrition import Nutrients
from mealplan.domain.week_nutrition import MealEntry, week_nutrition


def micro(code, amount, partial=False):
    return MicroValue(code=code, amount=D(str(amount)), partial=partial, share=None)


def meal(day, meal_, kcal, protein, *, vit_c=None, complete=True):
    micros = () if vit_c is None else (micro("VITC", vit_c),)
    return MealEntry(
        day=day,
        meal=meal_,
        dish_id=day * 10 + (0 if meal_ is Meal.LUNCH else 1),
        nutrients=Nutrients(kcal=D(kcal), protein_g=D(protein)),
        micros=micros,
        complete=complete,
    )


def test_day_is_lunch_plus_dinner_for_one_person():
    result = week_nutrition([meal(1, Meal.DINNER, 895, 44.5), meal(1, Meal.LUNCH, 898, 47)])
    tuesday = result.days[1]
    assert tuesday.meal_count == 2
    assert tuesday.nutrients.kcal == D(1793)
    assert tuesday.nutrients.protein_g == D("91.5")
    assert [m.meal for m in result.meals] == [Meal.LUNCH, Meal.DINNER]
    assert result.days[0].meal_count == 0


def test_average_counts_every_meal_once():
    result = week_nutrition(
        [meal(1, Meal.LUNCH, 900, 40), meal(1, Meal.DINNER, 700, 30), meal(2, Meal.LUNCH, 800, 50)]
    )
    assert result.average.meal_count == 3
    assert result.average.nutrients.kcal == D(800)
    assert result.average.nutrients.protein_g == D(40)


def test_incomplete_meal_makes_the_sum_a_lower_bound():
    result = week_nutrition([meal(3, Meal.LUNCH, 800, 40, complete=False)])
    assert result.days[3].complete is False
    assert result.average.complete is False


def test_micros_add_up_and_shares_follow():
    summed = sum_micros([(micro("VITC", 60),), (micro("VITC", 50, partial=True),)])
    vit_c = next(v for v in summed if v.code == "VITC")
    assert vit_c.amount == D(110)
    assert vit_c.partial is True
    assert vit_c.share is not None and vit_c.share > 0

    averaged = sum_micros([(micro("VITC", 60),), (micro("VITC", 40),)], divisor=D(2))
    assert next(v for v in averaged if v.code == "VITC").amount == D(50)


def test_meal_without_micros_marks_every_value_partial():
    summed = sum_micros([(micro("VITC", 60),), ()])
    assert all(value.partial for value in summed)
    assert sum_micros([(), ()]) == ()
