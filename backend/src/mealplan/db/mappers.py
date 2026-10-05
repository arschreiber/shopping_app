"""ORM <-> Domänen-Snapshots (ARCHITECTURE.md §2).

Hier - und nur hier - werden die *für eine Woche abgeleiteten* Fakten berechnet:
`weeks_since_cooked` (aus den Plänen und `cook_log`) und `offer_savings_eur` (Phase 2).
Damit bleibt die Domäne ohne Uhr und ohne Session.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.enums import (
    AssignmentKind,
    CategoryAxis,
    Effort,
    Meal,
    SlotSpecial,
    SuitableFor,
    TimeBudget,
    Unit,
)
from ..domain.model import (
    Assignment,
    Category,
    Contribution,
    DishSpec,
    IngredientSpec,
    Plan,
    PlanningSnapshot,
    ScoreBreakdown,
    SlotKey,
    SlotSpec,
)
from ..domain.nutrition import ArticleNutrition, article_nutrition
from ..domain.weights import PlannerWeights
from . import models as m


def week_start(iso_year: int, iso_week: int) -> date:
    return date.fromisocalendar(iso_year, iso_week, 1)


# ------------------------------------------------------------------------------- Gericht


def dish_to_spec(
    dish: m.Dish,
    *,
    weeks_since_cooked: int | None = None,
    offer_savings: Decimal = Decimal(0),
) -> DishSpec:
    return DishSpec(
        id=dish.id,
        name=dish.name,
        portions=dish.portions,
        packable=dish.packable,
        allow_double=dish.allow_double,
        allow_triple=dish.allow_triple,
        effort=Effort(dish.effort),
        suitable_for=SuitableFor(dish.suitable_for),
        rating=dish.rating,
        categories=frozenset(
            Category(CategoryAxis(c.axis), c.name) for c in dish.categories
        ),
        weeks_since_cooked=weeks_since_cooked,
        offer_savings_eur=offer_savings,
        article_ids=frozenset(i.article_id for i in dish.ingredients),
    )


def last_cooked(session: Session, *, through: date) -> dict[int, date]:
    """dish_id -> letzter Tag bis einschließlich `through`, an dem es gekocht wurde.

    Der Plan selbst ist der Verlauf: ein geplantes Gericht zählt ab seinem Tag als
    gekocht, außer es ist als "ausgefallen" markiert. Andersherum als general_plan.md §8
    Nr. 11 ("gekocht" bestätigen), weil ein vergessenes Abhaken die Abwechslung über die
    Wochen ganz abschalten würde - ein vergessenes "ausgefallen" kostet nur einen kleinen
    Abzug. Dazu kommen ausdrücklich bestätigte Einträge, auch ohne Plan.
    """
    latest: dict[int, date] = {}

    def record(dish_id: int, day: date) -> None:
        if day <= through and (dish_id not in latest or day > latest[dish_id]):
            latest[dish_id] = day

    cancelled = {
        (slot_id, dish_id)
        for slot_id, dish_id in session.execute(
            select(m.CookLog.slot_id, m.CookLog.dish_id).where(
                m.CookLog.confirmed.is_(False), m.CookLog.slot_id.is_not(None)
            )
        )
    }
    planned = session.execute(
        select(m.Week.iso_year, m.Week.iso_week, m.Slot.day, m.Slot.id, m.SlotAssignment.dish_id)
        .join(m.Slot, m.Slot.week_id == m.Week.id)
        .join(m.SlotAssignment, m.SlotAssignment.slot_id == m.Slot.id)
        .where(m.SlotAssignment.kind == AssignmentKind.DISH.value)
    )
    for iso_year, iso_week, day, slot_id, dish_id in planned:
        if (slot_id, dish_id) not in cancelled:
            record(dish_id, week_start(iso_year, iso_week) + timedelta(days=day))

    confirmed = session.execute(
        select(m.CookLog.dish_id, m.CookLog.cooked_at).where(m.CookLog.confirmed.is_(True))
    )
    for dish_id, cooked_at in confirmed:
        record(dish_id, cooked_at)
    return latest


def cooked_weeks_ago(
    session: Session, reference: date, *, through: date | None = None
) -> dict[int, int]:
    """dish_id -> volle Wochen zwischen dem letzten Kochen (bis `through`) und `reference`."""
    last = last_cooked(session, through=reference if through is None else through)
    return {dish_id: max(0, (reference - day).days // 7) for dish_id, day in last.items()}


def calendar_weeks_ago(day: date, today: date) -> int:
    """Kalenderwochen von `day` bis `today` - wie beim Planen gezählt.

    Mittwoch letzter Woche ist am Montag "vor 1 Woche", nicht "diese Woche", auch wenn es
    erst fünf Tage her ist.
    """
    this_monday = today - timedelta(days=today.weekday())
    that_monday = day - timedelta(days=day.weekday())
    return (this_monday - that_monday).days // 7


def is_cancelled(slot: m.Slot) -> bool:
    """Ist das Gericht dieses Slots als "ausgefallen" markiert?

    Die Markierung hängt am Gericht, nicht am Slot: wer danach umplant, hat ein neues
    Gericht, das wieder ganz normal zählt.
    """
    assignment = slot.assignment
    if assignment is None or assignment.kind != AssignmentKind.DISH.value:
        return False
    return any(
        not entry.confirmed and entry.dish_id == assignment.dish_id
        for entry in slot.cook_entries
    )


def ingredients_by_dish(session: Session) -> dict[int, list[IngredientSpec]]:
    rows = session.execute(
        select(
            m.Ingredient.dish_id,
            m.Ingredient.article_id,
            m.Ingredient.quantity,
            m.Ingredient.unit,
        ).order_by(m.Ingredient.dish_id, m.Ingredient.sort_order)
    ).all()
    out: dict[int, list[IngredientSpec]] = {}
    for dish_id, article_id, quantity, unit in rows:
        out.setdefault(dish_id, []).append(
            IngredientSpec(article_id=article_id, quantity=quantity, unit=Unit(unit))
        )
    return out


def article_nutrition_index(session: Session) -> dict[int, ArticleNutrition]:
    """`{article_id: ArticleNutrition}` - Artikel ohne jede Angabe fehlen hier."""
    rows = session.execute(
        select(
            m.Article.id,
            m.Article.unit,
            m.Article.kcal,
            m.Article.carbs_g,
            m.Article.fat_g,
            m.Article.protein_g,
        )
    ).all()
    out: dict[int, ArticleNutrition] = {}
    for article_id, unit, kcal, carbs, fat, protein in rows:
        facts = article_nutrition(
            article_id, Unit(unit), kcal=kcal, carbs_g=carbs, fat_g=fat, protein_g=protein
        )
        if facts is not None:
            out[article_id] = facts
    return out


def article_units(session: Session) -> dict[int, Unit]:
    rows = session.execute(select(m.Article.id, m.Article.unit)).all()
    return {article_id: Unit(unit) for article_id, unit in rows}


# ---------------------------------------------------------------------------------- Slot


def slot_to_spec(slot: m.Slot) -> SlotSpec:
    return SlotSpec(
        key=SlotKey.of(slot.day, Meal(slot.meal)),
        eaters_home=slot.eaters_home,
        packed_portions=slot.packed_portions,
        packed_fresh=slot.packed_fresh,
        time_budget=TimeBudget(slot.time_budget),
        special=SlotSpecial(slot.special),
        pinned=slot.pinned,
    )


def plan_from_week(week: m.Week) -> Plan:
    by_id = {slot.id: SlotKey.of(slot.day, Meal(slot.meal)) for slot in week.slots}
    plan = Plan()
    for slot in week.slots:
        assignment = slot.assignment
        if assignment is None:
            continue
        source = (
            by_id.get(assignment.leftover_source_slot_id)
            if assignment.leftover_source_slot_id
            else None
        )
        plan = plan.with_(
            by_id[slot.id],
            Assignment(
                kind=AssignmentKind(assignment.kind),
                dish_id=assignment.dish_id,
                factor=assignment.factor,
                leftover_source=source,
                portions_used=assignment.portions_used,
                score=breakdown_from_json(assignment.score_snapshot),
            ),
        )
    return plan


def breakdown_from_json(data: dict | None) -> ScoreBreakdown | None:
    if not data:
        return None
    return ScoreBreakdown(
        total=float(data.get("total", 0.0)),
        contributions=tuple(
            Contribution(c["rule"], float(c["delta"]), c["text"])
            for c in data.get("contributions", [])
        ),
    )


def breakdown_to_json(breakdown: ScoreBreakdown | None) -> dict | None:
    if breakdown is None:
        return None
    return {
        "total": breakdown.total,
        "contributions": [
            {"rule": c.rule, "delta": c.delta, "text": c.text} for c in breakdown.contributions
        ],
    }


# ------------------------------------------------------------------------------ Snapshot


def build_snapshot(
    session: Session,
    week: m.Week,
    *,
    weights: PlannerWeights,
    leftover_shelf_life_days: int = 2,
    offer_savings: dict[int, Decimal] | None = None,
) -> PlanningSnapshot:
    start = week_start(week.iso_year, week.iso_week)
    # Alles, was *vor* dieser Woche geplant ist - auch wenn es noch bevorsteht: wer im
    # Voraus plant, will nicht wiederholen, was die Woche davor schon dran ist. Die Woche
    # selbst ist der Plan, nicht sein Verlauf; sonst bekäme jedes ihrer Gerichte einen
    # Abzug für sich selbst.
    ages = cooked_weeks_ago(
        session, start + timedelta(days=6), through=start - timedelta(days=1)
    )
    dishes = session.scalars(select(m.Dish).where(m.Dish.archived.is_(False))).all()
    savings = offer_savings or {}
    return PlanningSnapshot(
        slots=tuple(slot_to_spec(slot) for slot in week.slots),
        dishes=tuple(
            dish_to_spec(
                dish,
                weeks_since_cooked=ages.get(dish.id),
                offer_savings=savings.get(dish.id, Decimal(0)),
            )
            for dish in dishes
        ),
        weights=weights,
        week_start=start,
        leftover_shelf_life_days=leftover_shelf_life_days,
    )


def slot_ids_by_key(week: m.Week) -> dict[SlotKey, int]:
    return {SlotKey.of(slot.day, Meal(slot.meal)): slot.id for slot in week.slots}
