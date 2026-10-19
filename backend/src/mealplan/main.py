"""App-Factory (ARCHITECTURE.md §1, §6, §8).

**Keine Auth - bewusst.** Die App ist im Heimnetz ohne Anmeldung erreichbar, weil das
den Alltag spuerbar vereinfacht (ARCHITECTURE.md §0). Jedes Geraet im LAN kann lesen
*und* schreiben, IoT-Geraete eingeschlossen. Die eine Regel, die daraus folgt:

    NIEMALS einen oeffentlich erreichbaren Reverse-Proxy davorsetzen, ohne vorher Auth
    nachzuruesten. Von aussen ist Tailscale der Weg, im Router wird kein Port auf 8080
    weitergeleitet.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.routers import articles, dishes, shopping, stores, system, weeks
from .config import Settings, get_settings
from .db.session import get_engine, set_engine
from .integrations.bring.bring_sync import BringSync
from .integrations.bring.text_export import TextExportSync
from .integrations.catalog.bring_catalog import FileBringCatalog, refresh_cache
from .ports import OfferSource, ShoppingListSync
from .services.articles import ValidationError
from .services.weeks import ConflictError

LOG = logging.getLogger("mealplan")
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Ohne Cache-Header darf der Browser selbst schätzen, wie lange er eine Datei aufhebt -
# nach einem Neubau lief dann die alte Oberfläche weiter. Deshalb ausdrücklich:
# `index.html` & Co. bei jedem Laden nachfragen, die gehashten Assets für immer behalten.
SHELL_CACHE = {"Cache-Control": "no-cache"}
ASSET_CACHE = "public, max-age=31536000, immutable"


class _HashedAssets(StaticFiles):
    """Vite hängt jedem Dateinamen einen Inhalts-Hash an: was hier liegt, ändert sich nie."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = ASSET_CACHE
        return response


def build_sync(settings: Settings) -> ShoppingListSync:
    """Adapterwahl (ARCHITECTURE.md §5): ohne Zugangsdaten bleibt es der Text-Export."""
    if settings.bring_sync == "bring" and settings.bring_email and settings.bring_password:
        return BringSync(settings.bring_email, settings.bring_password, settings.bring_list_name)
    if settings.bring_sync == "bring":
        LOG.warning("Bring!-Sync gewünscht, aber Zugangsdaten fehlen - nutze Text-Export")
    return TextExportSync()


def build_offer_source(settings: Settings) -> OfferSource | None:
    """Ohne Korbunio-URL gibt es keine Angebote - alles andere läuft normal."""
    if not settings.korbunio_url:
        return None
    from .integrations.offers.korbunio import KorbunioOfferSource

    return KorbunioOfferSource(settings.korbunio_url)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.ensure_dirs()
        get_engine()
        catalog = FileBringCatalog(settings.catalog_dir)
        if settings.catalog_autofetch and not catalog.is_cached():
            count = refresh_cache(settings.catalog_dir)
            LOG.info("Bring!-Katalog geladen: %s Einträge", count)
        app.state.catalog = getattr(app.state, "catalog", None) or catalog
        app.state.sync = getattr(app.state, "sync", None) or build_sync(settings)
        if not hasattr(app.state, "offer_source"):
            app.state.offer_source = build_offer_source(settings)
        LOG.info(
            "Bereit auf %s:%s - Sync-Adapter: %s (keine Auth, nur Heimnetz)",
            settings.host,
            settings.port,
            app.state.sync.name,
        )
        scheduler = None
        if settings.offer_fetch_enabled and app.state.offer_source is not None:
            from .jobs.scheduler import start_scheduler

            scheduler = start_scheduler(settings, app.state.offer_source)
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    app = FastAPI(
        title="Wochenplan & Einkauf",
        version="0.1.0",
        summary="Wochenplan bauen, Einkaufsliste erzeugen, nach Bring! pushen",
        lifespan=lifespan,
    )

    @app.exception_handler(ValidationError)
    async def _validation(_request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _conflict(_request: Request, exc: ConflictError) -> JSONResponse:
        """Laptop und Handy gleichzeitig -> 409 mit der aktuellen Version."""
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc), "current_version": exc.current_version},
        )

    @app.exception_handler(KeyError)
    async def _key_error(_request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"nicht gefunden: {exc}"})

    for router in (
        articles.router,
        dishes.router,
        weeks.router,
        shopping.router,
        stores.router,
        system.router,
    ):
        app.include_router(router)

    if STATIC_DIR.exists():
        # Gebaute Assets direkt, alles andere auf index.html: React Router braucht den
        # SPA-Fallback auch für tiefe Pfade wie /week/2026-W37. `StaticFiles(html=True)`
        # liefert index.html nur für Verzeichnisse, nicht für beliebige Routen.
        app.mount(
            "/assets", _HashedAssets(directory=STATIC_DIR / "assets"), name="assets"
        )

        @app.get("/{full_path:path}", include_in_schema=False)
        async def _spa(full_path: str) -> FileResponse:
            if full_path.startswith(("api/", "openapi.json", "docs", "redoc")):
                raise HTTPException(status_code=404, detail="nicht gefunden")
            candidate = (STATIC_DIR / full_path).resolve()
            if (
                full_path
                and candidate.is_file()
                and candidate.is_relative_to(STATIC_DIR.resolve())
            ):
                return FileResponse(candidate, headers=SHELL_CACHE)
            return FileResponse(STATIC_DIR / "index.html", headers=SHELL_CACHE)

    else:

        @app.get("/", include_in_schema=False)
        def _no_frontend() -> dict:
            return {
                "status": "backend läuft",
                "hinweis": "Frontend nicht gebaut - siehe README (npm run build)",
                "api": "/docs",
            }

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "mealplan.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


__all__ = ["app", "create_app", "run", "set_engine"]
