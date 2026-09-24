"""CLI (ARCHITECTURE.md §10 Meilenstein B): Planen und kalibrieren *ohne UI*.

    mealplan plan --week 2026-W37          # Vorschlag rechnen und anzeigen
    mealplan plan --week 2026-W37 --apply  # und speichern
    mealplan weights                       # aktuelle Gewichte zeigen
    mealplan weights --set rotation_cap=15 # kalibrieren (Spike 4)
    mealplan list --week 2026-W37          # Einkaufsliste als Text
    mealplan seed-demo                     # Beispieldaten zum Ausprobieren
    mealplan catalog-refresh               # Bring!-Katalog cachen
"""

from __future__ import annotations

from datetime import date

import typer

from ..config import get_settings
from ..db.session import session_scope
from ..domain.diagnostics import diagnose
from ..domain.render import render_plan, render_warnings
from ..services import planning, settings_store, shopping_list
from ..services.weeks import format_iso, get_or_create_week

app = typer.Typer(help="Wochenplan & Einkauf - Kommandozeile", no_args_is_help=True)


def _current_iso() -> str:
    today = date.today().isocalendar()
    return format_iso(today.year, today.week)


@app.command()
def plan(
    week: str = typer.Option(None, "--week", "-w", help="ISO-Woche, z. B. 2026-W37"),
    apply: bool = typer.Option(False, "--apply", help="Vorschlag in die DB schreiben"),
    only_empty: bool = typer.Option(False, "--only-empty", help="nur leere Slots fuellen"),
    reasons: bool = typer.Option(True, "--reasons/--no-reasons"),
) -> None:
    """Auto-Vorschlag rechnen und anzeigen."""
    iso = week or _current_iso()
    with session_scope() as session:
        if apply:
            result = planning.propose_week(session, iso, only_empty=only_empty)
            plan_obj, snapshot, warnings = result.plan, result.snapshot, result.warnings
        else:
            from ..domain.planner import propose

            week_row = get_or_create_week(session, iso)
            snapshot, current = planning.build_context(session, week_row)
            pinned = {
                key: current.get(key)
                for key in current.assignments
                if snapshot.slot(key).pinned
            }
            plan_obj = propose(snapshot, pinned, seed=week_row.planner_seed)
            warnings = diagnose(plan_obj, snapshot)
            session.rollback()

        typer.echo(f"Woche {iso}" + ("  (gespeichert)" if apply else "  (Vorschau)"))
        typer.echo("=" * 60)
        typer.echo(render_plan(plan_obj, snapshot, with_reasons=reasons))
        typer.echo("")
        typer.echo(render_warnings(warnings))


@app.command()
def show(week: str = typer.Option(None, "--week", "-w")) -> None:
    """Gespeicherten Plan einer Woche anzeigen."""
    iso = week or _current_iso()
    with session_scope() as session:
        week_row = get_or_create_week(session, iso)
        snapshot, current = planning.build_context(session, week_row)
        typer.echo(f"Woche {iso}")
        typer.echo("=" * 60)
        typer.echo(render_plan(current, snapshot))
        typer.echo("")
        typer.echo(render_warnings(diagnose(current, snapshot)))


@app.command(name="list")
def shopping_list_cmd(week: str = typer.Option(None, "--week", "-w")) -> None:
    """Einkaufsliste als Text (auch der Bring!-Fallback)."""
    iso = week or _current_iso()
    with session_scope() as session:
        shopping = shopping_list.get_list(session, iso)
        typer.echo(shopping_list.as_text(session, shopping))


@app.command()
def weights(
    set_: list[str] = typer.Option(None, "--set", help="z. B. rotation_cap=15"),
    reset: bool = typer.Option(False, "--reset", help="auf Defaults zurücksetzen"),
) -> None:
    """Planer-Gewichte anzeigen und kalibrieren (Spike 4, ohne Deploy).

    Geschrieben wird in einer eigenen Transaktion, *vor* der Ausgabe: sonst geht die
    Änderung verloren, sobald die Ausgabe abbricht (`mealplan weights --set … | head`).
    """
    if reset or set_:
        with session_scope() as session:
            if reset:
                settings_store.put(session, settings_store.KEY_WEIGHTS, {})
            if set_:
                current = dict(settings_store.weights(session).to_mapping())
                for pair in set_:
                    if "=" not in pair:
                        raise typer.BadParameter(f"'{pair}' ist kein key=value")
                    key, value = pair.split("=", 1)
                    if key not in current:
                        raise typer.BadParameter(f"'{key}' ist kein Gewicht")
                    current[key] = float(value)
                settings_store.put(session, settings_store.KEY_WEIGHTS, current)
        if reset:
            typer.echo("Gewichte auf Defaults zurückgesetzt.")
        if set_:
            typer.echo(f"{len(set_)} Gewicht(e) gespeichert.")

    with session_scope() as session:
        for key, value in sorted(settings_store.weights(session).to_mapping().items()):
            typer.echo(f"  {key:<32} {value:>8}")


@app.command()
def catalog_refresh() -> None:
    """Bring!-Katalog neu cachen (~380 Artikel, für Icons und Kategorien)."""
    from ..integrations.catalog.bring_catalog import refresh_cache

    settings = get_settings()
    settings.ensure_dirs()
    count = refresh_cache(settings.catalog_dir)
    if count:
        typer.echo(f"{count} Katalogeintraege gecacht nach {settings.catalog_dir}")
    else:
        typer.secho("Katalog konnte nicht geladen werden.", fg=typer.colors.YELLOW)


@app.command()
def push(week: str = typer.Option(None, "--week", "-w")) -> None:
    """Einkaufsliste nach Bring! pushen (oder Text-Fallback ausgeben)."""
    from ..main import build_sync
    from ..services import bring_sync

    iso = week or _current_iso()
    sync = build_sync(get_settings())
    with session_scope() as session:
        shopping_list.get_list(session, iso, rebuild_first=True)
        outcome = bring_sync.push(session, iso, sync)
    result = outcome.result
    typer.echo(f"Adapter: {sync.name}, {outcome.items_sent} Artikel")
    if result.ok:
        typer.secho("Push ok", fg=typer.colors.GREEN)
        if result.text_fallback:
            typer.echo(result.text_fallback)
    else:
        typer.secho(f"Push fehlgeschlagen: {result.error}", fg=typer.colors.RED)
        typer.echo(result.text_fallback or "")


@app.command()
def seed_demo() -> None:
    """Beispiel-Gerichte und -Artikel anlegen, um die App auszuprobieren."""
    from .demo import seed

    with session_scope() as session:
        created = seed(session)
    typer.echo(
        f"{created['articles']} Artikel und {created['dishes']} Gerichte angelegt."
    )


if __name__ == "__main__":
    app()
