"""Artikel-Router: Korpus, Combobox-Vorschläge, Bring!-Katalog."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from ...services import articles as service
from ...services import nutrients as nutrient_service
from ..deps import CatalogDep, SessionDep
from ..schemas.common import (
    ArticleBlsIn,
    ArticleIn,
    ArticleOut,
    ArticlePatch,
    ArticleSuggestion,
    BlsFoodOut,
    CatalogSuggestionOut,
    MergeIn,
    MicroFieldOut,
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


@router.get("/micro-fields", response_model=list[MicroFieldOut])
def micro_fields() -> list[MicroFieldOut]:
    """Die Etikett-Felder in Anzeigereihenfolge, Folsäure als eigenes Feld bei Folat."""
    from ...domain.micronutrients import FOLIC_ACID, MICRONUTRIENTS

    out: list[MicroFieldOut] = []
    for nutrient in MICRONUTRIENTS:
        out.append(
            MicroFieldOut(
                code=nutrient.code,
                label=nutrient.label,
                unit=nutrient.unit,
                group=nutrient.group,
                kind=nutrient.kind,
            )
        )
        if nutrient.code == "FOL":
            out.append(
                MicroFieldOut(
                    code=FOLIC_ACID, label="Folsäure", unit="µg", group=nutrient.group
                )
            )
    return out


@router.get("/bls-search", response_model=list[BlsFoodOut])
def bls_search(session: SessionDep, q: str = Query(min_length=2)) -> list[BlsFoodOut]:
    """Im Bundeslebensmittelschlüssel suchen - alle Wörter müssen vorkommen."""
    return [
        BlsFoodOut(code=hit.code, name=hit.name, score=hit.score)
        for hit in nutrient_service.search(session, q)
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
        max_unit_price=payload.max_unit_price,
        min_offer_amount=payload.min_offer_amount,
        regular_pack_amount=payload.regular_pack_amount,
        regular_pack_price=payload.regular_pack_price,
        regular_pack_unit=payload.regular_pack_unit,
        piece_size=payload.piece_size,
        kcal=payload.kcal,
        carbs_g=payload.carbs_g,
        fat_g=payload.fat_g,
        protein_g=payload.protein_g,
        label_micros=payload.label_micros,
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


@router.get("/{article_id}/bls-suggestions", response_model=list[BlsFoodOut])
def bls_suggestions(session: SessionDep, article_id: int) -> list[BlsFoodOut]:
    """Vorschläge für die BLS-Referenz - übernommen wird nur, was jemand wählt."""
    article = service.get_article(session, article_id)
    return [
        BlsFoodOut(code=hit.code, name=hit.name, score=hit.score)
        for hit in nutrient_service.suggestions_for(session, article)
    ]


@router.put("/{article_id}/bls", response_model=ArticleOut)
def set_bls(session: SessionDep, article_id: int, payload: ArticleBlsIn) -> ArticleOut:
    """Referenz setzen, bewusst keine, oder lösen - Fehler kommen als 422."""
    article = service.get_article(session, article_id)
    if payload.code:
        nutrient_service.link(
            session, article, payload.code, grams_per_unit=payload.grams_per_unit
        )
    elif payload.skip:
        nutrient_service.skip(session, article)
    else:
        nutrient_service.unlink(session, article)
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
