/**
 * Gerichts-Formular: links, was man tippt (Name, Zutaten), rechts, was daraus folgt
 * (Steckbrief mit Beilage, Protein, Portionen und Eigenschaften).
 *
 * Beilage und Protein werden aus den Zutaten erkannt (`RoleField`, `domain/dish_roles.py`)
 * und nur noch überstimmt, nicht mehr gepflegt. Die Achse "Küche" hat kein Gericht
 * benutzt und ist aus dem Formular verschwunden - vorhandene Werte bleiben erhalten.
 */
import { useEffect, useState, type ReactNode } from "react";
import type { Dish, DishIn, Effort, SuitableFor } from "../../api/client";
import { Segmented, Toggle } from "../../components/Primitives";
import { EFFORT_HINT, EFFORT_LABEL, formatNumber, SUITABLE_LABEL } from "../../lib/format";
import { IngredientRows, type IngredientRow, type RowTag } from "./IngredientRows";
import { NameField } from "./NameField";
import { NutritionPanel, useNutritionPreview } from "./NutritionPanel";
import {
  autoChoice,
  detectionFor,
  ROLE_AXES,
  ROLE_LABEL,
  RoleField,
  sameName,
  useDishRoles,
  type RoleAxis,
  type RoleMode,
} from "./RoleField";

export type CategoryChoice = { axis: "SIDE" | "PROTEIN" | "CUISINE"; name: string };

export type DishDraft = {
  name: string;
  portions: Portions;
  packable: boolean;
  reheatable: boolean;
  allow_double: boolean;
  allow_triple: boolean;
  effort: Effort;
  suitable_for: SuitableFor;
  rating: number | null;
  prep_text: string;
  note: string;
  ingredients: IngredientRow[];
  categories: CategoryChoice[];
  /** Folgt die Achse den Zutaten (auto) oder ist sie von Hand gesetzt? */
  roleModes: Record<RoleAxis, RoleMode>;
  /** Bestätigte Vorschläge: Achse -> Artikel, der die Rolle bekommt. */
  accepted: Partial<Record<RoleAxis, number>>;
};

type Portions = 1 | 2 | 3;

const PORTION_OPTIONS = [
  { value: "1", label: "1", title: "1 Portion – doppelt oder dreifach kochbar" },
  { value: "2", label: "2", title: "2 Portionen – verdoppelbar auf 4" },
  { value: "3", label: "3", title: "3 Portionen" },
];

function toPortions(value: number | string): Portions {
  const n = Number(value);
  return n === 1 || n === 2 ? n : 3;
}

/** "als 1, 2 oder 3 Portionen" - so oft lässt sich das Gericht auf einmal kochen. */
function sizesHint(draft: DishDraft): string | null {
  if (draft.portions === 2) return draft.allow_double ? "verdoppelbar auf 4" : null;
  if (draft.portions === 3) return null;
  const sizes = [1, ...(draft.allow_double ? [2] : []), ...(draft.allow_triple ? [3] : [])];
  if (sizes.length === 1) return null;
  const last = sizes.pop();
  return `als ${sizes.join(", ")} oder ${last} Portionen`;
}

export function emptyDraft(): DishDraft {
  return {
    name: "",
    portions: 3,
    packable: true,
    reheatable: true,
    allow_double: true,
    allow_triple: false,
    effort: "NORMAL",
    suitable_for: "BOTH",
    rating: null,
    prep_text: "",
    note: "",
    ingredients: [],
    categories: [],
    roleModes: { SIDE: "auto", PROTEIN: "auto" },
    accepted: {},
  };
}

/**
 * Ein gespeichertes Gericht als Entwurf. Ob Beilage und Protein "auto" oder "manuell"
 * sind, entscheidet die erste Erkennung (`pending`): stimmt sie mit dem Gespeicherten
 * überein, folgt die Achse ab da den Zutaten, sonst bleibt der gespeicherte Wert stehen.
 */
export function draftFromDish(dish: Dish): DishDraft {
  return {
    name: dish.name,
    portions: toPortions(dish.portions),
    packable: dish.packable,
    reheatable: dish.reheatable,
    allow_double: dish.allow_double,
    allow_triple: dish.allow_triple,
    effort: dish.effort,
    suitable_for: dish.suitable_for,
    rating: dish.rating,
    prep_text: dish.prep_text ?? "",
    note: dish.note ?? "",
    ingredients: dish.ingredients.map((ingredient) => ({
      article_id: ingredient.article_id,
      article_name: ingredient.article_name,
      quantity: ingredient.quantity,
      unit: ingredient.unit,
    })),
    categories: dish.categories.map((category) => ({
      axis: category.axis,
      name: category.name,
    })),
    roleModes: { SIDE: "pending", PROTEIN: "pending" },
    accepted: {},
  };
}

