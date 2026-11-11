"""Artikel-Rangliste je Nährstoff (domain/nutrient_ranking.py)."""

from __future__ import annotations

from decimal import Decimal as D

import pytest

from mealplan.domain.enums import Unit
from mealplan.domain.nutrient_ranking import ArticleValues, rank


def article(article_id, name, unit=Unit.G, piece_grams=None, **values):
    return ArticleValues(
        article_id=article_id,
        name=name,
        unit=unit,
        values={code: (D(str(v)), "bls") for code, v in values.items()},
        piece_grams=None if piece_grams is None else D(str(piece_grams)),
    )


PAPRIKA = article(1, "Paprika", VITC=160, kcal=20)
BROKKOLI = article(2, "Brokkoli", VITC=81, kcal=34)
ORANGENSAFT = article(3, "Orangensaft", Unit.ML, VITC=40, kcal=45)
KIWI = article(4, "Kiwi", Unit.STUECK, piece_grams=75, VITC=33, kcal=40)  # je Stück
SALZ = article(5, "Salz", NACL=100, kcal=0)
NUDELN = article(6, "Nudeln", kcal=350)


def test_per_100g_sorted_from_most_to_least():
    result = rank("VITC", [BROKKOLI, ORANGENSAFT, PAPRIKA, KIWI, NUDELN])
    assert [e.name for e in result.entries] == ["Paprika", "Brokkoli", "Kiwi", "Orangensaft"]
    assert [e.per for e in result.entries] == ["100 g", "100 g", "100 g", "100 ml"]
    kiwi = next(e for e in result.entries if e.name == "Kiwi")
    assert kiwi.amount == D(44)  # 33 mg je 75-g-Stück
    assert result.entries[0].share == D(145)  # 160 von 110 mg


def test_unknown_values_are_listed_apart_not_as_zero():
    result = rank("VITC", [PAPRIKA, NUDELN])
    assert [e.name for e in result.entries] == ["Paprika"]
    assert [(u.name, u.reason) for u in result.missing] == [("Nudeln", "keine Angabe")]


def test_piece_without_weight_cannot_be_compared_per_100g():
    bare = article(7, "Ei", Unit.STUECK, VITC=0, kcal=80)
    assert [u.reason for u in rank("VITC", [bare]).missing] == ["ohne Stückgewicht"]
    assert rank("VITC", [bare], "kcal").entries[0].per == "100 kcal"


def test_per_100_kcal_is_nutrient_density():
    result = rank("VITC", [BROKKOLI, PAPRIKA, ORANGENSAFT], "kcal")
    assert [e.name for e in result.entries] == ["Paprika", "Brokkoli", "Orangensaft"]
    assert result.entries[0].amount == D("800.0")
    assert result.entries[0].per == "100 kcal"


def test_no_calories_means_no_density():
    result = rank("NACL", [SALZ], "kcal")
    assert result.entries == ()
    assert [u.reason for u in result.missing] == ["ohne Kalorien"]


def test_kcal_per_kcal_falls_back_to_mass():
    result = rank("kcal", [PAPRIKA, NUDELN], "kcal")
    assert result.basis == "mass"
    assert [e.name for e in result.entries] == ["Nudeln", "Paprika"]
    assert result.entries[0].share is None  # Makros ohne Tageswert


def test_unknown_code_is_rejected():
    with pytest.raises(KeyError):
        rank("NOPE", [PAPRIKA])
