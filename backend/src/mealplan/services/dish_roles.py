"""Beilage und Protein fürs Gericht-Formular (Logik: domain/dish_roles.py).

Gelernt wird bei jedem Aufruf neu aus den gespeicherten Gerichten - bei ein paar Dutzend
Gerichten kostet das nichts, und es gibt keinen zweiten Stand, der veralten kann.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.mappers import article_nutrition_index, ingredients_by_dish
from ..domain.dish_roles import (
    ROLE_AXES,
    Detection,
    LearnDish,
    RoleLine,
    detect_roles,
    learn_roles,
)
from ..domain.enums import CategoryAxis, Unit
from ..domain.model import IngredientSpec
from ..domain.nutrition import ArticleNutrition, dish_nutrition


def _role_lines(
    rows: list[IngredientSpec],
    facts: dict[int, ArticleNutrition],
    names: dict[int, str],
) -> list[RoleLine]:
    """Was jede Zutat im ganzen Gericht beiträgt - Zutaten ohne Angaben mit null."""
    totals = dict(dish_nutrition(rows, facts, portions=1).contributions)
    lines: list[RoleLine] = []
    for article_id in dict.fromkeys(row.article_id for row in rows):
        part = totals.get(article_id)
        fact = facts.get(article_id)
        per_100 = fact.per_basis if fact is not None and fact.unit is not Unit.STUECK else None
        lines.append(
            RoleLine(
                article_id=article_id,
                name=names.get(article_id, f"#{article_id}"),
                carbs_g=part.carbs_g if part else Decimal(0),
                protein_g=part.protein_g if part else Decimal(0),
                carbs_density=per_100.carbs_g if per_100 else None,
                protein_density=per_100.protein_g if per_100 else None,
            )
        )
    return lines


def _context(session: Session):
    facts = article_nutrition_index(session)
    names = dict(session.execute(select(m.Article.id, m.Article.canonical_name)).all())
    return facts, names


def learned_roles(session: Session) -> dict[CategoryAxis, dict[int, str]]:
    facts, names = _context(session)
    return _learned(session, facts, names)


def _learned(session, facts, names) -> dict[CategoryAxis, dict[int, str]]:
    rows = session.execute(
        select(m.DishCategory.dish_id, m.Category.axis, m.Category.name)
        .join(m.Category, m.Category.id == m.DishCategory.category_id)
        .join(m.Dish, m.Dish.id == m.DishCategory.dish_id)
        .where(m.Dish.archived.is_(False))
        .order_by(m.DishCategory.dish_id)
    ).all()
    categories: dict[int, dict[CategoryAxis, str]] = {}
    for dish_id, axis, name in rows:
        if CategoryAxis(axis) in ROLE_AXES:
            categories.setdefault(dish_id, {})[CategoryAxis(axis)] = name
    lines = ingredients_by_dish(session)
    return learn_roles(
        LearnDish(
            categories=cats,
            lines=tuple(_role_lines(lines.get(dish_id, []), facts, names)),
        )
        for dish_id, cats in categories.items()
    )


def detect(session: Session, rows: list[IngredientSpec]) -> dict[CategoryAxis, Detection]:
    """Beilage und Protein für ein (auch ungespeichertes) Gericht."""
    facts, names = _context(session)
    existing: dict[CategoryAxis, list[str]] = {axis: [] for axis in ROLE_AXES}
    for axis, name in session.execute(select(m.Category.axis, m.Category.name)).all():
        if CategoryAxis(axis) in existing:
            existing[CategoryAxis(axis)].append(name)
    return detect_roles(
        _role_lines(rows, facts, names), _learned(session, facts, names), existing
    )
