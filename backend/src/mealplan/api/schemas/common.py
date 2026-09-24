"""Pydantic-DTOs, getrennt von ORM und Domäne (ARCHITECTURE.md §6)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from ...domain.enums import (
    AssignmentKind,
    CategoryAxis,
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
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal


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
    # Nährwerte je 100 g / 100 ml / Stück - die Bezugsgröße steckt in `unit`.
    kcal: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    nutrition_basis: str = ""

    @classmethod
    def of(cls, article) -> ArticleOut:
        from ...domain.nutrition import BASIS_LABEL
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
            kcal=trim(article.kcal),
            protein_g=trim(article.protein_g),
            carbs_g=trim(article.carbs_g),
            fat_g=trim(article.fat_g),
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
    kcal: Decimal | None = Field(default=None, ge=0)
    protein_g: Decimal | None = Field(default=None, ge=0)
    carbs_g: Decimal | None = Field(default=None, ge=0)
    fat_g: Decimal | None = Field(default=None, ge=0)


class ArticlePatch(Dto):
    canonical_name: str | None = None
    unit: Unit | None = None
    bring_catalog_name: str | None = None
    bring_category: str | None = None
    is_staple: bool | None = None
    is_watchlist: bool | None = None
    aliases: list[str] | None = None
    kcal: Decimal | None = Field(default=None, ge=0)
    protein_g: Decimal | None = Field(default=None, ge=0)
    carbs_g: Decimal | None = Field(default=None, ge=0)
    fat_g: Decimal | None = Field(default=None, ge=0)


class ArticleSuggestion(Dto):
    article: ArticleOut
    score: float
    # "COMPOUND" = teilt einen Wortbestandteil ("Basmatireis" / "Reis"),
    # "FUZZY" = nur ähnlich geschrieben.
    kind: str = "FUZZY"
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
    effort: Effort
    suitable_for: SuitableFor
    rating: int | None
    prep_text: str | None
    note: str | None
    archived: bool
    can_double: bool
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
    portions: int = Field(ge=2, le=3)
    packable: bool = True
    effort: Effort = Effort.NORMAL
    suitable_for: SuitableFor = SuitableFor.BOTH
    rating: int | None = Field(default=None, ge=1, le=5)
    prep_text: str | None = None
    note: str | None = None
    ingredients: list[IngredientIn] = Field(default_factory=list)
    categories: list[CategoryIn] = Field(default_factory=list)


class DishPatch(Dto):
    name: str | None = None
    portions: int | None = Field(default=None, ge=2, le=3)
    packable: bool | None = None
    effort: Effort | None = None
    suitable_for: SuitableFor | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    prep_text: str | None = None
    note: str | None = None
    archived: bool | None = None
    ingredients: list[IngredientIn] | None = None
    categories: list[CategoryIn] | None = None


class NutritionPreviewIn(Dto):
    portions: int = Field(ge=2, le=3)
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
    doubled: bool = False
    portions: int | None = None
    leftover_source_day: int | None = None
    leftover_source_meal: Meal | None = None
    leftover_source_label: str | None = None
    portions_used: int | None = None
    score: ScoreOut | None = None


class SlotOut(Dto):
    day: int
    meal: Meal
    date: date
    eaters_home: int
    packed_portions: int
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
    time_budget: TimeBudget
    special: SlotSpecial = SlotSpecial.NONE
    pinned: bool = False


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
    doubled: bool = False
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
    store_name: str
    raw_name: str
    brand: str | None
    price: Decimal | None
    old_price: Decimal | None
    savings: Decimal | None
    valid_to: str | None
    article_id: int | None
    article_name: str | None


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
