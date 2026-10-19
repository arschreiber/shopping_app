/** Gerichts-Formular: minimale Pflichtfelder (general_plan.md §8 Nr. 5). */
import { useEffect, useState, type ReactNode } from "react";
import type { Dish, Effort, SuitableFor } from "../../api/client";
import { Segmented, Toggle } from "../../components/Primitives";
import { EFFORT_HINT, EFFORT_LABEL, SUITABLE_LABEL } from "../../lib/format";
import { CategoryPicker, type CategoryChoice } from "./CategoryPicker";
import { IngredientRows, type IngredientRow } from "./IngredientRows";
import { NutritionPanel } from "./NutritionPanel";

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
  };
}

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
  };
}

export function DishForm({
  draft,
  onChange,
  onSubmit,
  onCancel,
  saving,
  submitLabel,
  extraAction,
}: {
  draft: DishDraft;
  onChange: (draft: DishDraft) => void;
  onSubmit: () => void;
  onCancel?: () => void;
  saving: boolean;
  submitLabel: string;
  extraAction?: ReactNode;
}) {
  const [nameRef, setNameRef] = useState<HTMLInputElement | null>(null);
  useEffect(() => nameRef?.focus(), [nameRef]);

  function patch(changes: Partial<DishDraft>) {
    onChange({ ...draft, ...changes });
  }

  const canSubmit = draft.name.trim().length > 0 && !saving;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSubmit) onSubmit();
      }}
      className="flex flex-col gap-5"
    >
      <div>
        <label className="label mb-1 block" htmlFor="dish-name">
          Name
        </label>
        <input
          id="dish-name"
          ref={setNameRef}
          value={draft.name}
          onChange={(event) => patch({ name: event.target.value })}
          placeholder="Hirtenkäse-Reispfanne"
          className="field text-base"
          required
        />
      </div>

      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div>
          <span className="label mb-1 block">Portionen</span>
          <Segmented
            label="Portionen"
            value={String(draft.portions)}
            options={PORTION_OPTIONS}
            onChange={(value) => patch({ portions: toPortions(value) })}
          />
          {sizesHint(draft) && (
            <p className="mt-1 text-2xs text-ink-faint">{sizesHint(draft)}</p>
          )}
        </div>

        <div>
          <span className="label mb-1 block">Aufwand</span>
          <Segmented
            label="Aufwand"
            value={draft.effort}
            options={(["NORMAL", "QUICK"] as Effort[]).map((effort) => ({
              value: effort,
              label: EFFORT_LABEL[effort],
              title: EFFORT_HINT[effort],
            }))}
            onChange={(value) => patch({ effort: value })}
          />
        </div>

        <div>
          <span className="label mb-1 block">Geeignet für</span>
          <Segmented
            label="Geeignet für"
            value={draft.suitable_for}
            options={(["BOTH", "LUNCH", "DINNER"] as SuitableFor[]).map((value) => ({
              value,
              label: value === "BOTH" ? "beides" : SUITABLE_LABEL[value].replace("nur ", ""),
            }))}
            onChange={(value) => patch({ suitable_for: value })}
          />
        </div>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pb-1">
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

        <div className="pb-0.5">
          <span className="label mb-1 block">Bewertung</span>
          <div className="flex items-center gap-0.5">
            {[1, 2, 3, 4, 5].map((value) => (
              <button
                key={value}
                type="button"
                aria-label={`${value} Sterne`}
                onClick={() => patch({ rating: draft.rating === value ? null : value })}
                className={[
                  "px-0.5 text-lg leading-none transition-colors duration-fast",
                  (draft.rating ?? 0) >= value ? "text-accent" : "text-line-strong hover:text-ink-faint",
                ].join(" ")}
              >
                ★
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="rule pt-4">
        <CategoryPicker
          selected={draft.categories}
          onChange={(categories) => patch({ categories })}
        />
      </div>

      <div className="rule pt-4">
        <div className="mb-2 flex items-baseline gap-2">
          <h3 className="label">Zutaten</h3>
          <span className="text-2xs text-ink-faint">
            jede Zutat ist ein Artikel – vorhandene werden vorgeschlagen
          </span>
        </div>
        <IngredientRows
          rows={draft.ingredients}
          onChange={(ingredients) => patch({ ingredients })}
        />
        {draft.ingredients.length > 0 && (
          <div className="mt-3">
            <NutritionPanel rows={draft.ingredients} portions={draft.portions} />
          </div>
        )}
      </div>

      <div className="rule pt-4">
        <label className="label mb-1 block" htmlFor="dish-prep">
          Zubereitung <span className="font-normal normal-case tracking-normal">(optional)</span>
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

      <div className="sticky bottom-0 -mx-4 flex items-center gap-2 border-t border-line
                      bg-surface/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <button type="submit" disabled={!canSubmit} className="btn-primary">
          {saving ? "speichert …" : submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="btn-secondary">
            Abbrechen
          </button>
        )}
        <div className="ml-auto">{extraAction}</div>
      </div>
    </form>
  );
}
