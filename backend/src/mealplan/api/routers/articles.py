"""Artikel-Router: Korpus, Combobox-Vorschläge, Bring!-Katalog."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from ...services import articles as service
from ..deps import CatalogDep, SessionDep
from ..schemas.common import (
    ArticleIn,
    ArticleOut,
    ArticlePatch,
    ArticleSuggestion,
    CatalogSuggestionOut,
    MergeIn,
)

router = APIRouter(prefix="/api/articles", tags=["articles"])


@router.get("", response_model=list[ArticleOut])
def list_articles(session: SessionDep, q: str | None = None) -> list[ArticleOut]:
    return [ArticleOut.of(a) for a in service.list_articles(session, query=q)]


@router.get("/suggest", response_model=list[ArticleSuggestion])
def suggest(session: SessionDep, q: str = Query(min_length=1)) -> list[ArticleSuggestion]:
    """Namenssuche für die Zutaten-Combobox: erst Präfix, dann Teilstring."""
    return [
        ArticleSuggestion(article=ArticleOut.of(article), kind=kind)
        for article, kind in service.suggest(session, q)
    ]


@router.get("/catalog-suggest", response_model=list[CatalogSuggestionOut])
def catalog_suggest(
    catalog: CatalogDep, q: str = Query(min_length=1)
) -> list[CatalogSuggestionOut]:
    """Bring!-Katalogname vorschlagen - nur exakte Namen bekommen dort ein Icon."""
    return [
        CatalogSuggestionOut(name=s.name, category=s.category, score=s.score)
        for s in catalog.suggest(q)
    ]


@router.post("", response_model=ArticleOut, status_code=status.HTTP_201_CREATED)
def create_article(session: SessionDep, payload: ArticleIn) -> ArticleOut:
    article = service.create_article(
        session,
        canonical_name=payload.canonical_name,
        unit=payload.unit,
        bring_catalog_name=payload.bring_catalog_name,
        bring_category=payload.bring_category,
        is_staple=payload.is_staple,
        is_watchlist=payload.is_watchlist,
        aliases=payload.aliases,
        kcal=payload.kcal,
        carbs_g=payload.carbs_g,
        fat_g=payload.fat_g,
        protein_g=payload.protein_g,
    )
    session.flush()
    session.refresh(article)
    return ArticleOut.of(article)


@router.get("/{article_id}", response_model=ArticleOut)
def get_article(session: SessionDep, article_id: int) -> ArticleOut:
    return ArticleOut.of(service.get_article(session, article_id))


@router.patch("/{article_id}", response_model=ArticleOut)
def update_article(session: SessionDep, article_id: int, payload: ArticlePatch) -> ArticleOut:
    article = service.update_article(
        session, article_id, **payload.model_dump(exclude_unset=True)
    )
    session.flush()
    session.refresh(article)
    return ArticleOut.of(article)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(session: SessionDep, article_id: int) -> None:
    service.delete_article(session, article_id)


@router.post("/{article_id}/merge", response_model=ArticleOut)
def merge(session: SessionDep, article_id: int, payload: MergeIn) -> ArticleOut:
    """Versehentlich doppelt angelegte Artikel auf diesen zusammenführen.

    Zutatenzeilen, Listeneinträge und Angebots-Zuordnungen wandern mit; die Quellen
    verschwinden samt Namen. Der Weg zurück ist ein neuer Artikel, kein Undo.
    """
    article = service.merge_articles(
        session, target_id=article_id, source_ids=payload.source_ids
    )
    return ArticleOut.of(article)
