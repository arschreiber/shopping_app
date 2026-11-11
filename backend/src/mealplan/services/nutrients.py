"""BLS-Referenzen: importieren, vorschlagen, zuordnen, ein Gericht durchrechnen.

Der Ablauf alle paar Wochen (`mealplan nutrients sync`):

1. BLS einlesen - nur wenn die Datei neu ist (Prüfsumme in `setting`).
2. Entscheidungen aus `data/catalog/bls/links.json` übernehmen, für Artikel, die noch
   offen sind. So lassen sich Zuordnungen an einer Kopie der Datenbank prüfen und dann
   mit einem Befehl einspielen; was jemand in der App gewählt hat, bleibt.
3. Für alle übrigen offenen Artikel Vorschläge zeigen. Übernommen wird nichts davon.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.enums import Unit
from ..domain.micronutrients import (
    IMPORTED_CODES,
    LABEL_CODES,
    ArticleMicros,
    DishMicros,
    dish_micronutrients,
    effective_label,
)
from ..domain.model import IngredientSpec
from ..integrations.nutrients import bls
from ..matching.bls import BlsSuggestion, FoodName
from ..matching.bls import search as search_foods
from ..matching.bls import suggest as suggest_foods
from . import settings_store
from .articles import ValidationError

LOG = logging.getLogger(__name__)

KEY_BLS = "bls_import"
LINKS_FILE = "links.json"


class NutrientError(ValidationError):
    """Wird von der API wie jede Eingabe-Validierung zu einem 422."""


# ------------------------------------------------------------------------------ Import


@dataclass(frozen=True, slots=True)
class ImportResult:
    path: Path
    foods: int
    imported: bool  # False = Datei unverändert, nichts getan


def import_bls(session: Session, path: Path, *, force: bool = False) -> ImportResult:
    digest = bls.file_digest(path)
    previous = settings_store.get(session, KEY_BLS) or {}
    if not force and previous.get("sha256") == digest:
        count = session.query(m.BlsFood).count()
        if count:
            return ImportResult(path, count, imported=False)

    rows = list(bls.read_rows(path, IMPORTED_CODES))
    if not rows:
        raise NutrientError(f"{path.name} enthält keine Lebensmittel")
    session.execute(delete(m.BlsFood))
    session.add_all(
        m.BlsFood(code=row.code, name=row.name, name_en=row.name_en, nutrients=row.nutrients)
        for row in rows
    )
    settings_store.put(
        session, KEY_BLS, {"sha256": digest, "file": path.name, "foods": len(rows)}
    )
    session.flush()
    return ImportResult(path, len(rows), imported=True)


def has_foods(session: Session) -> bool:
    return session.scalar(select(m.BlsFood.code).limit(1)) is not None


# ------------------------------------------------------------------- Vorschläge, Suche


class _FoodNameCache:
    """Die ~7000 Namen einmal je Prozess und BLS-Stand.

    Der Import läuft meist in einem anderen Prozess (CLI) als der Server - darum hängt
    der Cache an der Prüfsumme in `setting`, nicht an einem Aufruf von `import_bls`.
    """

    def __init__(self) -> None:
        self.key: str | None = None
        self.names: list[FoodName] = []

    def __call__(self, session: Session) -> list[FoodName]:
        key = (settings_store.get(session, KEY_BLS) or {}).get("sha256")
        if key is None or key != self.key:
            self.names = [
                FoodName(code, name)
                for code, name in session.execute(select(m.BlsFood.code, m.BlsFood.name))
            ]
            self.key = key
        return self.names


_food_names = _FoodNameCache()


def suggestions_for(
    session: Session, article: m.Article, *, limit: int = 6
) -> list[BlsSuggestion]:
    names = [article.canonical_name, *(a.alias for a in article.aliases)]
    return suggest_foods(names, _food_names(session), limit=limit)


def search(session: Session, query: str, *, limit: int = 30) -> list[BlsSuggestion]:
    return search_foods(query, _food_names(session), limit=limit)


def open_articles(session: Session) -> list[m.Article]:
    """Artikel ohne Referenz und nicht bewusst übersprungen."""
    return list(
        session.scalars(
            select(m.Article)
            .where(m.Article.bls_code.is_(None), m.Article.bls_skip.is_(False))
            .order_by(m.Article.canonical_name)
        )
    )


def get_food(session: Session, code: str) -> m.BlsFood:
    food = session.get(m.BlsFood, code)
    if food is None:
        raise NutrientError(f"BLS-Code {code} unbekannt")
    return food


# --------------------------------------------------------------------------- Zuordnen


def link(
    session: Session,
    article: m.Article,
    code: str,
    *,
    grams_per_unit: Decimal | None = None,
) -> m.Article:
    get_food(session, code)
    if grams_per_unit is not None and grams_per_unit <= 0:
        raise NutrientError("Gramm je Einheit muss größer als 0 sein")
    if Unit(article.unit) is Unit.G:
        grams_per_unit = None  # 1 g ist 1 g
    article.bls_code = code
    article.bls_grams_per_unit = grams_per_unit
    article.bls_skip = False
    return article


def skip(session: Session, article: m.Article) -> m.Article:
    article.bls_code = None
    article.bls_grams_per_unit = None
    article.bls_skip = True
    return article


def unlink(session: Session, article: m.Article) -> m.Article:
    article.bls_code = None
    article.bls_grams_per_unit = None
    article.bls_skip = False
    return article


def find_article(session: Session, name_or_id: str) -> m.Article:
    if name_or_id.isdigit():
        article = session.get(m.Article, int(name_or_id))
    else:
        article = session.scalar(
            select(m.Article).where(m.Article.canonical_name == name_or_id)
        )
    if article is None:
        raise NutrientError(f"Artikel '{name_or_id}' nicht gefunden")
    return article


# ----------------------------------------------------------- Entscheidungen als Datei


def export_links(session: Session) -> dict[str, Any]:
    """Alle getroffenen Entscheidungen, nach Artikelname - so bleibt die Datei lesbar
    und lässt sich von Hand prüfen, bevor `apply_links` sie einspielt."""
    out: dict[str, Any] = {}
    for article in session.scalars(select(m.Article).order_by(m.Article.canonical_name)):
        if article.bls_skip:
            out[article.canonical_name] = {"skip": True}
        elif article.bls_code:
            entry: dict[str, Any] = {"code": article.bls_code}
            if article.bls_grams_per_unit is not None:
                entry["grams_per_unit"] = str(article.bls_grams_per_unit.normalize())
            food = session.get(m.BlsFood, article.bls_code)
            if food is not None:
                entry["name"] = food.name  # nur zum Lesen
            out[article.canonical_name] = entry
    return out


@dataclass(frozen=True, slots=True)
class ApplyResult:
    applied: list[str]
    kept: list[str]  # schon entschieden, Datei ignoriert
    unknown: list[str]  # Artikel gibt es (hier) nicht


def apply_links(
    session: Session, decisions: dict[str, Any], *, overwrite: bool = False
) -> ApplyResult:
    applied: list[str] = []
    kept: list[str] = []
    unknown: list[str] = []
    for name, entry in decisions.items():
        article = session.scalar(select(m.Article).where(m.Article.canonical_name == name))
        if article is None:
            unknown.append(name)
            continue
        decided = article.bls_code is not None or article.bls_skip
        if decided and not overwrite:
            kept.append(name)
            continue
        if entry.get("skip"):
            skip(session, article)
        else:
            grams = entry.get("grams_per_unit")
            link(
                session,
                article,
                entry["code"],
                grams_per_unit=Decimal(str(grams)) if grams is not None else None,
            )
        applied.append(name)
    session.flush()
    return ApplyResult(applied, kept, unknown)


def links_path(catalog_dir: Path) -> Path:
    return bls.bls_dir(catalog_dir) / LINKS_FILE


def read_links(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("articles", data)


# ----------------------------------------------------------------------- Durchrechnen


def micro_index(session: Session) -> tuple[dict[int, ArticleMicros], frozenset[int]]:
    """`({article_id: ArticleMicros}, {übersprungene article_ids})`.

    Ein Artikel zählt, sobald BLS-Referenz *oder* Etikettwerte da sind - "bewusst ohne
    Referenz" ist dann keine Lücke mehr, wenn das Etikett einspringt.
    """
    rows = session.execute(
        select(
            m.Article.id,
            m.Article.unit,
            m.Article.bls_grams_per_unit,
            m.Article.bls_skip,
            m.Article.label_micros,
            m.BlsFood.nutrients,
        ).outerjoin(m.BlsFood, m.BlsFood.code == m.Article.bls_code)
    ).all()
    facts: dict[int, ArticleMicros] = {}
    skipped: set[int] = set()
    for article_id, unit, grams, is_skipped, label, nutrients in rows:
        if is_skipped:
            skipped.add(article_id)
        if nutrients is None and not label:
            continue
        facts[article_id] = ArticleMicros(
            article_id=article_id,
            unit=Unit(unit),
            per_100g={code: Decimal(str(v)) for code, v in (nutrients or {}).items()},
            grams_per_unit=grams,
            label=effective_label(parse_label(label)),
        )
    return facts, frozenset(skipped)


def parse_label(raw: dict[str, Any] | None) -> dict[str, Decimal]:
    return {code: Decimal(str(value)) for code, value in (raw or {}).items()}


def clean_label(values: dict[str, Decimal] | None) -> dict[str, str] | None:
    """Für die Spalte: nur bekannte Codes, keine leeren Werte; leer heißt NULL."""
    if not values:
        return None
    unknown = set(values) - set(LABEL_CODES)
    if unknown:
        raise NutrientError(f"Unbekannte Nährstoffe: {', '.join(sorted(unknown))}")
    out: dict[str, str] = {}
    for code, value in values.items():
        if value is None:
            continue
        if value < 0:
            raise NutrientError(f"{code} darf nicht negativ sein")
        out[code] = format(Decimal(value).normalize(), "f")
    return out or None


def dish_micros(
    session: Session, lines: list[IngredientSpec], *, portions: int
) -> DishMicros:
    facts, skipped = micro_index(session)
    return dish_micronutrients(lines, facts, skipped=skipped, portions=portions)
