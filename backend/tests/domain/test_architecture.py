"""Die eine Grenze, die zählt: `domain/` ist I/O-frei (ARCHITECTURE.md §2, §9)."""

from __future__ import annotations

import ast
from pathlib import Path

DOMAIN = Path(__file__).resolve().parents[2] / "src" / "mealplan" / "domain"
FORBIDDEN_PROJECT = {"db", "api", "integrations", "services", "jobs", "matching", "config"}
FORBIDDEN_EXTERNAL = {
    "sqlalchemy", "fastapi", "httpx", "aiohttp", "pydantic", "alembic", "bring_api",
    "requests", "apscheduler", "typer",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
        elif isinstance(node, ast.ImportFrom) and node.level > 0:
            names.add(f".{node.module or ''}")
    return names


def test_domain_imports_no_io():
    offenders: list[str] = []
    for path in sorted(DOMAIN.glob("*.py")):
        for name in _imports(path):
            root = name.split(".")[0]
            if root in FORBIDDEN_EXTERNAL:
                offenders.append(f"{path.name}: {name}")
            if name.startswith("mealplan."):
                package = name.split(".")[1]
                if package in FORBIDDEN_PROJECT:
                    offenders.append(f"{path.name}: {name}")
    assert not offenders, "domain/ darf kein I/O importieren:\n" + "\n".join(offenders)


def test_domain_has_no_datetime_now():
    """Keine Uhr in der Domäne - `Clock`/Datum kommt als Parameter (ARCHITECTURE.md §4)."""
    offenders = [
        path.name
        for path in DOMAIN.glob("*.py")
        if "datetime.now(" in path.read_text(encoding="utf-8")
        or "date.today(" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"Uhr in der Domäne: {offenders}"
