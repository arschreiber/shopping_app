"""Beispieldaten zum Ausprobieren.

Bewusst *keine* Migration und kein Auto-Seed: die echte Gerichteliste entsteht per Hand
(general_plan.md §5 Phase 0). Diese Daten sind zum Anschauen und Testen da - und als
Vorlage dafuer, wie die Erfassung gedacht ist.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.enums import CategoryAxis, Effort, SuitableFor, Unit
from ..services.dishes import CategoryInput, IngredientInput, create_dish
from ..services.ingredient_parsing import parse_lines

# (Name, Einheit, Grundvorrat?, Bring!-Katalogname, Nährwerte)
#
# Die Nährwerte beziehen sich auf die kanonische Einheit: je 100 g, je 100 ml oder je
# Stück. Es sind Hausnummern zum Ausprobieren, keine Laborwerte - beim eigenen Korpus
# stehen die Angaben auf der Packung.
#
# Salz und Pfeffer stehen bewusst auf null: sie kommen ohne Menge in den Rezepten vor,
# und eine Prise trägt nichts bei. Dadurch gelten Gerichte mit ihnen trotzdem als
# vollständig gerechnet.
ARTICLES: list[tuple[str, Unit, bool, str | None, tuple[float, float, float, float] | None]] = [
    ("Basmatireis", Unit.G, False, "Reis", (350, 7, 78, 1)),
    ("Nudeln", Unit.G, False, "Nudeln", (360, 12, 71, 1.5)),
    ("Kartoffeln", Unit.G, False, "Kartoffeln", (77, 2, 17, 0.1)),
    ("Hirtenkäse", Unit.G, False, "Feta", (250, 14, 4, 21)),
    ("Lachsfilet", Unit.G, False, "Lachs", (200, 20, 0, 13)),
    ("Hähnchenbrust", Unit.G, False, "Hähnchenbrust", (105, 23, 0, 1.5)),
    ("Rinderhackfleisch", Unit.G, False, "Hackfleisch", (250, 19, 0, 19)),
    ("Rote Linsen", Unit.G, False, "Linsen", (350, 24, 52, 2)),
    ("Kichererbsen", Unit.STUECK, False, "Kichererbsen", (290, 17, 40, 5)),
    ("Zucchini", Unit.STUECK, False, "Zucchini", (45, 3, 6, 0.8)),
    ("Paprika", Unit.STUECK, False, "Paprika", (30, 1.5, 5, 0.4)),
    ("Zwiebeln", Unit.STUECK, False, "Zwiebeln", (40, 1.2, 8, 0.2)),
    ("Knoblauch", Unit.STUECK, False, "Knoblauch", (5, 0.2, 1, 0)),
    ("Tomaten", Unit.G, False, "Tomaten", (18, 0.9, 3.5, 0.2)),
    ("Passierte Tomaten", Unit.ML, False, "Passierte Tomaten", (30, 1.4, 5, 0.2)),
    ("Kokosmilch", Unit.ML, False, "Kokosmilch", (190, 2, 3, 19)),
    ("Sahne", Unit.ML, False, "Sahne", (290, 2.4, 3.2, 30)),
    ("Reibekäse", Unit.G, False, "Käse", (350, 25, 1, 28)),
    ("Brokkoli", Unit.STUECK, False, "Brokkoli", (170, 14, 15, 2)),
    ("Süßkartoffeln", Unit.G, False, "Süßkartoffeln", (86, 1.6, 20, 0.1)),
    ("Baguette", Unit.STUECK, False, "Baguette", (650, 22, 130, 3)),
    ("Eier", Unit.STUECK, False, "Eier", (78, 6.5, 0.6, 5.3)),
    ("Spinat", Unit.G, False, "Spinat", (23, 2.9, 1.4, 0.4)),
    ("Feta", Unit.G, False, "Feta", (260, 14, 4, 21)),
    ("Olivenöl", Unit.ML, True, "Olivenöl", (830, 0, 0, 92)),
    ("Salz", Unit.G, True, "Salz", (0, 0, 0, 0)),
    ("Pfeffer", Unit.G, True, "Pfeffer", (0, 0, 0, 0)),
    ("Currypulver", Unit.G, True, "Curry", (325, 14, 56, 14)),
    ("Paprikapulver", Unit.G, True, "Paprikapulver", (280, 14, 54, 13)),
    ("Kaffee", Unit.G, False, "Kaffee", (0, 0, 0, 0)),
]

# (Name, Portionen, mitnehmbar, Aufwand, geeignet für, Beilage, Protein, Küche, Zutaten)
DISHES: list[tuple] = [
    (
        "Hirtenkäse-Reispfanne", 3, True, Effort.QUICK, SuitableFor.BOTH,
        "Reis", "Hirtenkäse", "mediterran",
        "250 g Basmatireis\n200 g Hirtenkäse\n1 Zucchini\n1 Paprika\n1 Zwiebeln\n"
        "2 EL Olivenöl\nSalz\nPfeffer",
    ),
    (
        "Lachs mit Ofengemüse", 2, True, Effort.NORMAL, SuitableFor.DINNER,
        "Kartoffeln", "Fisch", None,
        "300 g Lachsfilet\n600 g Kartoffeln\n1 Zucchini\n1 Paprika\n3 EL Olivenöl\nSalz",
    ),
    (
        "Spaghetti Bolognese", 3, True, Effort.NORMAL, SuitableFor.BOTH,
        "Nudeln", "Rind", "italienisch",
        "350 g Nudeln\n400 g Rinderhackfleisch\n500 ml Passierte Tomaten\n"
        "2 Zwiebeln\n2 Zehen Knoblauch\nSalz\nPfeffer",
    ),
    (
        "Rote-Linsen-Curry", 3, True, Effort.QUICK, SuitableFor.BOTH,
        "Reis", "Hülsenfrüchte", "indisch",
        "250 g Rote Linsen\n200 g Basmatireis\n400 ml Kokosmilch\n1 Zwiebeln\n"
        "10 g Currypulver\nSalz",
    ),
    (
        "Hähnchen-Brokkoli-Pfanne", 3, True, Effort.QUICK, SuitableFor.BOTH,
        "Reis", "Hähnchen", "asiatisch",
        "400 g Hähnchenbrust\n1 Brokkoli\n250 g Basmatireis\n2 Zehen Knoblauch\n"
        "2 EL Olivenöl\nSalz",
    ),
    (
        "Kartoffelgratin", 2, False, Effort.ELABORATE, SuitableFor.DINNER,
        "Kartoffeln", "vegetarisch", None,
        "800 g Kartoffeln\n200 ml Sahne\n150 g Reibekäse\n1 Zehen Knoblauch\nSalz\nPfeffer",
    ),
    (
        "Nudelauflauf mit Spinat", 3, True, Effort.NORMAL, SuitableFor.BOTH,
        "Nudeln", "Hirtenkäse", None,
        "300 g Nudeln\n400 g Spinat\n200 g Feta\n200 ml Sahne\n100 g Reibekäse\nSalz",
    ),
    (
        "Kichererbsen-Curry", 3, True, Effort.QUICK, SuitableFor.BOTH,
        "Reis", "Hülsenfrüchte", "indisch",
        "2 Dosen Kichererbsen\n400 ml Kokosmilch\n250 g Basmatireis\n1 Zwiebeln\n"
        "10 g Currypulver",
    ),
    (
        "Süßkartoffel-Ofengemüse", 2, True, Effort.NORMAL, SuitableFor.DINNER,
        "Kartoffeln", "vegetarisch", None,
        "600 g Süßkartoffeln\n1 Paprika\n1 Zucchini\n150 g Feta\n3 EL Olivenöl\n"
        "5 g Paprikapulver",
    ),
    (
        "Tomatenpasta", 2, True, Effort.QUICK, SuitableFor.BOTH,
        "Nudeln", "vegetarisch", "italienisch",
        "250 g Nudeln\n400 g Tomaten\n2 Zehen Knoblauch\n3 EL Olivenöl\nSalz",
    ),
    (
        "Shakshuka mit Baguette", 2, False, Effort.QUICK, SuitableFor.BOTH,
        "Brot", "Eier", "orientalisch",
        "4 Eier\n500 ml Passierte Tomaten\n1 Paprika\n1 Zwiebeln\n1 Baguette\n"
        "5 g Paprikapulver",
    ),
    (
        "Hähnchen-Curry mit Süßkartoffel", 3, True, Effort.NORMAL, SuitableFor.DINNER,
        "Reis", "Hähnchen", "indisch",
        "400 g Hähnchenbrust\n400 g Süßkartoffeln\n400 ml Kokosmilch\n250 g Basmatireis\n"
        "10 g Currypulver",
    ),
    (
        "Lachs-Spinat-Nudeln", 2, True, Effort.QUICK, SuitableFor.BOTH,
        "Nudeln", "Fisch", "italienisch",
        "250 g Nudeln\n250 g Lachsfilet\n300 g Spinat\n150 ml Sahne\nSalz",
    ),
    (
        "Ofen-Frittata", 3, True, Effort.NORMAL, SuitableFor.LUNCH,
        "Kartoffeln", "Eier", None,
        "6 Eier\n400 g Kartoffeln\n1 Zucchini\n100 g Reibekäse\n2 EL Olivenöl\nSalz",
    ),
]


def seed(session: Session) -> dict[str, int]:
    """Idempotent: schon vorhandene Namen werden übersprungen."""
    from ..services.articles import create_article, name_index

    existing_articles = {
        row.lower() for row in session.scalars(select(m.Article.canonical_name))
    }
    created_articles = 0
    for name, unit, staple, catalog_name, nutrition in ARTICLES:
        if name.lower() in existing_articles:
            continue
        values = (
            dict(
                zip(
                    ("kcal", "protein_g", "carbs_g", "fat_g"),
                    (Decimal(str(value)) for value in nutrition),
                    strict=True,
                )
            )
            if nutrition
            else {}
        )
        create_article(
            session,
            canonical_name=name,
            unit=unit,
            bring_catalog_name=catalog_name,
            is_staple=staple,
            is_watchlist=name == "Kaffee",
            **values,
        )
        created_articles += 1
    session.flush()

    index = name_index(session)
    units = {
        row.id: Unit(row.unit) for row in session.scalars(select(m.Article))
    }
    existing_dishes = {row.lower() for row in session.scalars(select(m.Dish.name))}
    created_dishes = 0
    for (
        name, portions, packable, effort, suitable, side, protein, cuisine, ingredient_text
    ) in DISHES:
        if name.lower() in existing_dishes:
            continue
        rows = []
        for line in parse_lines(ingredient_text, index, units):
            if line.article_id is None:
                continue
            rows.append(
                IngredientInput(
                    article_id=line.article_id,
                    quantity=_as_decimal(line.quantity),
                    unit=line.unit,
                )
            )
        categories = [CategoryInput(axis=CategoryAxis.SIDE, name=side)] if side else []
        if protein:
            categories.append(CategoryInput(axis=CategoryAxis.PROTEIN, name=protein))
        if cuisine:
            categories.append(CategoryInput(axis=CategoryAxis.CUISINE, name=cuisine))
        create_dish(
            session,
            name=name,
            portions=portions,
            packable=packable,
            effort=effort,
            suitable_for=suitable,
            ingredients=rows,
            categories=categories,
        )
        created_dishes += 1
    session.flush()
    return {"articles": created_articles, "dishes": created_dishes}


def _as_decimal(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))
