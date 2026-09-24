"""Angebots-Matching (ARCHITECTURE.md §5, general_plan.md §8 Nr. 4).

Reihenfolge: bestaetigter Cache -> RapidFuzz gegen die Alias-Liste -> "Unzugeordnet".
Ein LLM-Schiedsrichter ist als Port vorgesehen, aber im MVP nicht implementiert.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.enums import MatchDecider
from ..matching.normalize import FUZZY_THRESHOLD, best_match, normalize
from .articles import ValidationError, alias_index


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    offer_id: int
    article_id: int | None
    score: float
    decided_by: MatchDecider


def unavailable_pairs(session: Session) -> set[tuple[int, int]]:
    """(article_id, store_id), die dort gar nicht gesucht werden (Plan §7)."""
    rows = session.execute(
        select(m.ArticleStoreAvailability.article_id, m.ArticleStoreAvailability.store_id)
        .where(m.ArticleStoreAvailability.available.is_(False))
    ).all()
    return {(article_id, store_id) for article_id, store_id in rows}


def match_snapshot(session: Session, snapshot: m.OfferSnapshot) -> list[MatchOutcome]:
    aliases = alias_index(session)
    blocked = unavailable_pairs(session)
    reachable = {
        article_id: names
        for article_id, names in aliases.items()
        if (article_id, snapshot.store_id) not in blocked
    }
    cache = {
        row.normalized_offer_name: row
        for row in session.scalars(
            select(m.OfferMatch).where(m.OfferMatch.store_id == snapshot.store_id)
        )
    }

    out: list[MatchOutcome] = []
    for offer in snapshot.offers:
        key = normalize(offer.raw_name)
        cached = cache.get(key)
        if cached is not None and cached.confirmed:
            out.append(
                MatchOutcome(
                    offer.id,
                    cached.article_id,
                    float(cached.score or 0),
                    MatchDecider.USER,
                )
            )
            continue

        hit = best_match(offer.raw_name, reachable, threshold=FUZZY_THRESHOLD)
        article_id, score = hit if hit else (None, 0.0)
        out.append(MatchOutcome(offer.id, article_id, score, MatchDecider.FUZZY))
        if cached is None:
            session.add(
                m.OfferMatch(
                    normalized_offer_name=key,
                    store_id=snapshot.store_id,
                    article_id=article_id,
                    score=score,
                    decided_by=MatchDecider.FUZZY.value,
                    confirmed=False,
                )
            )
        else:
            cached.article_id = article_id
            cached.score = score
    session.flush()
    return out


def confirm(
    session: Session,
    *,
    offer_name: str,
    store_id: int | None,
    article_id: int | None,
) -> m.OfferMatch:
    """Ein-Klick-Zuordnung aus der "Unzugeordnet"-Ansicht.

    Der Cache hängt am *normalisierten Namen*, nicht an der Angebots-ID - dieselbe
    Zuordnung greift damit auch in den Folgewochen (ARCHITECTURE.md §3).
    """
    if article_id is not None and session.get(m.Article, article_id) is None:
        raise ValidationError(f"Artikel {article_id} existiert nicht")
    key = normalize(offer_name)
    row = session.scalar(
        select(m.OfferMatch).where(
            m.OfferMatch.normalized_offer_name == key, m.OfferMatch.store_id == store_id
        )
    )
    if row is None:
        row = m.OfferMatch(
            normalized_offer_name=key,
            store_id=store_id,
            decided_by=MatchDecider.USER.value,
        )
        session.add(row)
    row.article_id = article_id
    row.decided_by = MatchDecider.USER.value
    row.confirmed = True
    row.score = 100.0
    session.flush()
    return row
