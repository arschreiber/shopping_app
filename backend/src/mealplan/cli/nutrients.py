"""`mealplan nutrients ...` - BLS-Referenzen pflegen, ohne die App aufzumachen.

    mealplan nutrients sync                   # BLS einlesen, links.json übernehmen,
                                              # offene Artikel mit Vorschlägen zeigen
    mealplan nutrients suggest [--json]       # nur die Vorschläge
    mealplan nutrients search "linse rot"     # im BLS suchen
    mealplan nutrients link Reis C352000      # zuordnen
    mealplan nutrients link Öl Q180000 --grams-per-unit 0.92
    mealplan nutrients skip "Monster Energy"  # bewusst ohne Referenz
    mealplan nutrients unlink Reis
    mealplan nutrients export [DATEI]         # Entscheidungen als JSON
    mealplan nutrients apply DATEI [--overwrite]
    mealplan nutrients dish "Chili sin Carne" # ein Gericht durchrechnen

Im Container: `sudo docker compose exec app python -m mealplan.cli.main nutrients sync`.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import typer
from sqlalchemy import select

from ..config import get_settings
from ..db import models as m
from ..db.session import session_scope
from ..domain.enums import Unit
from ..domain.micronutrients import MICRONUTRIENTS, REFERENCE_PERSON
from ..domain.model import IngredientSpec
from ..integrations.nutrients import bls
from ..services import nutrients as service

app = typer.Typer(help="Nährstoffe aus dem Bundeslebensmittelschlüssel", no_args_is_help=True)


def _fail(error: Exception) -> None:
    typer.secho(str(error), fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _unit_hint(article: m.Article) -> str:
    unit = Unit(article.unit)
    if unit is Unit.STUECK:
        return "  (Stück: --grams-per-unit = Gramm je Stück nötig)"
    if unit is Unit.ML:
        return "  (ml: Dichte 1, bei Öl --grams-per-unit 0.92)"
    return ""


def _print_suggestions(session, articles: list[m.Article], limit: int) -> None:
    for article in articles:
        typer.secho(
            f"{article.canonical_name} [#{article.id}, {article.unit}]{_unit_hint(article)}",
            bold=True,
        )
        hits = service.suggestions_for(session, article, limit=limit)
        if not hits:
            typer.echo("    - kein Vorschlag -")
        for hit in hits:
            typer.echo(f"    {hit.score:5.1f}  {hit.code}  {hit.name}")


@app.command()
def sync(
    file: Path = typer.Option(None, "--file", help="ZIP oder Excel statt Download"),
    force: bool = typer.Option(False, "--force", help="auch bei unveränderter Datei einlesen"),
    limit: int = typer.Option(5, "--limit", help="Vorschläge je Artikel"),
) -> None:
    """Der Lauf alle paar Wochen: einlesen, Entscheidungen übernehmen, offene zeigen."""
    settings = get_settings()
    settings.ensure_dirs()
    try:
        path = file or bls.locate_or_download(settings.catalog_dir)
    except bls.BlsSourceMissing as error:
        _fail(error)

    with session_scope() as session:
        result = service.import_bls(session, path, force=force)
    if result.imported:
        typer.echo(f"BLS eingelesen: {result.foods} Lebensmittel aus {path.name}")
    else:
        typer.echo(f"BLS unverändert ({result.foods} Lebensmittel)")

    links = service.links_path(settings.catalog_dir)
    decisions = service.read_links(links)
    if decisions:
        with session_scope() as session:
            applied = service.apply_links(session, decisions)
        typer.echo(
            f"{links.name}: {len(applied.applied)} übernommen, "
            f"{len(applied.kept)} schon entschieden"
            + (f", unbekannt: {', '.join(applied.unknown)}" if applied.unknown else "")
        )

    with session_scope() as session:
        open_ = service.open_articles(session)
        typer.echo(f"\n{len(open_)} Artikel ohne Referenz\n")
        _print_suggestions(session, open_, limit)


@app.command()
def suggest(
    article: str = typer.Argument(None, help="Name oder #ID; ohne: alle offenen"),
    limit: int = typer.Option(5, "--limit"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Vorschläge für offene Artikel (oder einen bestimmten)."""
    with session_scope() as session:
        if not service.has_foods(session):
            _fail(service.NutrientError("Noch kein BLS eingelesen - erst `sync`."))
        try:
            articles = [service.find_article(session, article)] if article else (
                service.open_articles(session)
            )
        except service.NutrientError as error:
            _fail(error)
        if as_json:
            payload = [
                {
                    "article": a.canonical_name,
                    "id": a.id,
                    "unit": a.unit,
                    "suggestions": [
                        {"code": s.code, "name": s.name, "score": s.score}
                        for s in service.suggestions_for(session, a, limit=limit)
                    ],
                }
                for a in articles
            ]
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _print_suggestions(session, articles, limit)