export function toDishIn(draft: DishDraft): DishIn {
  return {
    name: draft.name,
    portions: draft.portions,
    packable: draft.packable,
    reheatable: draft.reheatable,
    allow_double: draft.allow_double,
    allow_triple: draft.allow_triple,
    effort: draft.effort,
    suitable_for: draft.suitable_for,
    rating: draft.rating,
    prep_text: draft.prep_text || null,
    note: draft.note || null,
    ingredients: draft.ingredients.map((row) => ({
      article_id: row.article_id,
      quantity: row.quantity,
      unit: row.unit,
    })),
    categories: draft.categories,
  };
}

function categoryOf(draft: DishDraft, axis: RoleAxis): string | null {
  return draft.categories.find((category) => category.axis === axis)?.name ?? null;
}

function withCategory(
  categories: CategoryChoice[],
  axis: RoleAxis,
  name: string | null,
): CategoryChoice[] {
  const rest = categories.filter((category) => category.axis !== axis);
  return name ? [...rest, { axis, name }] : rest;
}

export function DishForm({
  draft,
  onChange,
  onSubmit,
  onCancel,
  saving,
  isNew,
  extraAction,
}: {
  draft: DishDraft;
  onChange: (draft: DishDraft) => void;
  /** `next`: gespeichert und gleich das nächste anlegen. */
  onSubmit: (next: boolean) => void;
  onCancel?: () => void;
  saving: boolean;
  isNew: boolean;
  extraAction?: ReactNode;
}) {
  const [nameRef, setNameRef] = useState<HTMLInputElement | null>(null);
  const [moreOpen, setMoreOpen] = useState(() => !isNew && Boolean(draft.prep_text));
  const [template, setTemplate] = useState<{ name: string; previous: DishDraft } | null>(
    null,
  );
  useEffect(() => nameRef?.focus(), [nameRef]);

  const nutrition = useNutritionPreview(draft.ingredients, draft.portions);
  const { roles, fresh } = useDishRoles(draft.ingredients);

  function patch(changes: Partial<DishDraft>) {
    onChange({ ...draft, ...changes });
  }

  // Auto-Achsen folgen der Erkennung; `pending` (gerade geladen) wird hier entschieden.
  useEffect(() => {
    if (!roles || !fresh) return;
    let categories = draft.categories;
    let modes = draft.roleModes;
    let changed = false;
    for (const axis of ROLE_AXES) {
      const current = categoryOf(draft, axis);
      const auto = autoChoice(detectionFor(roles, axis), draft.accepted[axis])?.name ?? null;
      if (modes[axis] === "pending") {
        modes = { ...modes, [axis]: sameName(current, auto) ? "auto" : "manual" };
        changed = true;
      } else if (modes[axis] === "auto" && !sameName(current, auto)) {
        categories = withCategory(categories, axis, auto);
        changed = true;
      }
    }
    if (changed) onChange({ ...draft, categories, roleModes: modes });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles, fresh, draft.accepted, draft.roleModes]);

  function choose(axis: RoleAxis, name: string | null) {
    const detection = detectionFor(roles, axis);
    const suggestion = detection?.suggestion;
    // Den Vorschlag aus der Liste zu wählen heißt, ihn zu bestätigen.
    const accepted =
      suggestion && name && sameName(name, suggestion.category)
        ? { ...draft.accepted, [axis]: suggestion.article_id }
        : draft.accepted;
    const auto = autoChoice(detection, accepted[axis])?.name ?? null;
    onChange({
      ...draft,
      accepted,
      categories: withCategory(draft.categories, axis, name),
      roleModes: { ...draft.roleModes, [axis]: sameName(name, auto) ? "auto" : "manual" },
    });
  }

  function accept(axis: RoleAxis, articleId: number) {
    const suggestion = detectionFor(roles, axis)?.suggestion;
    if (!suggestion) return;
    onChange({
      ...draft,
      accepted: { ...draft.accepted, [axis]: articleId },
      categories: withCategory(draft.categories, axis, suggestion.category),
      roleModes: { ...draft.roleModes, [axis]: "auto" },
    });
  }

  function reset(axis: RoleAxis) {
    const auto = autoChoice(detectionFor(roles, axis), draft.accepted[axis])?.name ?? null;
    onChange({
      ...draft,
      categories: withCategory(draft.categories, axis, auto),
      roleModes: { ...draft.roleModes, [axis]: "auto" },
    });
  }

  function applyTemplate(dish: Dish) {
    setTemplate({ name: dish.name, previous: draft });
    onChange({ ...draftFromDish(dish), name: draft.name, rating: null, note: "" });
  }

  // Welche Zutat liefert Beilage und Protein? Als Etikett an der Zeile.
  const tags: Record<number, RowTag> = {};
  for (const axis of ROLE_AXES) {
    const value = categoryOf(draft, axis);
    const detection = detectionFor(roles, axis);
    const auto = autoChoice(detection, draft.accepted[axis]);
    if (auto && sameName(auto.name, value)) {
      tags[auto.from.article_id] = { label: ROLE_LABEL[axis] };
    } else if (draft.roleModes[axis] === "auto" && !auto && detection?.suggestion) {
      tags[detection.suggestion.article_id] = {
        label: `${ROLE_LABEL[axis]}?`,
        tentative: true,
      };
    }
  }

  const canSubmit = draft.name.trim().length > 0 && !saving;
  const perPortion = nutrition?.has_any ? nutrition.per_portion : null;
  const summary = [
    categoryOf(draft, "SIDE"),
    categoryOf(draft, "PROTEIN"),
    perPortion && `${formatNumber(perPortion.kcal)} kcal je Portion`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) onSubmit(false);
      }}
      className="flex flex-col gap-4"
    >
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <div className="card flex min-w-0 flex-col gap-5 p-4 sm:p-5">
          <div>
            <NameField
              value={draft.name}
              onChange={(name) => patch({ name })}
              inputRef={setNameRef}
              templates={isNew && !template}
              onPickTemplate={applyTemplate}
            />
            {template && (
              <p className="mt-1.5 text-xs text-ink-muted">
                Zutaten und Eigenschaften von „{template.name}“ übernommen ·{" "}
                <button
                  type="button"
                  onClick={() => {
                    onChange({ ...template.previous, name: draft.name });
                    setTemplate(null);
                  }}
                  className="underline underline-offset-2 hover:text-ink"
                >
                  rückgängig
                </button>
              </p>
            )}
          </div>

          <div>
            <div className="mb-2 flex items-baseline gap-2">
              <h3 className="label">
                Zutaten{draft.ingredients.length > 0 && ` · ${draft.ingredients.length}`}
              </h3>
              <span className="text-2xs text-ink-faint">
                Beilage und Protein ergeben sich daraus
              </span>
            </div>
            <IngredientRows
              rows={draft.ingredients}
              onChange={(ingredients) => patch({ ingredients })}
              tags={tags}
            />
          </div>

          <div className="rule pt-3">
            <button
              type="button"
              onClick={() => setMoreOpen(!moreOpen)}
              aria-expanded={moreOpen}
              className="flex items-center gap-2 text-xs text-ink-muted hover:text-ink"
            >
              <span className="text-ink-faint">{moreOpen ? "▾" : "▸"}</span>
              Mehr: Zubereitung{!isNew && ", Bewertung"}
              {!moreOpen && draft.prep_text && (
                <span className="text-ink-faint">· Zubereitung erfasst</span>
              )}
            </button>
            {moreOpen && (
              <div className="mt-3 flex flex-col gap-4">
                <div>
                  <label className="label mb-1 block" htmlFor="dish-prep">
                    Zubereitung
                  </label>
                  <textarea
                    id="dish-prep"
                    value={draft.prep_text}
                    rows={3}
                    onChange={(event) => patch({ prep_text: event.target.value })}
                    placeholder="Reis kochen, Gemüse anbraten, Hirtenkäse darüber …"
                    className="field"
                  />
                </div>
                {/* Bewertet wird, was schon gekocht wurde - beim Anlegen wäre sie geraten. */}
                {!isNew && (
                  <div>
                    <span className="label mb-1 block">Bewertung</span>
                    <div className="flex items-center gap-0.5">
                      {[1, 2, 3, 4, 5].map((value) => (
                        <button
                          key={value}
                          type="button"
                          aria-label={`${value} Sterne`}
                          onClick={() =>
                            patch({ rating: draft.rating === value ? null : value })
                          }
                          className={[
                            "px-0.5 text-lg leading-none transition-colors duration-fast",
                            (draft.rating ?? 0) >= value
                              ? "text-accent"
                              : "text-line-strong hover:text-ink-faint",
                          ].join(" ")}
                        >
                          ★
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <aside className="card flex flex-col gap-3 p-4 lg:sticky lg:top-16">
          <span className="label">Steckbrief</span>
          {ROLE_AXES.map((axis) => (
            <RoleField
              key={axis}
              axis={axis}
              detection={detectionFor(roles, axis)}
              value={categoryOf(draft, axis)}
              mode={draft.roleModes[axis]}
              accepted={draft.accepted[axis]}
              onChoose={(name) => choose(axis, name)}
              onAccept={(articleId) => accept(axis, articleId)}
              onReset={() => reset(axis)}
            />
          ))}

          <div className="rule" />

          <div className="grid grid-cols-[5rem_minmax(0,1fr)] items-center gap-x-3 gap-y-2.5">
            <span className="text-xs text-ink-muted">Portionen</span>
            <div>
              <Segmented
                label="Portionen"
                size="sm"
                value={String(draft.portions)}
                options={PORTION_OPTIONS}
                onChange={(value) => patch({ portions: toPortions(value) })}
              />
            </div>
            {(perPortion || sizesHint(draft)) && (
              <p className="col-start-2 -mt-1.5 text-2xs text-ink-faint">
                {[
                  perPortion &&
                    `${formatNumber(perPortion.kcal)} kcal · ${formatNumber(perPortion.protein_g)} g Protein je Portion`,
                  sizesHint(draft),
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}

            <span className="text-xs text-ink-muted">Aufwand</span>
            <div>
              <Segmented
                label="Aufwand"
                size="sm"
                value={draft.effort}
                options={(["NORMAL", "QUICK"] as Effort[]).map((effort) => ({
                  value: effort,
                  label: EFFORT_LABEL[effort],
                  title: EFFORT_HINT[effort],
                }))}
                onChange={(value) => patch({ effort: value })}
              />
            </div>

            <span className="text-xs text-ink-muted">Mahlzeit</span>
            <div>
              <Segmented
                label="Geeignet für"
                size="sm"
                value={draft.suitable_for}
                options={(["BOTH", "LUNCH", "DINNER"] as SuitableFor[]).map((value) => ({
                  value,
                  label:
                    value === "BOTH" ? "beides" : SUITABLE_LABEL[value].replace("nur ", ""),
                }))}
                onChange={(value) => patch({ suitable_for: value })}
              />
            </div>
          </div>

          <div className="rule" />

          <div className="flex flex-col gap-2">
            <Toggle
              checked={draft.packable}
              onChange={(packable) => patch({ packable })}
              label="mitnehmbar"
            />
            {/* Aus: Reste taugen nichts - der Planer kocht es nur so, dass es genau aufgeht. */}
            <Toggle
              checked={draft.reheatable}
              onChange={(reheatable) => patch({ reheatable })}
              label="aufwärmbar"
            />
            {/* 3er-Gerichte werden nie vervielfacht; bei 1 Portion sind doppelt *und*
                dreifach wählbar. Die gespeicherten Werte bleiben beim Wechsel erhalten. */}
            {draft.portions !== 3 && (
              <Toggle
                checked={draft.allow_double}
                onChange={(allow_double) => patch({ allow_double })}
                label="doppelt möglich"
              />
            )}
            {draft.portions === 1 && (
              <Toggle
                checked={draft.allow_triple}
                onChange={(allow_triple) => patch({ allow_triple })}
                label="dreifach möglich"
              />
            )}
          </div>
        </aside>
      </div>

      {/* Unter beiden Spalten, volle Breite: die Vitamine brauchen drei Spalten Platz.
          Rechnet bei jeder Mengenänderung neu (entprellt) - je Portion. */}
      <section className="card flex flex-col gap-2 p-4 sm:p-5" aria-label="Nährwerte">
        <div className="flex items-baseline gap-2">
          <h3 className="label">Nährwerte</h3>
          <span className="text-2xs text-ink-faint">
            je Portion bei {draft.portions} {draft.portions === 1 ? "Portion" : "Portionen"} ·
            Balken = Anteil am Tageswert
          </span>
        </div>
        {nutrition?.has_any ? (
          <NutritionPanel rows={draft.ingredients} data={nutrition} microsOpen />
        ) : (
          <p className="text-sm text-ink-muted">
            {draft.ingredients.length === 0
              ? "Erscheinen hier, sobald Zutaten eingetragen sind."
              : "Noch keine Werte – fehlen Mengen oder Nährwerte an den Zutaten?"}
          </p>
        )}
      </section>

      <div
        className="sticky bottom-14 z-10 -mx-4 flex items-center gap-2 border-t border-line
                   bg-surface/95 px-4 py-3 backdrop-blur sm:bottom-0 sm:-mx-6 sm:px-6"
      >
        <button type="submit" disabled={!canSubmit} className="btn-primary">
          {saving ? (
            "speichert …"
          ) : isNew ? (
            "Speichern"
          ) : (
            <>
              <span className="sm:hidden">Speichern</span>
              <span className="hidden sm:inline">Änderungen speichern</span>
            </>
          )}
        </button>
        {isNew && (
          <button
            type="button"
            disabled={!canSubmit}
            onClick={() => onSubmit(true)}
            className="btn-secondary hidden sm:inline-flex"
          >
            Speichern &amp; nächstes
          </button>
        )}
        {onCancel && (
          <button type="button" onClick={onCancel} className="btn-ghost">
            Abbrechen
          </button>
        )}
        {summary && (
          <span className="ml-auto hidden min-w-0 truncate text-xs text-ink-muted sm:block">
            {summary}
          </span>
        )}
        {extraAction && (
          <div className={summary ? "ml-auto sm:ml-0" : "ml-auto"}>{extraAction}</div>
        )}
      </div>
    </form>
  );
}
