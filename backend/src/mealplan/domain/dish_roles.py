"""Beilage und Protein eines Gerichts aus seinen Zutaten erkennen (pure).

Beilage und Protein stehen fast immer schon als Zutat im Rezept: Reis ist die Beilage
"Reis", Räuchertofu das Protein "Tofu". Das Formular soll sie darum nicht mehr abfragen,
sondern vorschlagen.

Drei Regeln tragen das:

1. **Die Rolle hängt an der Zutat und wird gelernt, nicht gepflegt.** Welche Zutat welche
   Kategorie trägt, steht schon in den gespeicherten Gerichten: "Lasagne" hat die Beilage
   "Nudeln" und enthält Lasagneplatten. `learn_roles` liest das aus allen Gerichten
   heraus - zuerst über den Namen (Hirtenkäse Light -> Hirtenkäse), sonst über die
   Zutat, die am meisten beiträgt (Wildlachs -> Fisch). Es gibt kein eigenes Feld
   dafür: wer ein Gericht mit der Beilage "Hirse" speichert, hat Hirse damit gelernt.

2. **Pro Gericht entscheidet die Menge.** Beilage ist die Zutat mit Beilagen-Rolle, die
   die meisten Gramm Kohlenhydrate liefert, Protein die mit den meisten Gramm Protein.
   Die Beilagen-Zutat zählt dabei nicht als Protein - sonst gewönne bei Burritos der
   Proteinwrap gegen die Kidneybohnen.

3. **Unbekanntes wird vorgeschlagen, nicht gesetzt.** Trägt keine Zutat die Rolle,
   kommt höchstens ein Vorschlag: die nährwertstärkste Zutat, wenn sie dicht genug ist
   und genug vom Gericht ausmacht. Gesetzt wird er erst, wenn man ihn bestätigt. Chili
   ohne Beilage bleibt so ohne Beilage, statt passierte Tomaten zur Beilage zu machen.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from .enums import CategoryAxis

ROLE_AXES: tuple[CategoryAxis, ...] = (CategoryAxis.SIDE, CategoryAxis.PROTEIN)

# Ab wann eine Zutat ohne Rolle als Vorschlag taugt: Anteil am Gericht (KH bzw. Protein)
# und Dichte je 100 g/ml. Kartoffeln (19 g KH) und Kidneybohnen aus der Dose (7,5 g
# Protein) sollen durchkommen, gehackte Tomaten und Mais nicht.
MIN_SHARE: dict[CategoryAxis, Decimal] = {
    CategoryAxis.SIDE: Decimal("0.30"),
    CategoryAxis.PROTEIN: Decimal("0.25"),
}
MIN_DENSITY: dict[CategoryAxis, Decimal] = {
    CategoryAxis.SIDE: Decimal(15),
    CategoryAxis.PROTEIN: Decimal(6),
}
# Stück-Artikel haben keine Dichte - dort muss der Anteil allein überzeugen.
MIN_SHARE_PIECES = Decimal("0.40")
# Kürzere Namen ("Ei") stecken in zu vielen anderen.
MIN_NAME_LENGTH = 4


@dataclass(frozen=True, slots=True)
class RoleLine:
    """Eine Zutat des Gerichts mit dem, was sie im ganzen Gericht beiträgt."""

    article_id: int
    name: str
    carbs_g: Decimal = Decimal(0)
    protein_g: Decimal = Decimal(0)
    # je 100 g / 100 ml; None bei Stück-Artikeln
    carbs_density: Decimal | None = None
    protein_density: Decimal | None = None

    def grams(self, axis: CategoryAxis) -> Decimal:
        return self.carbs_g if axis is CategoryAxis.SIDE else self.protein_g

    def density(self, axis: CategoryAxis) -> Decimal | None:
        return self.carbs_density if axis is CategoryAxis.SIDE else self.protein_density


@dataclass(frozen=True, slots=True)
class LearnDish:
    """Ein gespeichertes Gericht: seine Kategorien und seine Zutaten."""

    categories: dict[CategoryAxis, str]
    lines: tuple[RoleLine, ...]


@dataclass(frozen=True, slots=True)
class Candidate:
    article_id: int
    name: str
    grams: Decimal
    # Die Kategorie, für die diese Zutat steht: gelernt (`known`) oder vorgeschlagen.
    category: str
    known: bool
    # Liefert schon die Beilage - zählt nicht als Protein.
    is_side: bool = False


@dataclass(frozen=True, slots=True)
class Detection:
    axis: CategoryAxis
    category: str | None  # erkannt; None = nichts sicher
    source: Candidate | None  # woher `category` kommt
    suggestion: Candidate | None  # nur wenn nichts erkannt ist
    candidates: tuple[Candidate, ...]  # alle Zutaten, nach Gramm absteigend


def name_matches(category: str, article: str) -> bool:
    """"Hirtenkäse" passt zu "Hirtenkäse Light", "Kartoffeln" zu "Kartoffel"."""
    c, a = category.strip().casefold(), article.strip().casefold()
    if len(c) < MIN_NAME_LENGTH or len(a) < MIN_NAME_LENGTH:
        return c == a
    return c in a or a in c


def proposed_category(article: str, existing: Iterable[str]) -> str:
    """Welche Kategorie eine Zutat bekäme: eine vorhandene mit passendem Namen, sonst
    ihr eigener Name ("Rote Linsen" -> "Linsen", "Hirse" -> "Hirse")."""
    names = list(existing)
    folded = article.strip().casefold()
    for name in names:
        if name.casefold() == folded:
            return name
    inside = [n for n in names if len(n) >= MIN_NAME_LENGTH and n.casefold() in folded]
    if inside:
        return max(inside, key=len)
    around = [n for n in names if name_matches(n, article)]
    if around:
        return min(around, key=len)
    return article.strip()


def _source_line(
    axis: CategoryAxis, category: str, lines: Iterable[RoleLine], exclude: int | None
) -> RoleLine | None:
    """Welche Zutat eines gespeicherten Gerichts für seine Kategorie steht."""
    pool = [line for line in lines if line.article_id != exclude]
    named = [line for line in pool if name_matches(category, line.name)]
    if named:
        return max(named, key=lambda line: line.grams(axis))
    best = max(pool, key=lambda line: line.grams(axis), default=None)
    if best is None or best.grams(axis) <= 0:
        return None
    return best


def learn_roles(dishes: Iterable[LearnDish]) -> dict[CategoryAxis, dict[int, str]]:
    """`{Achse: {article_id: Kategorie}}` aus den gespeicherten Gerichten.

    Widersprechen sich Gerichte, gewinnt die Mehrheit, bei Gleichstand das erste.
    """
    votes: dict[CategoryAxis, dict[int, Counter[str]]] = {axis: {} for axis in ROLE_AXES}
    for dish in dishes:
        side_id: int | None = None
        for axis in ROLE_AXES:
            category = dish.categories.get(axis)
            if not category:
                continue
            exclude = side_id if axis is CategoryAxis.PROTEIN else None
            line = _source_line(axis, category, dish.lines, exclude)
            if line is None:
                continue
            if axis is CategoryAxis.SIDE:
                side_id = line.article_id
            votes[axis].setdefault(line.article_id, Counter())[category] += 1
    return {
        axis: {
            article_id: counter.most_common(1)[0][0]
            for article_id, counter in by_article.items()
        }
        for axis, by_article in votes.items()
    }


def _qualifies(axis: CategoryAxis, line: RoleLine, total: Decimal) -> bool:
    grams = line.grams(axis)
    if grams <= 0 or total <= 0:
        return False
    share = grams / total
    density = line.density(axis)
    if density is None:
        return share >= MIN_SHARE_PIECES
    return share >= MIN_SHARE[axis] and density >= MIN_DENSITY[axis]


def _detect(
    axis: CategoryAxis,
    lines: list[RoleLine],
    roles: dict[CategoryAxis, dict[int, str]],
    existing: Iterable[str],
    exclude: int | None,
) -> Detection:
    own = roles.get(axis, {})
    other = {
        article_id
        for other_axis, by_article in roles.items()
        if other_axis is not axis
        for article_id in by_article
    }
    names = list(existing)
    # Alle Zutaten, auch ohne Nährwerte: eine gelernte Rolle gilt auch dann, wenn der
    # Artikel (noch) keine Angaben hat - nur ein Vorschlag braucht Gramm.
    ranked = sorted(lines, key=lambda line: line.grams(axis), reverse=True)
    candidates = tuple(
        Candidate(
            article_id=line.article_id,
            name=line.name,
            grams=line.grams(axis),
            category=own.get(line.article_id) or proposed_category(line.name, names),
            known=line.article_id in own,
            is_side=line.article_id == exclude,
        )
        for line in ranked
    )

    known = [c for c in candidates if c.known and not c.is_side]
    if known:
        return Detection(axis, known[0].category, known[0], None, candidates)

    # Nichts gelernt - höchstens ein Vorschlag. Was schon auf der anderen Achse eine
    # Rolle hat (Rote Linsen sind Protein), wird hier nicht noch einmal angeboten.
    pool = [line for line in ranked if line.article_id != exclude]
    total = sum((line.grams(axis) for line in pool), Decimal(0))
    for line in pool:
        if line.article_id in other:
            continue
        if _qualifies(axis, line, total):
            suggestion = next(c for c in candidates if c.article_id == line.article_id)
            return Detection(axis, None, None, suggestion, candidates)
        break  # nur die stärkste Zutat ohne Rolle zählt
    return Detection(axis, None, None, None, candidates)


def detect_roles(
    lines: Iterable[RoleLine],
    roles: dict[CategoryAxis, dict[int, str]],
    existing: dict[CategoryAxis, list[str]],
) -> dict[CategoryAxis, Detection]:
    """Beilage, dann Protein - die Beilagen-Zutat fällt beim Protein heraus."""
    merged: dict[int, RoleLine] = {}
    for line in lines:
        seen = merged.get(line.article_id)
        merged[line.article_id] = (
            line
            if seen is None
            else RoleLine(
                article_id=line.article_id,
                name=line.name,
                carbs_g=seen.carbs_g + line.carbs_g,
                protein_g=seen.protein_g + line.protein_g,
                carbs_density=line.carbs_density,
                protein_density=line.protein_density,
            )
        )
    rows = list(merged.values())
    side = _detect(CategoryAxis.SIDE, rows, roles, existing.get(CategoryAxis.SIDE, []), None)
    picked = side.source or side.suggestion
    protein = _detect(
        CategoryAxis.PROTEIN,
        rows,
        roles,
        existing.get(CategoryAxis.PROTEIN, []),
        picked.article_id if picked else None,
    )
    return {CategoryAxis.SIDE: side, CategoryAxis.PROTEIN: protein}