@app.command()
def search(query: str, limit: int = typer.Option(20, "--limit")) -> None:
    """Im BLS suchen - alle Wörter müssen im Namen vorkommen."""
    with session_scope() as session:
        for hit in service.search(session, query, limit=limit):
            typer.echo(f"{hit.code}  {hit.name}")


@app.command()
def link(
    article: str,
    code: str,
    grams_per_unit: str = typer.Option(
        None, "--grams-per-unit", help="Gramm je Stück (STUECK) oder Dichte (ML)"
    ),
) -> None:
    """Artikel einem BLS-Eintrag zuordnen."""
    with session_scope() as session:
        try:
            row = service.find_article(session, article)
            grams = Decimal(grams_per_unit.replace(",", ".")) if grams_per_unit else None
            service.link(session, row, code.upper(), grams_per_unit=grams)
        except service.NutrientError as error:
            _fail(error)
        food = service.get_food(session, row.bls_code)
        typer.echo(f"{row.canonical_name} -> {food.code} {food.name}")
        if Unit(row.unit) is Unit.STUECK and row.bls_grams_per_unit is None:
            typer.secho(
                "  Ohne --grams-per-unit zählt der Artikel im Gericht noch nicht.",
                fg=typer.colors.YELLOW,
            )


@app.command()
def skip(article: str) -> None:
    """Bewusst ohne Referenz (kein passender BLS-Eintrag)."""
    with session_scope() as session:
        try:
            row = service.find_article(session, article)
        except service.NutrientError as error:
            _fail(error)
        service.skip(session, row)
        typer.echo(f"{row.canonical_name}: ohne Referenz")


@app.command()
def unlink(article: str) -> None:
    """Zuordnung lösen - der Artikel ist wieder offen."""
    with session_scope() as session:
        try:
            row = service.find_article(session, article)
        except service.NutrientError as error:
            _fail(error)
        service.unlink(session, row)
        typer.echo(f"{row.canonical_name}: wieder offen")


@app.command()
def export(target: Path = typer.Argument(None, help="Datei; ohne: auf die Konsole")) -> None:
    """Alle Entscheidungen als JSON (Format von links.json)."""
    with session_scope() as session:
        payload = {"articles": service.export_links(session)}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if target:
        target.write_text(text + "\n", encoding="utf-8")
        typer.echo(f"{len(payload['articles'])} Entscheidungen nach {target}")
    else:
        typer.echo(text)


@app.command()
def apply(
    source: Path,
    overwrite: bool = typer.Option(False, "--overwrite", help="auch Entschiedenes ersetzen"),
) -> None:
    """Entscheidungen aus einer JSON-Datei übernehmen."""
    decisions = service.read_links(source)
    with session_scope() as session:
        try:
            result = service.apply_links(session, decisions, overwrite=overwrite)
        except service.NutrientError as error:
            _fail(error)
    typer.echo(f"{len(result.applied)} übernommen, {len(result.kept)} schon entschieden")
    if result.unknown:
        typer.secho(f"Unbekannte Artikel: {', '.join(result.unknown)}", fg=typer.colors.YELLOW)


@app.command()
def dish(name: str) -> None:
    """Mikronährstoffe eines Gerichts je Portion."""
    with session_scope() as session:
        row = session.scalar(select(m.Dish).where(m.Dish.name == name))
        if row is None:
            _fail(service.NutrientError(f"Gericht '{name}' nicht gefunden"))
        lines = [
            IngredientSpec(article_id=i.article_id, quantity=i.quantity, unit=Unit(i.unit))
            for i in row.ingredients
        ]
        result = service.dish_micros(session, lines, portions=row.portions)
        names = dict(session.execute(select(m.Article.id, m.Article.canonical_name)).all())

    typer.secho(f"{name} - je Portion ({row.portions} Portionen)", bold=True)
    for nutrient in MICRONUTRIENTS:
        value = result.get(nutrient.code)
        if value is None:
            continue
        share = f"{value.share:>4} %" if value.share is not None else "      "
        flag = " *" if value.partial else ""
        typer.echo(f"  {nutrient.label:<24} {value.amount:>9} {nutrient.unit:<3} {share}{flag}")
    typer.echo(f"\n  % = Anteil am Tageswert ({REFERENCE_PERSON})")
    typer.echo("  * = nicht für alle Zutaten bekannt")
    for label, ids in (
        ("ohne Referenz", result.missing_ids),
        ("bewusst ohne Referenz", result.skipped_ids),
        ("ohne Menge/Stückgewicht", result.open_quantity_ids),
    ):
        if ids:
            typer.echo(f"  {label}: {', '.join(names.get(i, f'#{i}') for i in ids)}")
