"""Pydantic-DTOs, getrennt von ORM und Domäne (ARCHITECTURE.md §6)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...domain.enums import (
    AssignmentKind,
    CategoryAxis,
    Chain,
    Effort,
    ItemSource,
    ListStatus,
    Meal,
    SlotSpecial,
    SuitableFor,
    SyncKind,
    SyncStatus,
    TimeBudget,
    Unit,
    WarningLevel,
)


class Dto(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ------------------------------------------------------------------------------ Artikel


class NutrientsOut(Dto):
    kcal: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    protein_g: Decimal


class DishNutritionOut(Dto):
    """Nährwerte je Portion plus die Lücken, die dahinter stecken."""

    per_portion: NutrientsOut
    total: NutrientsOut
    is_complete: bool
    has_any: bool
    counted: int
    ingredient_count: int
    missing_article_ids: list[int]
    open_quantity_article_ids: list[int]


class ArticleOut(Dto):
    id: int
    canonical_name: str
    unit: Unit
    bring_catalog_name: str | None = None
    bring_category: str | None = None
    is_staple: bool
    is_watchlist: bool
    aliases: list[str] = Field(default_factory=list)
    # Richtpreis in €/kg (G), €/l (ML) oder €/Stück - darüber zählt kein Angebot.
    max_unit_price: Decimal | None = None
    # Angebote erst ab dieser Packungsgröße (in `unit`) - kleinere zählen nicht
    min_offer_amount: Decimal | None = None
    # Normalpreis, wie eingekauft: Menge (in `unit`) und Preis - und der Grundpreis daraus
    regular_pack_amount: Decimal | None = None
    regular_pack_price: Decimal | None = None
    regular_pack_unit: Literal["STUECK"] | None = None  # None = in der Einheit des Artikels
    regular_unit_price: Decimal | None = None
    # So viel der Artikel-Einheit ist ein Stück ("1 Avocado ≈ 200 g") - nur bei G und ML
    piece_size: Decimal | None = None
    # Nährwerte je 100 g / 100 ml / Stück - die Bezugsgröße steckt in `unit`.
    kcal: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    protein_g: Decimal | None = None
    nutrition_basis: str = ""

    @classmethod
    def of(cls, article) -> ArticleOut:
        from ...domain.nutrition import BASIS_LABEL
        from ...domain.unit_price import pack_unit_price
        from ...domain.units import trim

        unit = Unit(article.unit)
        return cls(
            id=article.id,
            canonical_name=article.canonical_name,
            unit=unit,
            bring_catalog_name=article.bring_catalog_name,
            bring_category=article.bring_category,
            is_staple=article.is_staple,
            is_watchlist=article.is_watchlist,
            aliases=[a.alias for a in article.aliases],
            max_unit_price=article.max_unit_price,
            min_offer_amount=trim(article.min_offer_amount),
            regular_pack_amount=trim(article.regular_pack_amount),
            regular_pack_price=article.regular_pack_price,
            regular_pack_unit=article.regular_pack_unit,
            regular_unit_price=pack_unit_price(
                article.regular_pack_amount,
                article.regular_pack_price,
                unit,
                in_pieces=article.regular_pack_unit == Unit.STUECK.value,
                piece_size=article.piece_size,
            ),
            piece_size=trim(article.piece_size),
            kcal=trim(article.kcal),
            carbs_g=trim(article.carbs_g),
            fat_g=trim(article.fat_g),
            protein_g=trim(article.protein_g),
            nutrition_basis=BASIS_LABEL.get(unit, ""),
        )


class ArticleIn(Dto):
    canonical_name: str
    unit: Unit = Unit.G
    bring_catalog_name: str | None = None
    bring_category: str | None = None
    is_staple: bool = False
    is_watchlist: bool = False
    aliases: list[str] = Field(default_factory=list)
    max_unit_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    min_offer_amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    regular_pack_amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    regular_pack_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    regular_pack_unit: Literal["STUECK"] | None = None
    piece_size: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    kcal: Decimal | None = Field(default=None, ge=0)
    carbs_g: Decimal | None = Field(default=None, ge=0)
    fat_g: Decimal | None = Field(default=None, ge=0)
    protein_g: Decimal | None = Field(default=None, ge=0)


class ArticlePatch(Dto):
    canonical_name: str | None = None
    unit: Unit | None = None
    bring_catalog_name: str | None = None
    bring_category: str | None = None
    is_staple: bool | None = None
    is_watchlist: bool | None = None
    aliases: list[str] | None = None
    max_unit_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    min_offer_amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    regular_pack_amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=3)
    regular_pack_price: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    regular_pack_unit: Literal["STUECK"] | None = None
    piece_size: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    kcal: Decimal | None = Field(default=None, ge=0)
    carbs_g: Decimal | None = Field(default=None, ge=0)
    fat_g: Decimal | None = Field(default=None, ge=0)
    protein_g: Decimal | None = Field(default=None, ge=0)


class ArticleSuggestion(Dto):
    article: ArticleOut
    # Aus der Combobox: "PREFIX" = Name fängt mit der Eingabe an, "CONTAINS" = enthält
    # sie. Aus dem Parser: "COMPOUND" = teilt einen Wortbestandteil ("Basmatireis" /
    # "Reis"), "FUZZY" = nur ähnlich geschrieben.
    kind: str = "FUZZY"
    # Nur die Parser-Vorschläge sind bewertet; die Namenssuche ordnet statt zu punkten.
    score: float | None = None
    matched_name: str | None = None


class MergeIn(Dto):
    source_ids: list[int]


class CatalogSuggestionOut(Dto):
    name: str
    category: str | None
    score: float


# ----------------------------------------------------------------------------- Gerichte


class CategoryOut(Dto):
    id: int
    axis: CategoryAxis
    name: str
    usage: int = 0


class CategoryIn(Dto):
    axis: CategoryAxis
    name: str


class IngredientOut(Dto):
    article_id: int
    article_name: str
    quantity: Decimal | None
    unit: Unit
    spec_text: str
    note: str | None = None


class IngredientIn(Dto):
    article_id: int
    quantity: Decimal | None = None
    unit: Unit
    note: str | None = None


class DishOut(Dto):
    id: int
    name: str
    portions: int
    packable: bool
    reheatable: bool
    effort: Effort
    suitable_for: SuitableFor
    rating: int | None
    prep_text: str | None
    note: str | None
    archived: bool
    allow_double: bool  # am Gericht erlaubt
    allow_triple: bool
    factors: list[int]  # tatsächlich erlaubt, z. B. [1, 2] = auch doppelt kochbar
    categories: list[CategoryOut]
    ingredients: list[IngredientOut]
    last_cooked: date | None = None
    weeks_since_cooked: int | None = None
    nutrition: DishNutritionOut | None = None


class DishSummary(Dto):
    id: int
    name: str
    portions: int
    packable: bool
    reheatable: bool
    allow_double: bool
    allow_triple: bool
    factors: list[int]
    effort: Effort
    suitable_for: SuitableFor
    rating: int | None
    categories: list[CategoryOut]
    ingredient_count: int
    last_cooked: date | None = None
    weeks_since_cooked: int | None = None
    nutrition: DishNutritionOut | None = None


class DishIn(Dto):
    name: str
    portions: int = Field(ge=1, le=3)
    packable: bool = True
    reheatable: bool = True
    allow_double: bool = True
    allow_triple: bool = False
    effort: Effort = Effort.NORMAL
    suitable_for: SuitableFor = SuitableFor.BOTH
    rating: int | None = Field(default=None, ge=1, le=5)
    prep_text: str | None = None
    note: str | None = None
    ingredients: list[IngredientIn] = Field(default_factory=list)
    categories: list[CategoryIn] = Field(default_factory=list)


class DishPatch(Dto):
    name: str | None = None
    portions: int | None = Field(default=None, ge=1, le=3)
    packable: bool | None = None
    reheatable: bool | None = None
    allow_double: bool | None = None
    allow_triple: bool | None = None
    effort: Effort | None = None
    suitable_for: SuitableFor | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    prep_text: str | None = None
    note: str | None = None
    archived: bool | None = None
    ingredients: list[IngredientIn] | None = None
    categories: list[CategoryIn] | None = None


class NutritionPreviewIn(Dto):
    portions: int = Field(ge=1, le=3)
    ingredients: list[IngredientIn] = Field(default_factory=list)


class CookConfirmIn(Dto):
    dish_id: int
    cooked_at: date
    slot_day: int | None = None
    slot_meal: Meal | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None


# ------------------------------------------------------------------------------- Parser


class ParseIn(Dto):
    text: str


class ParsedLineOut(Dto):
    raw: str
    name: str
    quantity: Decimal | None
    unit: Unit
    article_id: int | None
    article_name: str | None
    confidence: float
    note: str | None
    suggested_unit: Unit
    unit_conflict: bool = False
    catalog_suggestion: str | None = None
    # Vorhandene Artikel, die gemeint sein könnten - gegen "Reis" dreimal im Korpus.
    suggestions: list[ArticleSuggestion] = Field(default_factory=list)


class ParseOut(Dto):
    lines: list[ParsedLineOut]


# --------------------------------------------------------------------------------- Woche


class ContributionOut(Dto):
    rule: str
    delta: float
    text: str


class ScoreOut(Dto):
    total: float
    contributions: list[ContributionOut]
    reasons: list[str]


class AssignmentOut(Dto):
    kind: AssignmentKind
    dish_id: int | None = None
    dish_name: str | None = None
    factor: int = 1  # 2 = doppelt, 3 = dreifach gekocht
    portions: int | None = None
    leftover_source_day: int | None = None
    leftover_source_meal: Meal | None = None
    leftover_source_label: str | None = None
    portions_used: int | None = None
    score: ScoreOut | None = None
    cancelled: bool = False  # ausgefallen: zählt nicht als gekocht


class SlotOut(Dto):
    day: int
    meal: Meal
    date: date
    eaters_home: int
    packed_portions: int
    packed_fresh: bool  # Mitnehm-Portionen frisch gekocht statt vorgekocht
    time_budget: TimeBudget
    special: SlotSpecial
    pinned: bool
    demand: int
    assignment: AssignmentOut | None = None


class SlotIn(Dto):
    day: int = Field(ge=0, le=6)
    meal: Meal
    eaters_home: int = Field(ge=0, le=2)
    packed_portions: int = Field(ge=0, le=2)
    packed_fresh: bool = False
    time_budget: TimeBudget
    special: SlotSpecial = SlotSpecial.NONE
    pinned: bool = False


class StandardSlotIn(Dto):
    """Eine Mahlzeit der Standardwoche - das Raster ohne Plan, Pins und Sonderfälle."""

    day: int = Field(ge=0, le=6)
    meal: Meal
    eaters_home: int = Field(ge=0, le=2)
    packed_portions: int = Field(ge=0, le=2)
    packed_fresh: bool = False
    time_budget: TimeBudget = TimeBudget.NORMAL


class StandardSlotOut(Dto):
    day: int
    meal: Meal
    eaters_home: int
    packed_portions: int
    packed_fresh: bool
    time_budget: TimeBudget


class StandardWeekIn(Dto):
    slots: list[StandardSlotIn]


class WarningOut(Dto):
    level: WarningLevel
    code: str
    text: str
    day: int | None = None
    meal: Meal | None = None


class WeekOut(Dto):
    iso: str
    iso_year: int
    iso_week: int
    start_date: date
    version: int
    planner_seed: int
    primary_store_id: int | None
    secondary_store_id: int | None
    slots: list[SlotOut]
    warnings: list[WarningOut]
    planned_count: int
    needed_count: int


class GridIn(Dto):
    slots: list[SlotIn]
    version: int | None = None


class ProposeIn(Dto):
    keep_pins: bool = True
    only_empty: bool = False
    version: int | None = None


class AssignmentIn(Dto):
    kind: AssignmentKind
    dish_id: int | None = None
    factor: int = Field(default=1, ge=1, le=3)
    leftover_source_day: int | None = None
    leftover_source_meal: Meal | None = None
    portions_used: int | None = None
    version: int | None = None


class CandidateOut(Dto):
    label: str
    assignment: AssignmentOut
    score: ScoreOut
    warnings: list[str]
    eligible: bool


class PinIn(Dto):
    pinned: bool


class CancelIn(Dto):
    cancelled: bool


# ------------------------------------------------------------------------ Einkaufsliste


class ShoppingItemOut(Dto):
    article_id: int
    article_name: str
    quantity: Decimal | None
    unit: Unit
    spec_text: str
    source: ItemSource
    have_already: bool
    is_staple: bool
    from_dish_ids: list[int]
    bring_name: str | None
    offer_hint: str | None = None


class ShoppingListOut(Dto):
    iso: str
    status: ListStatus
    sent_at: datetime | None
    items: list[ShoppingItemOut]
    open_count: int
    text_export: str


class HaveAlreadyIn(Dto):
    article_id: int
    have_already: bool


class AddItemIn(Dto):
    article_id: int
    quantity: Decimal | None = None
    source: ItemSource = ItemSource.MANUAL


class PushOut(Dto):
    ok: bool
    adapter: str
    items_sent: int
    created: list[str]
    updated: list[str]
    removed: list[str]
    error: str | None = None
    text_fallback: str | None = None
    run_id: int


# ------------------------------------------------------------------- Angebote & Betrieb


class OfferOut(Dto):
    offer_id: int
    store_id: int
    store_name: str
    raw_name: str
    brand: str | None
    pack: str | None
    category: str | None
    price: Decimal | None
    old_price: Decimal | None
    base_price: str | None
    savings: Decimal | None
    valid_from: str | None
    valid_to: str | None
    article_id: int | None
    article_name: str | None
    match_confirmed: bool  # False = automatisch zugeordnet, noch nicht bestätigt
    # Zum Nachprüfen der Quelle
    description: str | None = None
    image_url: str | None = None
    source_url: str | None = None
    market_label: str | None = None
    market_url: str | None = None
    source_detail: str | None = None  # "offiziell" (Händlerseite) oder "Marktguru"
    fetched_at: datetime | None = None
    # Richtpreis des Artikels und das Urteil über dieses Angebot
    unit_price: Decimal | None = None  # Grundpreis in unit_price_unit
    unit_price_unit: str | None = None  # kg | l | Stück
    target_price: Decimal | None = None
    price_verdict: str | None = None  # None (kein Richtpreis) | ok | too_expensive | unknown
    # Mindestpackung des Artikels und das Urteil über die Packung dieses Angebots
    offer_amount: Decimal | None = None  # Packungsgröße in der Einheit des Artikels
    min_offer_amount: Decimal | None = None
    pack_verdict: str | None = None  # None (keine Grenze) | ok | too_small | unknown
    counts: bool  # zugeordnet, nicht über dem Richtpreis, Packung groß genug
    # Normalpreis des Artikels und der Abstand des Angebots dazu (negativ = günstiger)
    regular_unit_price: Decimal | None = None
    normal_diff: Decimal | None = None
    normal_diff_percent: int | None = None
    article_price_unit: str | None = None  # Einheit von Richt- und Normalpreis
    compared_price: Decimal | None = None  # das Angebot in dieser Einheit
    compared_via_piece: bool = False  # über das Stückgewicht umgerechnet (Schätzwert)
    piece_size: Decimal | None = None


class StoreIn(Dto):
    name: str = Field(min_length=1, max_length=80)
    chain: Chain
    postal_code: str | None = None
    market_id: str | None = None
    offers_enabled: bool = False
    is_primary: bool = False


class StorePatch(Dto):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    chain: Chain | None = None
    postal_code: str | None = None  # "" löscht
    market_id: str | None = None  # "" löscht
    offers_enabled: bool | None = None
    is_primary: bool | None = None


class StoreOut(Dto):
    id: int
    name: str
    chain: Chain
    postal_code: str | None
    market_id: str | None
    offers_enabled: bool
    is_primary: bool


class StoreStatusOut(Dto):
    store_id: int
    store_name: str
    last_fetched_at: datetime | None
    last_status: SyncStatus | None
    last_error: str | None
    market_label: str | None  # welchen Markt die Quelle tatsächlich genommen hat
    current_count: int


class OfferMatchIn(Dto):
    offer_name: str
    store_id: int | None = None
    article_id: int | None = None


class SyncRunOut(Dto):
    id: int
    kind: SyncKind
    status: SyncStatus
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    summary: dict | None


class HealthOut(Dto):
    db: str
    dishes: int
    articles: int
    catalog_cached: bool
    sync_adapter: str
    last_bring_push: datetime | None
    last_offer_fetch: datetime | None


class SettingsOut(Dto):
    planner_weights: dict[str, float]
    household: dict
    shopping: dict


class SettingsIn(Dto):
    planner_weights: dict[str, float] | None = None
    household: dict | None = None
    shopping: dict | None = None
