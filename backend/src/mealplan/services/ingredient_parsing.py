"""Deterministischer Zutaten-Parser (ARCHITECTURE.md §7, ersetzt die LLM-Schnellerfassung).

Eine Zeile pro Zutat: `250 g Basmatireis`. Der Parser ist regelbasiert und
reproduzierbar - Mengen-Regex + Einheiten-Synonyme + Fuzzy-Match gegen den
Artikelkorpus. Kein Modell, kein Netz, keine Ueberraschungen.

Erkannt werden u. a.:
    250 g Basmatireis
    1 Zucchini
    2 Dosen Kichererbsen
    Salz
    Olivenöl nach Bedarf
    1/2 Packung Hirtenkäse
    Hirtenkäse 200g
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ..domain.enums import Unit
from ..domain.units import DIMENSION_OF, Dimension, trim

# Einheiten-Synonyme -> (kanonische Einheit, Faktor auf die Basiseinheit)
UNIT_SYNONYMS: dict[str, tuple[Unit, Decimal]] = {
    "g": (Unit.G, Decimal(1)),
    "gr": (Unit.G, Decimal(1)),
    "gramm": (Unit.G, Decimal(1)),
    "kg": (Unit.G, Decimal(1000)),
    "kilo": (Unit.G, Decimal(1000)),
    "kilogramm": (Unit.G, Decimal(1000)),
    "ml": (Unit.ML, Decimal(1)),
    "cl": (Unit.ML, Decimal(10)),
    "l": (Unit.ML, Decimal(1000)),
    "liter": (Unit.ML, Decimal(1000)),
    "el": (Unit.ML, Decimal(15)),  # Esslöffel
    "tl": (Unit.ML, Decimal(5)),  # Teelöffel
    "stk": (Unit.STUECK, Decimal(1)),
    "stück": (Unit.STUECK, Decimal(1)),
    "stueck": (Unit.STUECK, Decimal(1)),
    "st": (Unit.STUECK, Decimal(1)),
    "x": (Unit.STUECK, Decimal(1)),
    "dose": (Unit.STUECK, Decimal(1)),
    "dosen": (Unit.STUECK, Decimal(1)),
    "packung": (Unit.STUECK, Decimal(1)),
    "packungen": (Unit.STUECK, Decimal(1)),
    "pck": (Unit.STUECK, Decimal(1)),
    "glas": (Unit.STUECK, Decimal(1)),
    "gläser": (Unit.STUECK, Decimal(1)),
    "becher": (Unit.STUECK, Decimal(1)),
    "beutel": (Unit.STUECK, Decimal(1)),
    "bund": (Unit.STUECK, Decimal(1)),
    "zehe": (Unit.STUECK, Decimal(1)),
    "zehen": (Unit.STUECK, Decimal(1)),
    "scheibe": (Unit.STUECK, Decimal(1)),
    "scheiben": (Unit.STUECK, Decimal(1)),
    "prise": (Unit.STUECK, Decimal(1)),
    "prisen": (Unit.STUECK, Decimal(1)),
}

# Wörter, die "keine Menge" bedeuten und aus dem Namen fliegen.
_OPEN_MARKERS = ("nach bedarf", "nach geschmack", "etwas", "ein wenig", "beliebig")

_NUMBER = r"(?:\d+\s*[/⁄]\s*\d+|\d+[.,]\d+|\d+)"
_LEADING = re.compile(
    rf"^\s*(?P<amount>{_NUMBER})\s*(?P<unit>[a-zA-ZäöüÄÖÜ]+\.?)?\s*(?P<rest>.*)$"
)
_TRAILING = re.compile(
    rf"^(?P<rest>.+?)[,;]?\s*(?P<amount>{_NUMBER})\s*(?P<unit>[a-zA-ZäöüÄÖÜ]+)\s*$"
)
_FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3"}


@dataclass(frozen=True, slots=True)
class ParsedLine:
    """Ergebnis einer Zeile. `article_id is None` -> Chip "als neuen Artikel anlegen"."""

    raw: str
    name: str
    quantity: Decimal | None
    unit: Unit
    article_id: int | None = None
    article_name: str | None = None
    confidence: float = 0.0
    note: str | None = None
    unit_explicit: bool = False

    @property
    def is_new_article(self) -> bool:
        return self.article_id is None


def parse_lines(
    text: str,
    articles: dict[int, list[str]] | None = None,
    article_units: dict[int, Unit] | None = None,
) -> list[ParsedLine]:
    """Parst einen Textblock. `articles` ist `{id: [kanonischer Name, Alias, ...]}`."""
    out: list[ParsedLine] = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-•*").strip()
        if not line:
            continue
        out.append(parse_line(line, articles, article_units))
    return out


def parse_line(
    raw: str,
    articles: dict[int, list[str]] | None = None,
    article_units: dict[int, Unit] | None = None,
) -> ParsedLine:
    line = raw.strip()
    for glyph, replacement in _FRACTIONS.items():
        line = line.replace(glyph, replacement)

    note: str | None = None
    lowered = line.lower()
    open_quantity = False
    for marker in _OPEN_MARKERS:
        if marker in lowered:
            open_quantity = True
            index = lowered.index(marker)
            line = (line[:index] + line[index + len(marker) :]).strip(" ,;")
            note = marker
            break

    quantity, unit, name, explicit = _split(line)
    if open_quantity:
        quantity = None
    name = name.strip(" ,;.-")

    article_id, article_name, confidence = _match(name, articles)

    # Ohne Menge *und* ohne Einheit ("Salz") trägt die Zeile keine Einheiteninformation.
    # Dann gilt die Einheit des Artikels - eine Kollision zu melden wäre hier nur
    # Bürokratie. Sobald eine Menge im Spiel ist, bleibt der Konflikt ein Konflikt
    # (2 Tomaten sind nicht 2 g Tomaten).
    if quantity is None and not explicit and article_id is not None and article_units:
        unit = article_units.get(article_id, unit)

    return ParsedLine(
        raw=raw.strip(),
        name=name,
        quantity=quantity,
        unit=unit,
        article_id=article_id,
        article_name=article_name,
        confidence=confidence,
        note=note,
        unit_explicit=explicit,
    )


def _split(line: str) -> tuple[Decimal | None, Unit, str, bool]:
    """Zerlegt in (Menge, Einheit, Name, Einheit-stand-in-der-Zeile)."""
    match = _LEADING.match(line)
    if match:
        amount = _to_decimal(match.group("amount"))
        token_raw = (match.group("unit") or "").strip()
        token = token_raw.rstrip(".").lower()
        rest = match.group("rest").strip()

        if token in UNIT_SYNONYMS:
            unit, factor = UNIT_SYNONYMS[token]
            # "2 x 400 g Tomaten" -> 800 g: die zweite Menge multipliziert die erste.
            if rest and _LEADING.match(rest) and _starts_with_number(rest):
                inner_amount, inner_unit, inner_name, inner_explicit = _split(rest)
                if inner_amount is not None and amount is not None:
                    return _scale(inner_amount, amount), inner_unit, inner_name, inner_explicit
            if rest:
                return _scale(amount, factor), unit, rest, True
            return _scale(amount, factor), unit, "", True

        # Zahl ohne Einheit: "1 Zucchini" -> 1 Stueck, das Wort gehört zum Namen.
        name = f"{token_raw} {rest}".strip()
        if name:
            return amount, Unit.STUECK, name, False

    trailing = _TRAILING.match(line)
    if trailing:
        token = trailing.group("unit").rstrip(".").lower()
        if token in UNIT_SYNONYMS:
            unit, factor = UNIT_SYNONYMS[token]
            amount = _to_decimal(trailing.group("amount"))
            return _scale(amount, factor), unit, trailing.group("rest"), True

    return None, Unit.STUECK, line, False


def _starts_with_number(text: str) -> bool:
    return bool(re.match(rf"^\s*{_NUMBER}", text))


def _to_decimal(text: str) -> Decimal | None:
    cleaned = text.replace(" ", "").replace(",", ".").replace("⁄", "/")
    try:
        if "/" in cleaned:
            numerator, denominator = cleaned.split("/", 1)
            return Decimal(numerator) / Decimal(denominator)
        return Decimal(cleaned)
    except (InvalidOperation, ZeroDivisionError, ValueError):
        return None


def _scale(amount: Decimal | None, factor: Decimal) -> Decimal | None:
    if amount is None:
        return None
    return _tidy(amount * factor)


def _tidy(value: Decimal) -> Decimal:
    trimmed = trim(value.quantize(Decimal("0.001")))
    assert trimmed is not None
    return trimmed


def _match(
    name: str, articles: dict[int, list[str]] | None
) -> tuple[int | None, str | None, float]:
    if not articles or not name:
        return None, None, 0.0
    from ..matching.normalize import best_match

    hit = best_match(name, articles, threshold=80)
    if hit is None:
        return None, None, 0.0
    article_id, score = hit
    return article_id, articles[article_id][0], score


def unit_matches_article(line_unit: Unit, article_unit: Unit) -> bool:
    """Dimensionswechsel wird abgelehnt, nicht geraten (general_plan.md §8 Nr. 10)."""
    return DIMENSION_OF[line_unit] == DIMENSION_OF[article_unit]


def suggested_article_unit(unit: Unit) -> Unit:
    dimension = DIMENSION_OF[unit]
    return {
        Dimension.COUNT: Unit.STUECK,
        Dimension.MASS: Unit.G,
        Dimension.VOLUME: Unit.ML,
    }[dimension]
