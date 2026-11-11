"""Nährstoffe und welche Artikel am meisten davon tragen (domain/nutrient_ranking.py)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from ...domain.micronutrients import MICRONUTRIENTS, REFERENCE_PERSON
from ...domain.nutrient_ranking import MACROS, NUTRIENTS
from ...services import nutrient_ranking as service
from ..deps import SessionDep
from ..schemas.common import (
    NutrientDefOut,
    NutrientRankingOut,
    RankedArticleOut,
    UnrankedArticleOut,
)

router = APIRouter(prefix="/api/nutrients", tags=["nutrients"])


def _def_out(nutrient) -> NutrientDefOut:
    return NutrientDefOut(
        code=nutrient.code,
        label=nutrient.label,
        unit=nutrient.unit,
        group=nutrient.group,
        reference=nutrient.reference,
        kind=nutrient.kind,
    )


@router.get("", response_model=list[NutrientDefOut])
def list_nutrients() -> list[NutrientDefOut]:
    """Makros, dann Mikros - in der Reihenfolge der Nährwert-Tabellen."""
    return [_def_out(n) for n in (*MACROS, *MICRONUTRIENTS)]


@router.get("/{code}/articles", response_model=NutrientRankingOut)
def ranking(
    session: SessionDep, code: str, basis: Literal["mass", "kcal"] = "mass"
) -> NutrientRankingOut:
    """Alle Artikel nach Menge sortiert: je 100 g/ml (Standard) oder je 100 kcal."""
    from ...integrations.nutrients.bls import ATTRIBUTION

    result = service.ranking(session, code, basis)
    return NutrientRankingOut(
        nutrient=_def_out(NUTRIENTS[code]),
        basis=result.basis,
        entries=[
            RankedArticleOut(
                article_id=e.article_id,
                name=e.name,
                amount=e.amount,
                per=e.per,
                share=e.share,
                source=e.source,
            )
            for e in result.entries
        ],
        missing=[
            UnrankedArticleOut(article_id=u.article_id, name=u.name, reason=u.reason)
            for u in result.missing
        ],
        reference_person=REFERENCE_PERSON,
        attribution=ATTRIBUTION,
    )
