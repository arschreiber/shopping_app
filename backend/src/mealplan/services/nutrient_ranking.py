"""Artikel-Rangliste je Nährstoff (Logik: domain/nutrient_ranking.py)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..db.mappers import article_nutrition_index
from ..domain.enums import Unit
from ..domain.micronutrients import article_amounts
from ..domain.nutrient_ranking import NUTRIENTS, ArticleValues, Basis, Ranking, Source, rank
from .articles import ValidationError
from .nutrients import micro_index

MACRO_FIELDS = ("kcal", "carbs_g", "fat_g", "protein_g")


def article_values(session: Session) -> list[ArticleValues]:
    """Alle Artikel mit Makros (Etikett, sonst BLS) und Mikros (Etikett vor BLS)."""
    macros = article_nutrition_index(session)
    micros, _ = micro_index(session)
    rows = session.execute(
        select(
            m.Article.id,
            m.Article.canonical_name,
            m.Article.unit,
            m.Article.kcal,
            m.Article.carbs_g,
            m.Article.fat_g,
            m.Article.protein_g,
            m.Article.bls_grams_per_unit,
        )
    ).all()
    out: list[ArticleValues] = []
    for article_id, name, unit, kcal, carbs, fat, protein, piece_grams in rows:
        values: dict[str, tuple[Decimal, Source]] = {}
        own = dict(zip(MACRO_FIELDS, (kcal, carbs, fat, protein), strict=True))
        if any(value is not None for value in own.values()):
            # Eigene Angaben: nur, was wirklich eingetragen ist - keine geratene Null.
            for code, value in own.items():
                if value is not None:
                    values[code] = (Decimal(value), "label")
        elif (facts := macros.get(article_id)) is not None:
            for code in MACRO_FIELDS:
                values[code] = (getattr(facts.per_basis, code), "bls")
        if (micro := micros.get(article_id)) is not None:
            values.update(article_amounts(micro))
        out.append(
            ArticleValues(
                article_id=article_id,
                name=name,
                unit=Unit(unit),
                values=values,
                piece_grams=piece_grams if Unit(unit) is Unit.STUECK else None,
            )
        )
    return out


def ranking(session: Session, code: str, basis: Basis) -> Ranking:
    if code not in NUTRIENTS:
        raise ValidationError(f"Unbekannter Nährstoff '{code}'")
    return rank(code, article_values(session), basis)
