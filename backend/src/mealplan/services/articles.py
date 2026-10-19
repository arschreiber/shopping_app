"""Artikel-Use-Cases: Korpus pflegen, Combobox-Vorschläge, Inline-Anlage."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..db import models as m
from ..domain.enums import AliasKind, Unit
from ..domain.units import CANONICAL_UNITS, DIMENSION_OF, Quantity
from ..matching.normalize import Suggestion, normalize, search
from ..matching.normalize import suggest as suggest_names

# Nährwerte je kanonischer Einheit (100 g / 100 ml / 1 Stück), alle optional.
NUTRITION_FIELDS = ("kcal", "carbs_g", "fat_g", "protein_g")
# Felder, bei denen `None` eine Aussage ist und darum durchkommen muss
CLEARABLE_FIELDS = (
    *NUTRITION_FIELDS,
    "bring_catalog_name",  # leer: auf Bring! unter dem Artikelnamen
    "max_unit_price",
    "min_offer_amount",
    "regular_pack_amount",
    "regular_pack_price",
    "regular_pack_unit",
    "piece_size",
)


class ValidationError(ValueError):
    """Fachlicher Eingabefehler -> HTTP 422 (ARCHITECTURE.md §6)."""


def list_articles(session: Session, *, query: str | None = None) -> list[m.Article]:
    stmt = select(m.Article).order_by(m.Article.canonical_name)
    if query:
        stmt = stmt.where(m.Article.canonical_name.icontains(query))
    return list(session.scalars(stmt))


def get_article(session: Session, article_id: int) -> m.Article:
    article = session.get(m.Article, article_id)
    if article is None:
        raise ValidationError(f"Artikel {article_id} existiert nicht")
    return article


def create_article(
    session: Session,
    *,
    canonical_name: str,
    unit: Unit,
    bring_catalog_name: str | None = None,
    bring_category: str | None = None,
    is_staple: bool = False,
    is_watchlist: bool = False,
    aliases: list[str] | None = None,
    max_unit_price: Decimal | None = None,
    min_offer_amount: Decimal | None = None,
    regular_pack_amount: Decimal | None = None,
    regular_pack_price: Decimal | None = None,
    regular_pack_unit: str | None = None,
    piece_size: Decimal | None = None,
    **nutrition,
) -> m.Article:
    name = canonical_name.strip()
    if not name:
        raise ValidationError("Artikelname fehlt")
    if unit not in CANONICAL_UNITS:
        raise ValidationError(
            f"'{unit.value}' ist keine kanonische Einheit - erlaubt: "
            + ", ".join(u.value for u in CANONICAL_UNITS)
        )
    existing = session.scalar(
        select(m.Article).where(func.lower(m.Article.canonical_name) == name.lower())
    )
    if existing is not None:
        raise ValidationError(f"'{name}' gibt es schon")

    article = m.Article(
        canonical_name=name,
        unit=unit.value,
        bring_catalog_name=bring_catalog_name,
        bring_category=bring_category,
        is_staple=is_staple,
        is_watchlist=is_watchlist,
        max_unit_price=max_unit_price,
        min_offer_amount=min_offer_amount,
        regular_pack_amount=regular_pack_amount,
        regular_pack_price=regular_pack_price,
        regular_pack_unit=regular_pack_unit,
        piece_size=piece_size,
        **{
            field: value
            for field, value in nutrition.items()
            if field in NUTRITION_FIELDS
        },
    )
    _check_regular_price(article)
    session.add(article)
    session.flush()
    for alias in aliases or []:
        add_alias(session, article, alias)
    return article


def update_article(session: Session, article_id: int, **changes) -> m.Article:
    article = get_article(session, article_id)
    if "unit" in changes and changes["unit"] is not None:
        unit = Unit(changes.pop("unit"))
        if unit not in CANONICAL_UNITS:
            raise ValidationError(f"'{unit.value}' ist keine kanonische Einheit")
        _guard_unit_change(session, article, unit)
        article.unit = unit.value
        if unit is Unit.STUECK:
            # Ein Stück-Artikel *ist* in Stück - Stückgewicht und "pro Stück" sind leer.
            article.piece_size = None
            article.regular_pack_unit = None
            changes.pop("piece_size", None)
            changes.pop("regular_pack_unit", None)
    aliases = changes.pop("aliases", None)
    for field, value in changes.items():
        if not hasattr(article, field):
            continue
        # Bei Nährwerten ist `None` eine Aussage ("nicht erfasst") und `0` eine andere
        # ("enthält nichts davon") - beide müssen durchkommen. Beim Richtpreis heißt
        # `None` "jedes Angebot zählt".
        if field in CLEARABLE_FIELDS or value is not None:
            setattr(article, field, value)
    _check_regular_price(article)
    if aliases is not None:
        article.aliases.clear()
        session.flush()
        for alias in aliases:
            add_alias(session, article, alias)
    return article


def _check_regular_price(article: m.Article) -> None:
    """Normalpreis = Menge *und* Preis ("250 g für 1,29 €") - eins allein sagt nichts.

    Pro Stück ("1 Stück für 0,79 €") geht er bei Gramm- und Milliliter-Artikeln nur mit
    Stückgewicht; bei Stück-Artikeln ist "pro Stück" ohnehin die Einheit.
    """
    name = article.canonical_name
    unit = Unit(article.unit)
    if article.piece_size is not None:
        if unit is Unit.STUECK:
            raise ValidationError(f"{name}: ein Stück-Artikel braucht kein Stückgewicht")
        if article.piece_size <= 0:
            raise ValidationError(f"{name}: das Stückgewicht muss über 0 sein")
    amount, price = article.regular_pack_amount, article.regular_pack_price
    if (amount is None) != (price is None):
        raise ValidationError(f"{name}: der Normalpreis braucht Menge und Preis")
    if amount is not None and (amount <= 0 or price <= 0):
        raise ValidationError(f"{name}: Menge und Preis müssen über 0 sein")
    if amount is None or unit is Unit.STUECK:
        article.regular_pack_unit = None  # ohne Normalpreis bzw. ohnehin in Stück
    elif article.regular_pack_unit not in (None, Unit.STUECK.value):
        raise ValidationError(f"{name}: unbekannte Einheit für den Normalpreis")
    elif article.regular_pack_unit == Unit.STUECK.value and article.piece_size is None:
        raise ValidationError(
            f"{name}: für einen Normalpreis pro Stück braucht der Artikel ein Stückgewicht"
        )


def _guard_unit_change(session: Session, article: m.Article, unit: Unit) -> None:
    """Einheit nur wechseln, wenn keine Zutat in einer anderen Dimension hängt."""
    from ..domain.units import DIMENSION_OF

    used = session.scalars(
        select(m.Ingredient.unit).where(m.Ingredient.article_id == article.id).distinct()
    ).all()
    clashing = [u for u in used if DIMENSION_OF[Unit(u)] != DIMENSION_OF[unit]]
    if clashing:
        raise ValidationError(
            f"'{article.canonical_name}' wird in {', '.join(sorted(set(clashing)))} "
            f"verwendet - Wechsel auf {unit.value} würde die Mengen verfälschen"
        )


def add_alias(
    session: Session, article: m.Article, alias: str, kind: AliasKind = AliasKind.ALIAS
) -> None:
    cleaned = alias.strip()
    if not cleaned:
        return
    if any(a.alias.lower() == cleaned.lower() for a in article.aliases):
        return
    session.add(m.ArticleAlias(article_id=article.id, alias=cleaned, kind=kind.value))


def delete_article(session: Session, article_id: int) -> None:
    article = get_article(session, article_id)
    used = session.scalar(
        select(func.count()).select_from(m.Ingredient).where(
            m.Ingredient.article_id == article_id
        )
    )
    if used:
        raise ValidationError(
            f"'{article.canonical_name}' steht in {used} Zutatenzeile(n) - erst dort entfernen"
        )
    session.delete(article)


def name_index(session: Session) -> dict[int, list[str]]:
    """`{article_id: [kanonischer Name]}` - die *eine* Identität einer Zutat.

    Bewusst ohne Aliase: eine Zutat heißt genau so, wie sie heißt. Wer "Basmatireis"
    tippt, soll das vorhandene "Reis" *vorgeschlagen* bekommen und es auswählen -
    nicht eine zweite Schreibweise anlegen, die später niemand mehr überblickt.
    """
    return {
        article.id: [article.canonical_name]
        for article in session.scalars(select(m.Article))
    }


def alias_index(session: Session) -> dict[int, list[str]]:
    """Namen *plus* Aliase - nur für das Angebots-Matching (general_plan.md §7).

    Dort sind Aliase fachlich nötig: ein Angebot heißt "Gut & Günstig Schafskäse", der
    Artikel heißt "Hirtenkäse". Für die Erfassung von Zutaten gilt `name_index`.
    """
    out: dict[int, list[str]] = {}
    for article in session.scalars(select(m.Article)):
        names = [article.canonical_name]
        names.extend(alias.alias for alias in article.aliases)
        if article.bring_catalog_name:
            names.append(article.bring_catalog_name)
        out[article.id] = names
    return out


def suggest(session: Session, query: str, *, limit: int = 50) -> list[tuple[m.Article, str]]:
    """Combobox: erst die Artikel, die mit `query` anfangen, dann die, die ihn enthalten.

    Gesucht wird allein im kanonischen Namen - Zweitnamen gibt es nicht, und der
    Bring!-Katalogname ist eine Angabe für Bring!, kein zweiter Zutatenname.
    """
    articles = {a.id: a for a in session.scalars(select(m.Article))}
    if not articles:
        return []
    haystack = {
        article_id: names[0] for article_id, names in name_index(session).items()
    }
    return [
        (articles[article_id], kind)
        for article_id, kind in search(query, haystack, limit=limit)
    ]


def staple_ids(session: Session) -> frozenset[int]:
    return frozenset(
        session.scalars(select(m.Article.id).where(m.Article.is_staple.is_(True)))
    )


# --------------------------------------------------------- Dubletten vermeiden & beheben


def suggestions_for(
    session: Session, name: str, *, limit: int = 6
) -> list[tuple[m.Article, Suggestion]]:
    """Vorhandene Artikel, die zu `name` passen *könnten* - für die Zutaten-Erfassung.

    Der Zweck ist Sparsamkeit im Korpus: wer "Basmatireis" tippt und schon "Reis" hat,
    soll das sehen, statt eine dritte Reissorte anzulegen. Entschieden wird von Hand -
    automatisch zusammenzulegen wäre geraten.
    """
    hits = suggest_names(name, name_index(session), limit=limit)
    if not hits:
        return []
    articles = {
        article.id: article
        for article in session.scalars(
            select(m.Article).where(m.Article.id.in_([hit.key for hit in hits]))
        )
    }
    return [(articles[hit.key], hit) for hit in hits if hit.key in articles]


def merge_articles(
    session: Session,
    *,
    target_id: int,
    source_ids: list[int],
) -> m.Article:
    """Führt Artikel zusammen: alle Verweise wandern auf `target_id`.

    Zutatenzeilen, Listeneinträge, Angebots-Zuordnungen und Bring!-Zustand werden
    umgehängt, danach sind die Quellen weg - mit ihren Namen. Genau das ist der Zweck:
    hinterher gibt es "Reis", nicht "Reis" mit zwei Zweitnamen.

    Verschiedene Dimensionen werden abgelehnt: 2 Stück Zwiebeln und 150 g Zwiebeln
    lassen sich nicht summieren, und stillschweigend zu raten wäre falsch
    (general_plan.md §8 Nr. 10).
    """
    target = get_article(session, target_id)
    sources = []
    for source_id in dict.fromkeys(source_ids):
        if source_id == target_id:
            continue
        source = get_article(session, source_id)
        if DIMENSION_OF[Unit(source.unit)] != DIMENSION_OF[Unit(target.unit)]:
            raise ValidationError(
                f"'{source.canonical_name}' wird in {source.unit} geführt, "
                f"'{target.canonical_name}' in {target.unit} - verschiedene Dimensionen "
                "lassen sich nicht zusammenführen"
            )
        sources.append(source)
    if not sources:
        raise ValidationError("Keine Artikel zum Zusammenführen angegeben")

    for source in sources:
        _move_ingredients(session, source, target)
        _move_shopping_items(session, source, target)
        _move_aliases(session, source, target)
        _move_availability(session, source, target)
        _move_bring_state(session, source, target)
        session.execute(
            update(m.OfferMatch)
            .where(m.OfferMatch.article_id == source.id)
            .values(article_id=target.id)
        )
        # Flags übernehmen: wer eine Quelle als Grundvorrat geführt hat, meinte das ernst.
        target.is_staple = target.is_staple or source.is_staple
        target.is_watchlist = target.is_watchlist or source.is_watchlist
        if not target.bring_catalog_name and source.bring_catalog_name:
            target.bring_catalog_name = source.bring_catalog_name
        if target.max_unit_price is None and source.max_unit_price is not None:
            target.max_unit_price = source.max_unit_price
        if target.min_offer_amount is None and source.min_offer_amount is not None:
            target.min_offer_amount = source.min_offer_amount
        if target.piece_size is None and source.piece_size is not None:
            target.piece_size = source.piece_size
        if target.regular_pack_amount is None and source.regular_pack_amount is not None:
            target.regular_pack_amount = source.regular_pack_amount
            target.regular_pack_price = source.regular_pack_price
            target.regular_pack_unit = source.regular_pack_unit
        session.delete(source)

    session.flush()
    session.refresh(target)
    return target


def _move_ingredients(session: Session, source: m.Article, target: m.Article) -> None:
    """Zeilen umhängen. Hat ein Gericht beide Artikel, werden die Mengen addiert."""
    rows = list(
        session.scalars(select(m.Ingredient).where(m.Ingredient.article_id == source.id))
    )
    for row in rows:
        twin = session.scalar(
            select(m.Ingredient).where(
                m.Ingredient.dish_id == row.dish_id,
                m.Ingredient.article_id == target.id,
            )
        )
        if twin is None:
            row.article_id = target.id
            continue
        merged = Quantity(twin.quantity, Unit(twin.unit)) + Quantity(row.quantity, Unit(row.unit))
        twin.quantity = merged.amount
        twin.unit = merged.unit.value
        session.delete(row)
    session.flush()


def _move_shopping_items(session: Session, source: m.Article, target: m.Article) -> None:
    rows = list(
        session.scalars(
            select(m.ShoppingListItem).where(m.ShoppingListItem.article_id == source.id)
        )
    )
    for row in rows:
        twin = session.scalar(
            select(m.ShoppingListItem).where(
                m.ShoppingListItem.shopping_list_id == row.shopping_list_id,
                m.ShoppingListItem.article_id == target.id,
            )
        )
        if twin is None:
            row.article_id = target.id
            continue
        merged = Quantity(twin.quantity, Unit(twin.unit)) + Quantity(row.quantity, Unit(row.unit))
        twin.quantity = merged.amount
        twin.unit = merged.unit.value
        twin.have_already = twin.have_already and row.have_already
        session.delete(row)
    session.flush()


def _move_aliases(session: Session, source: m.Article, target: m.Article) -> None:
    """Angebots-Aliase der Quelle übernehmen, Dubletten verwerfen.

    Der *Name* der Quelle wird nicht zum Alias: Zutaten haben genau einen Namen.
    """
    existing = {normalize(alias.alias) for alias in target.aliases}
    existing.add(normalize(target.canonical_name))
    for alias in list(source.aliases):
        if normalize(alias.alias) in existing:
            session.delete(alias)
            continue
        alias.article_id = target.id
        existing.add(normalize(alias.alias))
    session.flush()


def _move_availability(session: Session, source: m.Article, target: m.Article) -> None:
    rows = list(
        session.scalars(
            select(m.ArticleStoreAvailability).where(
                m.ArticleStoreAvailability.article_id == source.id
            )
        )
    )
    for row in rows:
        twin = session.get(m.ArticleStoreAvailability, (target.id, row.store_id))
        if twin is None:
            session.add(
                m.ArticleStoreAvailability(
                    article_id=target.id, store_id=row.store_id, available=row.available
                )
            )
        else:
            twin.available = twin.available and row.available
        session.delete(row)
    session.flush()


def _move_bring_state(session: Session, source: m.Article, target: m.Article) -> None:
    """Bring!-Zustand der Quelle verwerfen, wenn das Ziel schon einen hat.

    Der nächste Push gleicht ohnehin ab; zwei Zustände für denselben Artikel wären
    dagegen eine Duplikatquelle (general_plan.md §8 Nr. 8).
    """
    rows = list(
        session.scalars(
            select(m.BringSyncItem).where(m.BringSyncItem.article_id == source.id)
        )
    )
    for row in rows:
        twin = session.scalar(
            select(m.BringSyncItem).where(
                m.BringSyncItem.bring_list_uuid == row.bring_list_uuid,
                m.BringSyncItem.article_id == target.id,
            )
        )
        if twin is None:
            row.article_id = target.id
        else:
            session.delete(row)
    session.flush()
