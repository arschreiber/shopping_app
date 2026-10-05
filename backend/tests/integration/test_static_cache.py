"""Was der Browser behalten darf - und was er bei jedem Laden neu erfragen muss.

Nach einem Neubau zeigte der Browser weiter die alte Oberfläche: `index.html` kam ohne
Cache-Header, und ohne Vorgabe darf ein Browser selbst schätzen, wie lange er sie
aufhebt. Im Heimnetz über http gibt es auch keinen Service Worker, der das auffängt -
der braucht https oder localhost.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mealplan import main as main_module


@pytest.fixture
def frontend(tmp_path, monkeypatch, engine, settings):
    """Ein Mini-Build statt des echten: der ist nicht eingecheckt und im Test nicht da."""
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text(
        "<!doctype html><script type=module src=/assets/index-abc123.js></script>"
    )
    (static / "assets" / "index-abc123.js").write_text("console.log('app')")
    (static / "sw.js").write_text("self.addEventListener('install', () => {})")
    monkeypatch.setattr(main_module, "STATIC_DIR", static)
    with TestClient(main_module.create_app(settings)) as client:
        yield client


@pytest.mark.parametrize("path", ["/", "/week/2026-W40", "/dishes/3", "/sw.js"])
def test_the_app_shell_is_asked_for_on_every_load(frontend, path):
    """`no-cache` heißt nicht "nie speichern", sondern "vor jeder Nutzung nachfragen"."""
    response = frontend.get(path)
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-cache"


def test_hashed_assets_are_kept_for_good(frontend):
    """Vite hängt einen Inhalts-Hash an: ändert sich die Datei, ändert sich ihr Name."""
    response = frontend.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "public, max-age=31536000, immutable"
