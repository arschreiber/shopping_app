"""SQLAlchemy-2.0-Modelle (ARCHITECTURE.md §3).

Phase-2-Tabellen (`store`, `offer*`) werden von Anfang an angelegt und erst später
bespielt - Migrationen sind billiger als Rework.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ..domain.enums import (
    AliasKind,
    AssignmentKind,
    CategoryAxis,
    Chain,
    Effort,
    ItemSource,
    ListStatus,
    MatchDecider,
    Meal,
    SlotSpecial,
    SuitableFor,
    SyncKind,
    SyncStatus,
    TimeBudget,
    Unit,
)


class Base(DeclarativeBase):
    type_annotation_map = {
        dict[str, Any]: JSON,
        list[int]: JSON,
        Decimal: Numeric(10, 3, asdecimal=True),
        datetime: DateTime(timezone=True),
        date: Date,
    }


def _enum(enum_cls, length: int = 24) -> String:
    """Enums als String-Spalten: lesbare SQLite-Dumps, migrationsarme Erweiterung."""
    return String(length)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


# ------------------------------------------------------------------------------ Artikel


class Article(Base, TimestampMixin):
    __tablename__ = "article"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(120), unique=True)
    unit: Mapped[str] = mapped_column(_enum(Unit), default=Unit.G.value)
    bring_category: Mapped[str | None] = mapped_column(String(60))
    bring_catalog_name: Mapped[str | None] = mapped_column(String(120))
    is_staple: Mapped[bool] = mapped_column(Boolean, default=False)
    is_watchlist: Mapped[bool] = mapped_column(Boolean, default=False)
    # So viel der Artikel-Einheit ist ein Stück ("1 Avocado ≈ 200 g") - nur bei Gramm- und
    # Milliliter-Artikeln. Macht Angebote pro Stück mit Richt- und Normalpreis vergleichbar.
    piece_size: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    note: Mapped[str | None] = mapped_column(Text)
    # Richtpreis: Angebote darüber zählen für diesen Artikel nicht. In der Einheit des
    # Artikels - €/kg bei G, €/l bei ML, €/Stück bei STUECK. NULL = jedes Angebot zählt.
    max_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # Angebote zählen erst ab dieser Packungsgröße, in der Einheit des Artikels
    # ("Heidelbeeren ab 400 g"). NULL = jede Packung.
    min_offer_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    # Normalpreis, so wie man einkauft: "250 g für 1,29 €" - Menge in der Einheit des
    # Artikels. Daraus wird der Grundpreis gerechnet (domain/unit_price.py). Beide oder
    # keins; unabhängig vom Richtpreis (Eigenmarke vs. Markenangebot).
    regular_pack_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    regular_pack_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    # NULL = Menge in der Einheit des Artikels; "STUECK" = Anzahl Stück ("1 Stück für
    # 0,79 €"), umgerechnet über `piece_size`.
    regular_pack_unit: Mapped[str | None] = mapped_column(String(10))

    # Nährwerte, alle optional. Die Bezugsgröße ergibt sich aus `unit` und braucht
    # deshalb kein eigenes Feld: je 100 g, je 100 ml oder je 1 Stück. Ohne Werte bleibt
    # der Artikel einfach ungezählt - sichtbar als Lücke, nicht als stille Null.
    kcal: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    carbs_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    aliases: Mapped[list[ArticleAlias]] = relationship(
        back_populates="article", cascade="all, delete-orphan", lazy="selectin"
    )
    __table_args__ = (
        CheckConstraint("unit in ('STUECK','G','ML')", name="ck_article_canonical_unit"),
    )


class ArticleAlias(Base):
    __tablename__ = "article_alias"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(_enum(AliasKind), default=AliasKind.ALIAS.value)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("store.id", ondelete="SET NULL"))

    article: Mapped[Article] = relationship(back_populates="aliases")
    __table_args__ = (UniqueConstraint("article_id", "alias", name="uq_alias"),)


# ---------------------------------------------------------------------------- Gerichte


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    axis: Mapped[str] = mapped_column(_enum(CategoryAxis))
    name: Mapped[str] = mapped_column(String(60))

    __table_args__ = (UniqueConstraint("axis", "name", name="uq_category"),)


class Dish(Base, TimestampMixin):
    __tablename__ = "dish"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    portions: Mapped[int] = mapped_column(Integer, default=3)
    packable: Mapped[bool] = mapped_column(Boolean, default=True)
    # Nicht aufwärmbar (Salat mit Dressing, knusprig Gebratenes ...): Reste taugen nichts,
    # also nur in einer Größe kochen, die genau aufgeht (domain/eligibility.py).
    reheatable: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("1"))
    # 2er-Gerichte: auf 4 verdoppeln; 1er-Gerichte: doppelt bzw. dreifach kochen.
    # 3er-Gerichte werden nie vervielfacht (domain/model.py `DishSpec.factors`).
    allow_double: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("1")
    )
    allow_triple: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("0")
    )
    effort: Mapped[str] = mapped_column(_enum(Effort), default=Effort.NORMAL.value)
    suitable_for: Mapped[str] = mapped_column(
        _enum(SuitableFor), default=SuitableFor.BOTH.value
    )
    rating: Mapped[int | None] = mapped_column(Integer)
    prep_text: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)

    ingredients: Mapped[list[Ingredient]] = relationship(
        back_populates="dish",
        cascade="all, delete-orphan",
        order_by="Ingredient.sort_order",
        lazy="selectin",
    )
    categories: Mapped[list[Category]] = relationship(
        secondary="dish_category", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("portions in (1, 2, 3)", name="ck_dish_portions"),
        CheckConstraint("rating is null or rating between 1 and 5", name="ck_dish_rating"),
    )


class DishCategory(Base):
    __tablename__ = "dish_category"

    dish_id: Mapped[int] = mapped_column(
        ForeignKey("dish.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.id", ondelete="CASCADE"), primary_key=True
    )


class Ingredient(Base):
    __tablename__ = "ingredient"

    id: Mapped[int] = mapped_column(primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("dish.id", ondelete="CASCADE"))
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id", ondelete="RESTRICT"))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))  # NULL = nach Bedarf
    unit: Mapped[str] = mapped_column(_enum(Unit))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(String(120))

    dish: Mapped[Dish] = relationship(back_populates="ingredients")
    article: Mapped[Article] = relationship(lazy="selectin")

    __table_args__ = (Index("ix_ingredient_article", "article_id"),)


# -------------------------------------------------------------------------------- Woche


class Week(Base, TimestampMixin):
    __tablename__ = "week"

    id: Mapped[int] = mapped_column(primary_key=True)
    iso_year: Mapped[int] = mapped_column(Integer)
    iso_week: Mapped[int] = mapped_column(Integer)
    primary_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("store.id", ondelete="SET NULL")
    )
    secondary_store_id: Mapped[int | None] = mapped_column(
        ForeignKey("store.id", ondelete="SET NULL")
    )
    planner_seed: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistisches Locking
    note: Mapped[str | None] = mapped_column(Text)

    slots: Mapped[list[Slot]] = relationship(
        back_populates="week",
        cascade="all, delete-orphan",
        # Fachliche Reihenfolge: Tag, dann Mittag vor Abend. Nach der String-Spalte
        # sortiert stünde DINNER vor LUNCH.
        order_by="Slot.day, case((Slot.meal == 'LUNCH', 0), else_=1)",
        lazy="selectin",
    )
    __table_args__ = (UniqueConstraint("iso_year", "iso_week", name="uq_week"),)


class Slot(Base):
    __tablename__ = "slot"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("week.id", ondelete="CASCADE"))
    day: Mapped[int] = mapped_column(Integer)  # 0 = Montag
    meal: Mapped[str] = mapped_column(_enum(Meal))
    eaters_home: Mapped[int] = mapped_column(Integer, default=2)
    packed_portions: Mapped[int] = mapped_column(Integer, default=0)
    packed_fresh: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("0"))
    time_budget: Mapped[str] = mapped_column(
        _enum(TimeBudget), default=TimeBudget.NORMAL.value
    )
    special: Mapped[str] = mapped_column(_enum(SlotSpecial), default=SlotSpecial.NONE.value)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    week: Mapped[Week] = relationship(back_populates="slots")
    assignment: Mapped[SlotAssignment | None] = relationship(
        back_populates="slot",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
        foreign_keys="SlotAssignment.slot_id",
    )
    # Was in diesem Slot wirklich passiert ist, soweit jemand etwas dazu gesagt hat
    # (heute nur "ausgefallen"). Kein delete-orphan: der Verlauf überlebt den Slot.
    cook_entries: Mapped[list[CookLog]] = relationship(
        back_populates="slot", lazy="selectin", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("week_id", "day", "meal", name="uq_slot"),
        CheckConstraint("day between 0 and 6", name="ck_slot_day"),
        CheckConstraint("eaters_home between 0 and 2", name="ck_slot_eaters"),
        CheckConstraint("packed_portions between 0 and 2", name="ck_slot_packed"),
    )


class SlotAssignment(Base):
    __tablename__ = "slot_assignment"

    slot_id: Mapped[int] = mapped_column(
        ForeignKey("slot.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(_enum(AssignmentKind))
    dish_id: Mapped[int | None] = mapped_column(ForeignKey("dish.id", ondelete="CASCADE"))
    factor: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    leftover_source_slot_id: Mapped[int | None] = mapped_column(
        ForeignKey("slot.id", ondelete="CASCADE")
    )
    portions_used: Mapped[int | None] = mapped_column(Integer)
    score_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    slot: Mapped[Slot] = relationship(back_populates="assignment", foreign_keys=[slot_id])
    dish: Mapped[Dish | None] = relationship(lazy="selectin")


class CookLog(Base):
    """Trennt "geplant" von "gekocht" (general_plan.md §8 Nr. 11).

    Ein geplantes Gericht gilt als gekocht, sobald sein Tag da ist - dafür braucht es
    keine Zeile. Eine Zeile gibt es nur, wenn jemand etwas dazu gesagt hat:
    `confirmed = false` mit `slot_id` heißt "ausgefallen" (zählt nicht), `confirmed =
    true` ist ein ausdrücklich bestätigtes Kochen, auch ohne Plan.
    """

    __tablename__ = "cook_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("slot.id", ondelete="SET NULL"))
    dish_id: Mapped[int] = mapped_column(ForeignKey("dish.id", ondelete="CASCADE"))
    cooked_at: Mapped[date] = mapped_column(Date)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)

    slot: Mapped[Slot | None] = relationship(back_populates="cook_entries")

    __table_args__ = (
        Index("ix_cook_log_dish", "dish_id", "cooked_at"),
        CheckConstraint("rating is null or rating between 1 and 5", name="ck_cook_rating"),
    )


# ------------------------------------------------------------------------ Einkaufsliste


class ShoppingList(Base, TimestampMixin):
    __tablename__ = "shopping_list"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("week.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(_enum(ListStatus), default=ListStatus.DRAFT.value)
    sent_at: Mapped[datetime | None] = mapped_column()

    items: Mapped[list[ShoppingListItem]] = relationship(
        back_populates="shopping_list", cascade="all, delete-orphan", lazy="selectin"
    )


class ShoppingListItem(Base):
    __tablename__ = "shopping_list_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    shopping_list_id: Mapped[int] = mapped_column(
        ForeignKey("shopping_list.id", ondelete="CASCADE")
    )
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    unit: Mapped[str] = mapped_column(_enum(Unit))
    source: Mapped[str] = mapped_column(_enum(ItemSource), default=ItemSource.RECIPE.value)
    have_already: Mapped[bool] = mapped_column(Boolean, default=False)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("store.id", ondelete="SET NULL"))
    spec_text: Mapped[str | None] = mapped_column(String(120))
    from_dish_ids: Mapped[list[int] | None] = mapped_column(JSON)

    shopping_list: Mapped[ShoppingList] = relationship(back_populates="items")
    article: Mapped[Article] = relationship(lazy="selectin")

    __table_args__ = (
        UniqueConstraint("shopping_list_id", "article_id", name="uq_list_article"),
    )


class BringSyncItem(Base):
    """Eigene UUIDs - damit der Push nie Fremdeinträge anfasst (Plan §8 Nr. 8)."""

    __tablename__ = "bring_sync_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"))
    bring_list_uuid: Mapped[str] = mapped_column(String(64))
    bring_item_uuid: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(120))
    last_spec: Mapped[str | None] = mapped_column(String(120))
    last_pushed_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint("bring_list_uuid", "article_id", name="uq_bring_item"),
    )


class SyncRun(Base):
    """Jeder Push/Fetch wird protokolliert und ist in der UI sichtbar (ARCHITECTURE §8)."""

    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(_enum(SyncKind))
    status: Mapped[str] = mapped_column(_enum(SyncStatus))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (Index("ix_sync_run_kind", "kind", "started_at"),)


class Setting(Base):
    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON)


# ------------------------------------------------------------------- Phase 2: Angebote


class Store(Base):
    """Ein Laden, in dem eingekauft wird - mit oder ohne Angebote.

    `offer_source` NULL heißt: keine Angebote abrufen (Allfrisch veröffentlicht seine
    nur in der Edeka-App). Die PLZ gehört zum *Laden*, nicht zum Haushalt: Korbunio
    findet einen Rewe-Markt nur über dessen eigene PLZ.
    """

    __tablename__ = "store"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    chain: Mapped[str] = mapped_column(_enum(Chain))
    postal_code: Mapped[str | None] = mapped_column(String(5))
    market_id: Mapped[str | None] = mapped_column(String(60))
    offer_source: Mapped[str | None] = mapped_column(String(40))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)


class ArticleStoreAvailability(Base):
    __tablename__ = "article_store_availability"

    article_id: Mapped[int] = mapped_column(
        ForeignKey("article.id", ondelete="CASCADE"), primary_key=True
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("store.id", ondelete="CASCADE"), primary_key=True
    )
    available: Mapped[bool] = mapped_column(Boolean, default=True)


class OfferSnapshot(Base):
    __tablename__ = "offer_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("store.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(40))
    fetched_at: Mapped[datetime] = mapped_column(server_default=func.now())
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(_enum(SyncStatus))
    offer_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Welchen Markt die Quelle tatsächlich genommen hat ("REWE Heinrichstr. 37") -
    # Korbunio wählt bei Edeka selbst, das soll man sehen können.
    market_label: Mapped[str | None] = mapped_column(String(200))
    market_url: Mapped[str | None] = mapped_column(String(500))  # Angebotsseite des Markts
    source_detail: Mapped[str | None] = mapped_column(String(60))  # "offiziell", "Marktguru"
    error: Mapped[str | None] = mapped_column(Text)

    offers: Mapped[list[Offer]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    __table_args__ = (Index("ix_snapshot_store", "store_id", "fetched_at"),)


class Offer(Base):
    __tablename__ = "offer"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("offer_snapshot.id", ondelete="CASCADE")
    )
    raw_name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(80))
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    base_price: Mapped[str | None] = mapped_column(String(60))
    pack: Mapped[str | None] = mapped_column(String(60))
    category: Mapped[str | None] = mapped_column(String(60))
    description: Mapped[str | None] = mapped_column(String(300))  # Prospekttext
    image_url: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(500))  # das Angebot bei der Quelle
    # Grundpreis, beim Speichern vergleichbar gemacht (domain/unit_price.py)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    unit_price_unit: Mapped[str | None] = mapped_column(String(10))  # kg | l | Stück
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    image_path: Mapped[str | None] = mapped_column(String(200))

    snapshot: Mapped[OfferSnapshot] = relationship(back_populates="offers")


class OfferMatch(Base):
    """Cache auf dem *normalisierten Namen*, nicht auf `offer_id` - überlebt die Woche."""

    __tablename__ = "offer_match"

    id: Mapped[int] = mapped_column(primary_key=True)
    normalized_offer_name: Mapped[str] = mapped_column(String(200))
    store_id: Mapped[int | None] = mapped_column(ForeignKey("store.id", ondelete="CASCADE"))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"))
    score: Mapped[float | None] = mapped_column(Numeric(6, 2))
    decided_by: Mapped[str] = mapped_column(_enum(MatchDecider))
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("normalized_offer_name", "store_id", name="uq_offer_match"),
    )
