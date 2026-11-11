"""Mikronährstoffe eines Gerichts aus dem Bundeslebensmittelschlüssel (pure).

Die Quelle ist der BLS 4.0 des Max Rubner-Instituts (CC BY 4.0): je Lebensmittel und
je 100 g. Ein Artikel zeigt per `bls_code` auf genau einen Eintrag; die App liest daraus
eine kuratierte Auswahl - Ballaststoffe, Mineralstoffe, Vitamine - statt aller 138.

Dieselben Haltungen wie in `nutrition.py`:

1. **Gramm sind die Brücke.** Der BLS rechnet je 100 g, der Artikel in seiner
   kanonischen Einheit. `grams_per_unit` übersetzt: bei G immer 1, bei ML die Dichte
   (Öl ≈ 0,92, sonst 1), bei STUECK das Stückgewicht. Fehlt das Stückgewicht, ist die
   Zutat eine Lücke - geraten wird nicht.
2. **Lücken werden gemeldet.** Zutaten ohne Referenz, bewusst ohne Referenz
   (`skipped`) und ohne Menge stehen einzeln im Ergebnis. Und weil der BLS nicht für
   jedes Lebensmittel jeden Nährstoff kennt, trägt jeder Wert sein eigenes Flag
   `partial`.
3. **Etikett vor Datenbank**, je Nährstoff. Steht ein Wert auf dem Etikett
   (`label`, je 100 g / 100 ml / Stück wie die Makros, in der Anzeigeeinheit), zählt er;
   sonst der BLS. So bekommen Proteinpulver oder angereicherte Drinks ihre Werte, auch
   ganz ohne BLS-Referenz - was weder Etikett noch BLS nennt, bleibt `partial`.

Die Referenzwerte sind die der DGE für einen Mann von 25 bis unter 51 Jahren, also eine
Orientierung und kein Ziel pro Mahlzeit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from .enums import Unit
from .model import IngredientSpec
from .nutrition import BASIS_AMOUNT, Nutrients
from .units import Quantity

HUNDRED = Decimal(100)

ReferenceKind = Literal["target", "limit"]


@dataclass(frozen=True, slots=True)
class NutrientDef:
    code: str  # BLS-Komponentencode
    label: str
    unit: str  # Anzeigeeinheit
    group: str
    reference: Decimal | None = None  # je Tag
    kind: ReferenceKind | None = None  # "target" = mindestens, "limit" = höchstens
    scale: Decimal = Decimal(1)  # BLS-Einheit -> Anzeigeeinheit (B6: µg -> mg)
    places: int = 1


GROUP_GENERAL = "Allgemein"
GROUP_MINERALS = "Mineralstoffe"
GROUP_VITAMINS = "Vitamine"

REFERENCE_PERSON = "DGE-Referenzwerte, Mann 25 bis unter 51 Jahre"

# Energie für die Fettsäure-Grenze: Richtwert bei PAL 1,4 (≈ 2400 kcal) -
# gesättigte Fettsäuren höchstens 10 % davon ≈ 27 g.
MICRONUTRIENTS: tuple[NutrientDef, ...] = (
    NutrientDef("FIBT", "Ballaststoffe", "g", GROUP_GENERAL, Decimal(30), "target"),
    NutrientDef("SUGAR", "Zucker", "g", GROUP_GENERAL),
    NutrientDef("FASAT", "Ges. Fettsäuren", "g", GROUP_GENERAL, Decimal(27), "limit"),
    NutrientDef("FAPUN3", "Omega-3", "g", GROUP_GENERAL, places=2),
    NutrientDef("NACL", "Salz", "g", GROUP_GENERAL, Decimal(6), "limit", places=2),
    NutrientDef("K", "Kalium", "mg", GROUP_MINERALS, Decimal(4000), "target", places=0),
    NutrientDef("CA", "Calcium", "mg", GROUP_MINERALS, Decimal(1000), "target", places=0),
    NutrientDef("MG", "Magnesium", "mg", GROUP_MINERALS, Decimal(350), "target", places=0),
    NutrientDef("P", "Phosphor", "mg", GROUP_MINERALS, Decimal(550), "target", places=0),
    NutrientDef("FE", "Eisen", "mg", GROUP_MINERALS, Decimal(11), "target"),
    NutrientDef("ZN", "Zink", "mg", GROUP_MINERALS, Decimal(14), "target"),
    NutrientDef("ID", "Jod", "µg", GROUP_MINERALS, Decimal(150), "target", places=0),
    NutrientDef("VITAA", "Vitamin A", "µg", GROUP_VITAMINS, Decimal(850), "target", places=0),
    NutrientDef("VITD", "Vitamin D", "µg", GROUP_VITAMINS, Decimal(20), "target"),
    NutrientDef("VITE", "Vitamin E", "mg", GROUP_VITAMINS, Decimal(14), "target"),
    NutrientDef("VITK", "Vitamin K", "µg", GROUP_VITAMINS, Decimal(70), "target", places=0),
    NutrientDef("THIA", "Vitamin B1", "mg", GROUP_VITAMINS, Decimal("1.2"), "target", places=2),
    NutrientDef("RIBF", "Vitamin B2", "mg", GROUP_VITAMINS, Decimal("1.4"), "target", places=2),
    NutrientDef("NIAEQ", "Niacin", "mg", GROUP_VITAMINS, Decimal(15), "target"),
    NutrientDef(
        "VITB6", "Vitamin B6", "mg", GROUP_VITAMINS, Decimal("1.6"), "target",
        scale=Decimal("0.001"), places=2,
    ),
    NutrientDef("FOL", "Folat", "µg", GROUP_VITAMINS, Decimal(300), "target", places=0),
    NutrientDef("VITB12", "Vitamin B12", "µg", GROUP_VITAMINS, Decimal(4), "target"),
    NutrientDef("VITC", "Vitamin C", "mg", GROUP_VITAMINS, Decimal(110), "target", places=0),
)

# Makros im BLS - für Artikel, die kein Etikett haben.
MACRO_CODES = {"kcal": "ENERCC", "carbs_g": "CHO", "fat_g": "FAT", "protein_g": "PROT625"}

# Etiketten nennen synthetische Folsäure; gerechnet wird in Folat-Äquivalenten
# (BLS: FOL = Folat + 1,7 · Folsäure). Darum darf das Etikett beides tragen.
FOLIC_ACID = "FOLAC"
FOLIC_ACID_FACTOR = Decimal("1.7")
LABEL_CODES: tuple[str, ...] = (*(n.code for n in MICRONUTRIENTS), FOLIC_ACID)


def effective_label(label: Mapping[str, Decimal]) -> dict[str, Decimal]:
    """Etikettwerte, wie die Rechnung sie braucht: Folsäure in Folat-Äquivalente."""
    out = {code: value for code, value in label.items() if code != FOLIC_ACID}
    folic = label.get(FOLIC_ACID)
    if folic is not None:
        out["FOL"] = out.get("FOL", Decimal(0)) + folic * FOLIC_ACID_FACTOR
    return out


# Alles, was der Import aus der Excel übernimmt.
IMPORTED_CODES: tuple[str, ...] = (
    *MACRO_CODES.values(),
    *(n.code for n in MICRONUTRIENTS),
)


@dataclass(frozen=True, slots=True)
class ArticleMicros:
    """Die Werte eines Artikels: BLS je 100 g plus die Brücke zur Artikel-Einheit, und
    was das Etikett nennt (je Bezugsgröße, Anzeigeeinheit, Folsäure schon umgerechnet)."""

    article_id: int
    unit: Unit
    per_100g: Mapping[str, Decimal]
    grams_per_unit: Decimal | None = None  # None = 1 bei G/ML, Lücke bei STUECK
    label: Mapping[str, Decimal] = field(default_factory=dict)

    @property
    def grams_factor(self) -> Decimal | None:
        """Gramm je *einer* Artikel-Einheit (1 g, 1 ml, 1 Stück)."""
        if self.grams_per_unit is not None:
            return self.grams_per_unit
        return None if self.unit is Unit.STUECK else Decimal(1)


@dataclass(frozen=True, slots=True)
class MicroValue:
    code: str
    amount: Decimal  # in der Anzeigeeinheit, gerundet
    partial: bool  # mindestens eine gezählte Zutat ohne Angabe zu diesem Nährstoff
    share: Decimal | None  # Anteil am Tageswert in Prozent, gerundet


@dataclass(frozen=True, slots=True)
class DishMicros:
    per_portion: tuple[MicroValue, ...]
    ingredient_count: int
    counted_ids: tuple[int, ...] = ()
    missing_ids: tuple[int, ...] = ()  # ohne BLS-Zuordnung
    skipped_ids: tuple[int, ...] = ()  # bewusst ohne Referenz
    open_quantity_ids: tuple[int, ...] = ()  # ohne Menge oder ohne Stückgewicht
    # Je gezählter Zutat und Portion: `{Code: Menge}` in der Anzeigeeinheit, gerundet.
    # Fehlt ein Code, kennt keine Quelle den Wert für diese Zutat.
    contributions: tuple[tuple[int, dict[str, Decimal]], ...] = ()

    def get(self, code: str) -> MicroValue | None:
        return next((value for value in self.per_portion if value.code == code), None)

    @property
    def gap_count(self) -> int:
        return len(self.missing_ids) + len(self.skipped_ids) + len(self.open_quantity_ids)

    @property
    def is_complete(self) -> bool:
        return self.ingredient_count > 0 and self.gap_count == 0

    @property
    def has_any(self) -> bool:
        return bool(self.counted_ids)


def dish_micronutrients(
    ingredients: list[IngredientSpec],
    articles: Mapping[int, ArticleMicros],
    *,
    skipped: frozenset[int] | set[int] = frozenset(),
    portions: int,
) -> DishMicros:
    """Summiert Etikett- und BLS-Werte der Zutaten und teilt durch die Portionen.

    `totals` rechnet in der Anzeigeeinheit: BLS-Werte werden beim Addieren skaliert,
    Etikettwerte sind es schon.
    """
    totals: dict[str, Decimal] = {n.code: Decimal(0) for n in MICRONUTRIENTS}
    shares: dict[int, dict[str, Decimal]] = {}
    partial: set[str] = set()
    counted: list[int] = []
    missing: list[int] = []
    skipped_ids: list[int] = []
    open_quantity: list[int] = []

    for line in ingredients:
        facts = articles.get(line.article_id)
        if facts is None:
            (skipped_ids if line.article_id in skipped else missing).append(line.article_id)
            continue
        factor = facts.grams_factor
        # Ohne Stückgewicht trägt nur das Etikett - und das nur, wenn es überhaupt etwas
        # nennt; sonst ist die Zeile eine Lücke wie eine ohne Menge.
        if line.quantity is None or (factor is None and not facts.label):
            open_quantity.append(line.article_id)
            continue

        amount = Quantity(line.quantity, line.unit).to(facts.unit).amount
        assert amount is not None
        basis_share = amount / BASIS_AMOUNT[facts.unit]
        grams = amount * factor if factor is not None else None
        share = shares.setdefault(line.article_id, {})
        for nutrient in MICRONUTRIENTS:
            labelled = facts.label.get(nutrient.code)
            if labelled is not None:
                part = labelled * basis_share
            else:
                value = facts.per_100g.get(nutrient.code)
                if value is None or grams is None:
                    partial.add(nutrient.code)
                    continue
                part = value * grams / HUNDRED * nutrient.scale
            totals[nutrient.code] += part
            share[nutrient.code] = share.get(nutrient.code, Decimal(0)) + part
        counted.append(line.article_id)

    divisor = Decimal(portions if portions > 0 else 1)
    places = {n.code: Decimal(1).scaleb(-n.places) for n in MICRONUTRIENTS}
    contributions = tuple(
        (
            article_id,
            {code: (part / divisor).quantize(places[code]) for code, part in share.items()},
        )
        for article_id, share in shares.items()
    )
    values = tuple(
        _value(nutrient, totals[nutrient.code] / divisor, nutrient.code in partial)
        for nutrient in MICRONUTRIENTS
    )
    return DishMicros(
        per_portion=values if counted else (),
        contributions=contributions,
        ingredient_count=len(ingredients),
        counted_ids=tuple(counted),
        missing_ids=tuple(missing),
        skipped_ids=tuple(skipped_ids),
        open_quantity_ids=tuple(open_quantity),
    )


def _value(nutrient: NutrientDef, amount: Decimal, partial: bool) -> MicroValue:
    share = None
    if nutrient.reference:
        share = (amount / nutrient.reference * HUNDRED).quantize(Decimal(1))
    return MicroValue(
        code=nutrient.code,
        amount=amount.quantize(Decimal(1).scaleb(-nutrient.places)),
        partial=partial,
        share=share,
    )


def sum_micros(
    groups: Iterable[Sequence[MicroValue]], *, divisor: Decimal = Decimal(1)
) -> tuple[MicroValue, ...]:
    """Mehrere Portionen addieren (ein Tag) oder mitteln (`divisor`: Ø je Mahlzeit).

    Hat eine der Portionen gar keine Mikro-Angaben, ist jede Summe eine Untergrenze -
    alle Werte werden dann `partial`.
    """
    rows = list(groups)
    if not any(rows):
        return ()
    gap = any(not row for row in rows)
    values: list[MicroValue] = []
    for nutrient in MICRONUTRIENTS:
        amount = Decimal(0)
        partial = gap
        for row in rows:
            value = next((v for v in row if v.code == nutrient.code), None)
            if value is None:
                partial = partial or bool(row)
                continue
            amount += value.amount
            partial = partial or value.partial
        values.append(_value(nutrient, amount / divisor, partial))
    return tuple(values)


def macros_from_bls(facts: ArticleMicros) -> Nutrients | None:
    """Die BLS-Makros je Bezugsgröße des Artikels (100 g, 100 ml, 1 Stück).

    Nur als Ersatz, wenn am Artikel nichts vom Etikett steht. `None`, wenn das
    Stückgewicht fehlt oder der BLS-Eintrag keine Energie kennt.
    """
    factor = facts.grams_factor
    kcal = facts.per_100g.get(MACRO_CODES["kcal"])
    if factor is None or kcal is None:
        return None
    grams = BASIS_AMOUNT[facts.unit] * factor
    per = grams / HUNDRED

    def pick(key: str) -> Decimal:
        return (facts.per_100g.get(MACRO_CODES[key]) or Decimal(0)) * per

    return Nutrients(
        kcal=kcal * per,
        carbs_g=pick("carbs_g"),
        fat_g=pick("fat_g"),
        protein_g=pick("protein_g"),
    )


# ------------------------------------------------------------------ Profil je Artikel

ProfileSource = Literal["label", "bls"]


@dataclass(frozen=True, slots=True)
class ProfileValue:
    code: str
    amount: Decimal  # je Bezugsgröße des Artikels, Anzeigeeinheit, gerundet
    source: ProfileSource
    share: Decimal | None  # % vom Tageswert der Referenzperson


def article_amounts(facts: ArticleMicros) -> dict[str, tuple[Decimal, ProfileSource]]:
    """Ungerundet: `{Code: (Menge je Bezugsgröße in Anzeigeeinheit, Quelle)}`.

    Dieselbe Regel wie im Gericht - Etikett vor BLS, je Nährstoff. Bei Stück-Artikeln
    ohne Stückgewicht trägt nur das Etikett; der BLS rechnet in Gramm.
    """
    factor = facts.grams_factor
    grams = BASIS_AMOUNT[facts.unit] * factor if factor is not None else None
    out: dict[str, tuple[Decimal, ProfileSource]] = {}
    for nutrient in MICRONUTRIENTS:
        labelled = facts.label.get(nutrient.code)
        if labelled is not None:
            out[nutrient.code] = (labelled, "label")
            continue
        value = facts.per_100g.get(nutrient.code)
        if value is None or grams is None:
            continue
        out[nutrient.code] = (value * grams / HUNDRED * nutrient.scale, "bls")
    return out


def article_profile(facts: ArticleMicros) -> tuple[ProfileValue, ...]:
    """Was der Artikel je 100 g / 100 ml / Stück trägt - gerundet, mit Tageswert-Anteil.
    Werte, die keine Quelle kennt, fehlen."""
    amounts = article_amounts(facts)
    out: list[ProfileValue] = []
    for nutrient in MICRONUTRIENTS:
        if nutrient.code not in amounts:
            continue
        amount, source = amounts[nutrient.code]
        rounded = _value(nutrient, amount, partial=False)
        out.append(ProfileValue(nutrient.code, rounded.amount, source, rounded.share))
    return tuple(out)
