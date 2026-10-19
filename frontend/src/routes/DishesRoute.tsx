/**
 * Gerichte-Liste mit Schnellerfassung. Phase 0 heißt: 30-50 Gerichte an einem Abend
 * eintippen (general_plan.md §5). Darum bleibt das Formular oben offen und der Fokus
 * springt nach dem Speichern zurück in den Namen.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import type { DishSummary } from "../api/client";
import { useDishes, useSaveDish } from "../api/hooks";
import { IconBook, IconPlus } from "../components/Icons";
import { EmptyState, Spinner } from "../components/Primitives";
import { errorText, useToast } from "../components/Toast";
import {
  DishForm,
  emptyDraft,
  type DishDraft,
} from "../features/dishes/DishForm";
import { NutritionCell } from "../features/dishes/NutritionPanel";
import { AXIS_LABEL, EFFORT_LABEL, FACTOR_WORD, stars } from "../lib/format";

export function DishesRoute() {
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<DishDraft>(emptyDraft);
  // Zählt jedes gespeicherte Gericht hoch und montiert damit das Formular neu. Ein
  // zurückgesetzter Entwurf allein reicht nicht: Textblock, Kategorie-Eingaben und der
  // Fokus liegen im Formular selbst und überlebten das Speichern sonst.
  const [formKey, setFormKey] = useState(0);
  const dishes = useDishes(query || undefined);
  const save = useSaveDish();
  const toast = useToast();

  function submit() {
    save.mutate(
      {
        body: {
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
        },
      },
      {
        onError: (error) => toast.show(errorText(error), "error"),
        onSuccess: (dish) => {
          toast.show(`„${dish.name}“ gespeichert`, "ok");
          // "Speichern & nächstes" heißt: leeres Formular. Vorher blieben Aufwand,
          // Portionen und die Schalter stehen - gedacht als Tipphilfe für ähnliche
          // Gerichte, gelesen aber als "das Formular hat mich nicht verstanden".
          setDraft(emptyDraft());
          setFormKey((current) => current + 1);
        },
      },
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-xl font-semibold">Gerichte</h1>
          <p className="text-sm text-ink-muted">
            {dishes.data ? `${dishes.data.length} erfasst` : "…"}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="suchen …"
            className="field w-40 sm:w-56"
            aria-label="Gerichte suchen"
          />
          <button
            type="button"
            onClick={() => setAdding(!adding)}
            className={adding ? "btn-secondary btn-sm" : "btn-primary btn-sm"}
          >
            <IconPlus className="h-3.5 w-3.5" />
            {adding ? "schließen" : "Gericht"}
          </button>
        </div>
      </header>

      {adding && (
        <div className="card p-4 sm:p-6">
          <DishForm
            key={formKey}
            draft={draft}
            onChange={setDraft}
            onSubmit={submit}
            onCancel={() => setAdding(false)}
            saving={save.isPending}
            submitLabel="Speichern & nächstes"
          />
        </div>
      )}

      {dishes.isLoading && <Spinner label="Gerichte werden geladen …" />}

      {dishes.data?.length === 0 && !adding && (
        <EmptyState
          title="Noch keine Gerichte"
          hint="Die Planung braucht Vorrat: 30-50 Gerichte sind der Punkt, an dem die
                Vorschläge wirklich Auswahl haben. Zutaten kannst du als Textblock
                einfügen – eine Zeile pro Zutat."
          action={
            <button type="button" onClick={() => setAdding(true)} className="btn-primary btn-sm">
              <IconPlus className="h-3.5 w-3.5" />
              Erstes Gericht
            </button>
          }
        />
      )}

      {dishes.data && dishes.data.length > 0 && <DishTable dishes={dishes.data} />}
    </div>
  );
}

function DishTable({ dishes }: { dishes: DishSummary[] }) {
  return (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line bg-sunken/60 text-left">
            <th className="px-3 py-2 font-medium text-ink-muted">Gericht</th>
            <th className="hidden px-3 py-2 font-medium text-ink-muted sm:table-cell">
              Kategorien
            </th>
            <th className="px-3 py-2 text-right font-medium text-ink-muted">P</th>
            <th className="hidden px-3 py-2 font-medium text-ink-muted sm:table-cell">
              je Portion
            </th>
            <th className="hidden px-3 py-2 font-medium text-ink-muted md:table-cell">
              Aufwand
            </th>
            <th className="hidden px-3 py-2 font-medium text-ink-muted md:table-cell">
              zuletzt
            </th>
            <th className="px-3 py-2" />
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {dishes.map((dish) => (
            <tr key={dish.id} className="hover:bg-sunken/40">
              <td className="px-3 py-2">
                <Link
                  to={`/dishes/${dish.id}`}
                  className="font-medium hover:text-accent hover:underline"
                >
                  {dish.name}
                </Link>
                <div className="mt-0.5 flex items-center gap-1.5">
                  {!dish.packable && (
                    <span className="text-2xs text-ink-faint">nicht mitnehmbar</span>
                  )}
                  {!dish.reheatable && (
                    <span className="text-2xs text-ink-faint">nicht aufwärmbar</span>
                  )}
                  {dish.portions === 2 && !dish.allow_double && (
                    <span className="text-2xs text-ink-faint">nicht verdoppelbar</span>
                  )}
                  {dish.portions === 1 && dish.factors.length > 1 && (
                    <span className="text-2xs text-ink-faint">
                      auch {dish.factors.slice(1).map((f) => FACTOR_WORD[f]).join(" & ")}
                    </span>
                  )}
                  {dish.rating && (
                    <span className="text-2xs text-accent">{stars(dish.rating)}</span>
                  )}
                  <span className="text-2xs text-ink-faint sm:hidden">
                    {dish.categories.map((category) => category.name).join(" · ")}
                  </span>
                </div>
              </td>
              <td className="hidden px-3 py-2 sm:table-cell">
                <span className="flex flex-wrap gap-1">
                  {dish.categories.map((category) => (
                    <span
                      key={category.id}
                      className="chip"
                      title={AXIS_LABEL[category.axis]}
                    >
                      {category.name}
                    </span>
                  ))}
                </span>
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{dish.portions}</td>
              <td className="hidden px-3 py-2 text-sm sm:table-cell">
                <NutritionCell nutrition={dish.nutrition} />
              </td>
              <td className="hidden px-3 py-2 text-ink-muted md:table-cell">
                {EFFORT_LABEL[dish.effort]}
              </td>
              <td className="hidden px-3 py-2 text-ink-muted md:table-cell">
                {dish.weeks_since_cooked === null
                  ? "noch nie"
                  : dish.weeks_since_cooked === 0
                    ? "diese Woche"
                    : `vor ${dish.weeks_since_cooked} Wo.`}
              </td>
              <td className="px-3 py-2 text-right">
                <Link to={`/dishes/${dish.id}`} className="btn-ghost btn-sm">
                  <IconBook className="h-3.5 w-3.5" />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
