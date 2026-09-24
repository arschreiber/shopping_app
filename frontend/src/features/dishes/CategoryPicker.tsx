/**
 * Kategorien als Chip-Picker, häufigste Chips vorne (ARCHITECTURE.md §7 - Ersatz für die
 * weggefallenen LLM-Vorschläge). Neue Werte entstehen durch Tippen, ohne Verwaltungsseite.
 */
import { useMemo, useState } from "react";
import type { Category } from "../../api/client";
import { useCategories } from "../../api/hooks";
import { IconPlus } from "../../components/Icons";
import { AXIS_LABEL } from "../../lib/format";

export type CategoryChoice = { axis: "SIDE" | "PROTEIN" | "CUISINE"; name: string };

const AXES: CategoryChoice["axis"][] = ["SIDE", "PROTEIN", "CUISINE"];

const HINTS: Record<CategoryChoice["axis"], string> = {
  SIDE: "Reis, Nudeln, Kartoffeln, Brot …",
  PROTEIN: "Fisch, Hähnchen, Hirtenkäse, Hülsenfrüchte …",
  CUISINE: "italienisch, asiatisch, indisch …",
};

export function CategoryPicker({
  selected,
  onChange,
}: {
  selected: CategoryChoice[];
  onChange: (next: CategoryChoice[]) => void;
}) {
  const { data } = useCategories();
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const byAxis = useMemo(() => {
    const map: Record<string, Category[]> = { SIDE: [], PROTEIN: [], CUISINE: [] };
    for (const category of data ?? []) map[category.axis]?.push(category);
    return map;
  }, [data]);

  function toggle(choice: CategoryChoice) {
    const exists = selected.some(
      (entry) => entry.axis === choice.axis && entry.name === choice.name,
    );
    onChange(
      exists
        ? selected.filter((entry) => !(entry.axis === choice.axis && entry.name === choice.name))
        : [...selected.filter((entry) => entry.axis !== choice.axis), choice],
    );
  }

  function addDraft(axis: CategoryChoice["axis"]) {
    const name = (drafts[axis] ?? "").trim();
    if (!name) return;
    toggle({ axis, name });
    setDrafts((current) => ({ ...current, [axis]: "" }));
  }

  return (
    <div className="flex flex-col gap-3">
      {AXES.map((axis) => {
        const active = selected.find((entry) => entry.axis === axis);
        return (
          <div key={axis}>
            <div className="mb-1 flex items-baseline gap-2">
              <span className="label">{AXIS_LABEL[axis]}</span>
              <span className="text-2xs text-ink-faint">{HINTS[axis]}</span>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {byAxis[axis]?.map((category) => {
                const isActive = active?.name === category.name;
                return (
                  <button
                    key={category.id}
                    type="button"
                    onClick={() => toggle({ axis, name: category.name })}
                    className={isActive ? "chip chip-accent" : "chip hover:border-line-strong"}
                  >
                    {category.name}
                    {category.usage > 0 && (
                      <span className="text-2xs opacity-60">{category.usage}</span>
                    )}
                  </button>
                );
              })}
              {active && !byAxis[axis]?.some((entry) => entry.name === active.name) && (
                <button
                  type="button"
                  onClick={() => toggle(active)}
                  className="chip chip-accent"
                >
                  {active.name}
                </button>
              )}
              <span className="inline-flex items-center">
                <input
                  value={drafts[axis] ?? ""}
                  onChange={(event) =>
                    setDrafts((current) => ({ ...current, [axis]: event.target.value }))
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addDraft(axis);
                    }
                  }}
                  placeholder="neu …"
                  aria-label={`${AXIS_LABEL[axis]} hinzufügen`}
                  className="w-24 rounded-l border border-line bg-surface px-2 py-0.5 text-xs
                             placeholder:text-ink-faint focus:border-accent-line"
                />
                <button
                  type="button"
                  onClick={() => addDraft(axis)}
                  aria-label={`${AXIS_LABEL[axis]} übernehmen`}
                  className="rounded-r border border-l-0 border-line bg-surface px-1.5 py-[3px]
                             text-ink-muted hover:bg-sunken hover:text-ink"
                >
                  <IconPlus className="h-3 w-3" />
                </button>
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
