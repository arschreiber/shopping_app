"""Grundpreise vergleichbar machen (Phase 2: Richtpreis pro Artikel).

Ein Richtpreis gilt in der Einheit, in der der Artikel geführt wird: Gramm-Artikel in
€/kg, Milliliter-Artikel in €/l, Stück-Artikel in €/Stück. Angebote bringen ihren
Grundpreis als Text mit ("5,08 €/kg", "0,89 €/100 g"); fehlt er, wird er aus Preis und
Packung gerechnet ("250 g", "6 × 330 ml"), zuletzt aus der Stückzahl ("2er-Schale",
"je St." - steht bei Obst und Gemüse oft nur im Prospekttext). Was sich so nicht bestimmen
lässt ("€/Portion", "€/Blatt"), bleibt unbestimmt - und ein unbestimmter Preis ist nie
"unter dem Richtpreis".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .enums import Unit

KG, LITER, PIECE = "kg", "l", "Stück"

# Artikel-Einheit -> Einheit, in der Preise verglichen werden
COMPARE_UNIT: dict[Unit, str] = {Unit.G: KG, Unit.ML: LITER, Unit.STUECK: PIECE}

# Text-Einheit -> (Vergleichseinheit, Faktor auf diese Einheit)
_UNITS: dict[str, tuple[str, Decimal]] = {
    "kg": (KG, Decimal(1)),
    "g": (KG, Decimal("0.001")),
    "l": (LITER, Decimal(1)),
    "liter": (LITER, Decimal(1)),
    "ml": (LITER, Decimal("0.001")),
    "stück": (PIECE, Decimal(1)),
    "stk": (PIECE, Decimal(1)),
    "st": (PIECE, Decimal(1)),
}
_NUMBER = r"(\d+(?:[.,]\d+)?)"
_UNIT = r"(kg|g|ml|liter|l|stück|stk|st)\b\.?"
# "5,08 €/kg", "0,89 € / 100 g", "1,30 €/Stück"
_BASE = re.compile(_NUMBER + r"\s*€\s*/\s*(?:" + _NUMBER + r"\s*)?" + _UNIT, re.IGNORECASE)
# "6 × 330 ml", "4 x 125 g"
_MULTI = re.compile(r"(\d+)\s*[×x]\s*" + _NUMBER + r"\s*" + _UNIT, re.IGNORECASE)
# "250 g", "1,75 l" - bei "300 g / 285 g" zählt das erste (Füllmenge vor Abtropfgewicht)
_SINGLE = re.compile(_NUMBER + r"\s*" + _UNIT, re.IGNORECASE)
# Stückware: "2er-Schale", "3 Stück", "je 39 St.-Pckg.", "je St.", Aldis "… · Stück"
_PIECES = re.compile(
    r"\b(\d+)er[-\s]?(?:schale|packung|pack|pckg|netz|beutel|tray|bund)\b"
    r"|\b(\d+)\s*(?:stück|stk|st)\b"
    r"|\bje\s+(?:stück|stk|st)\b"
    r"|(?:^|·\s*)(?:stück|stk)\b",  # nicht "St.": "St. Moritz"
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class UnitPrice:
    value: Decimal
    unit: str  # KG | LITER | PIECE

    def label(self) -> str:
        return f"{self.value:.2f}".replace(".", ",") + f" €/{self.unit}"


def unit_price(
    price: Decimal | None,
    base_price: str | None,
    pack: str | None,
    description: str | None = None,
) -> UnitPrice | None:
    """Grundpreis aus dem Text der Quelle, sonst aus Preis und Packung, sonst je Stück."""
    return (
        parse_base_price(base_price)
        or from_pack(price, pack)
        or from_pieces(price, pack, description)
    )


def parse_base_price(text: str | None) -> UnitPrice | None:
    match = _BASE.search(text or "")
    if not match:
        return None
    value, per, unit_text = match.groups()
    unit, factor = _UNITS[unit_text.lower()]
    amount = _decimal(per) if per else Decimal(1)
    if amount is None or amount == 0:
        return None
    price = _decimal(value)
    if price is None:
        return None
    return UnitPrice(_round(price / (amount * factor)), unit)


@dataclass(frozen=True, slots=True)
class Quantity:
    """Wie viel eine Packung ist - in kg, l oder Stück."""

    amount: Decimal
    unit: str  # KG | LITER | PIECE


def pack_quantity(pack: str | None) -> Quantity | None:
    """"250 g" -> 0,25 kg, "6 × 330 ml" -> 1,98 l, "3 Stück" -> 3 Stück."""
    if not pack:
        return None
    text = pack.replace(" ", " ")
    multi = _MULTI.search(text)
    if multi:
        count, amount, unit_text = multi.groups()
        size = _decimal(amount)
        quantity = Decimal(count) * size if size is not None else None
    else:
        single = _SINGLE.search(text)
        if not single:
            return None
        amount, unit_text = single.groups()
        quantity = _decimal(amount)
    if not quantity:
        return None
    unit, factor = _UNITS[unit_text.lower()]
    return Quantity(quantity * factor, unit)


def from_pack(price: Decimal | None, pack: str | None) -> UnitPrice | None:
    quantity = pack_quantity(pack)
    if price is None or quantity is None:
        return None
    return UnitPrice(_round(price / quantity.amount), quantity.unit)


def pieces(text: str | None) -> int | None:
    """Wie viele Stück ein Angebot sind: "2er-Schale" -> 2, "je St." -> 1."""
    match = _PIECES.search(text or "")
    if not match:
        return None
    count = int(match.group(1) or match.group(2) or 1)
    return count or None


def from_pieces(price: Decimal | None, *texts: str | None) -> UnitPrice | None:
    """Stückware ohne Gewicht: "Avocados 1,29 €, 2er-Schale" -> 0,65 €/Stück. Erst die
    Packung, dann der Prospekttext - aus dem nur Stückzahlen, nie Gewichte ("ca. 33 cm")."""
    if price is None:
        return None
    for text in texts:
        count = pieces(text)
        if count:
            return UnitPrice(_round(price / count), PIECE)
    return None


def offer_quantity(
    price: Decimal | None,
    per_unit: UnitPrice | None,
    pack: str | None,
    description: str | None = None,
) -> Quantity | None:
    """Wie viel ein Angebot ist: aus der Packung, sonst aus der Stückzahl, sonst aus Preis
    und Grundpreis - "1,59 € (1,59 €/kg)" ist lose Ware zu 1 kg, "3,33 € (16,65 €/kg)"
    sind 200 g. Der Grundpreis ist auf den Cent gerundet, darum hier drei Stellen."""
    quantity = pack_quantity(pack)
    if quantity is not None:
        return quantity
    for text in (pack, description):
        count = pieces(text)
        if count:
            return Quantity(Decimal(count), PIECE)
    if price is not None and per_unit is not None and per_unit.value > 0:
        return Quantity(_significant(price / per_unit.value), per_unit.unit)
    return None


def in_article_unit(
    quantity: Quantity | None, article_unit: Unit, piece_size: Decimal | None = None
) -> Decimal | None:
    """Die Menge in der Einheit des Artikels: 0,3 kg -> 300 g, 2 Stück à 150 g -> 300 g."""
    if quantity is None:
        return None
    target = COMPARE_UNIT.get(article_unit)
    if quantity.unit == target:
        return quantity.amount * _PER_COMPARE_UNIT[article_unit]
    if quantity.unit == PIECE and target in (KG, LITER) and piece_size and piece_size > 0:
        return quantity.amount * piece_size
    return None


@dataclass(frozen=True, slots=True)
class Compared:
    """Ein Angebotspreis in der Einheit des Artikels."""

    value: Decimal
    via_piece: bool = False  # über das Stückgewicht umgerechnet - ein Schätzwert


def compare(
    price: UnitPrice | None, article_unit: Unit, piece_size: Decimal | None = None
) -> Compared | None:
    """Der Preis in der Einheit des Artikels - oder None, wenn er dort nichts sagt.

    Ein Stück-Preis für einen Gramm-Artikel ("Avocado 0,99 €/Stück") wird über das
    Stückgewicht zum kg-Preis (1 Stück ≈ 200 g -> 4,95 €/kg). Ohne Stückgewicht bleibt er
    unvergleichbar; geraten wird nicht.
    """
    if price is None:
        return None
    target = COMPARE_UNIT.get(article_unit)
    if target == price.unit:
        return Compared(price.value)
    if price.unit == PIECE and target in (KG, LITER) and piece_size and piece_size > 0:
        return Compared(_round(price.value * Decimal(1000) / piece_size), via_piece=True)
    return None


def comparable(
    price: UnitPrice | None, article_unit: Unit, piece_size: Decimal | None = None
) -> Decimal | None:
    compared = compare(price, article_unit, piece_size)
    return compared.value if compared else None


# Wie viel der Artikel-Einheit auf eine Vergleichseinheit geht: 1000 g = 1 kg
_PER_COMPARE_UNIT: dict[Unit, Decimal] = {
    Unit.G: Decimal(1000),
    Unit.ML: Decimal(1000),
    Unit.STUECK: Decimal(1),
}


def pack_unit_price(
    amount: Decimal | None,
    price: Decimal | None,
    article_unit: Unit,
    *,
    in_pieces: bool = False,
    piece_size: Decimal | None = None,
) -> Decimal | None:
    """Normalpreis so eingegeben, wie man einkauft, als Grundpreis des Artikels:
    "250 g für 1,29 €" -> 5,16 €/kg, "1 Stück für 0,79 €" bei 1 Stück ≈ 200 g -> 3,95 €/kg.
    """
    if not amount or price is None or amount <= 0:
        return None
    if in_pieces and article_unit is not Unit.STUECK:
        if not piece_size or piece_size <= 0:
            return None
        amount = amount * piece_size  # Stück -> g bzw. ml
    per = _PER_COMPARE_UNIT.get(article_unit)
    if per is None:
        return None
    return _round(price * per / amount)


def _decimal(text: str | None) -> Decimal | None:
    if text is None:
        return None
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def _significant(value: Decimal, digits: int = 3) -> Decimal:
    if value == 0:
        return value
    step = Decimal(1).scaleb(value.adjusted() - digits + 1)
    return value.quantize(step, rounding=ROUND_HALF_UP)


def _round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
