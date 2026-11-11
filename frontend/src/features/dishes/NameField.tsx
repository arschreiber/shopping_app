/**
 * Name eines neuen Gerichts - mit vorhandenen Gerichten als Vorlage.
 *
 * Chili, Chili mit Beilage und One-Pot-Chili teilen sich die meisten Zutaten. Wer
 * "Chili sin…" tippt, bekommt die ähnlich benannten Gerichte angeboten und übernimmt
 * Zutaten und Eigenschaften, statt sie neu einzutippen. Ohne Pfeiltaste bleibt Enter
 * "Speichern" - die Liste drängt sich nicht in den Weg.
 */
import { useMemo, useState } from "react";
import type { Dish, DishSummary } from "../../api/client";
import { fetchDish, useDishes } from "../../api/hooks";
import { errorText, useToast } from "../../components/Toast";

const MIN_WORD = 3;

function words(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[\s\-–,]+/)
    .filter((word) => word.length >= MIN_WORD);
}

/** Ähnlich benannte Gerichte, die meisten gemeinsamen Wörter zuerst. */
export function similarDishes(name: string, dishes: DishSummary[], limit = 4): DishSummary[] {
  const typed = words(name);
  if (typed.length === 0) return [];
  return dishes
    .map((dish) => {
      const own = words(dish.name);
      const lower = dish.name.toLowerCase();
      const score = typed.filter(
        (word) => lower.includes(word) || own.some((part) => word.startsWith(part)),
      ).length;
      return { dish, score };
    })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score || a.dish.name.length - b.dish.name.length)
    .slice(0, limit)
    .map((entry) => entry.dish);
}

export function NameField({
  value,
  onChange,
  inputRef,
  templates,
  onPickTemplate,
}: {
  value: string;
  onChange: (value: string) => void;
  inputRef?: (element: HTMLInputElement | null) => void;
  /** Vorlagen anbieten (nur beim Anlegen). */
  templates: boolean;
  onPickTemplate: (dish: Dish) => void;
}) {
  const dishes = useDishes();
  const toast = useToast();
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState<number | null>(null);

  const matches = useMemo(
    () => (templates ? similarDishes(value, dishes.data ?? []) : []),
    [templates, value, dishes.data],
  );
  const exists = (dishes.data ?? []).some(
    (dish) => dish.name.trim().toLowerCase() === value.trim().toLowerCase(),
  );
  const open = templates && focused && !dismissed && matches.length > 0;

  async function pick(dish: DishSummary) {
    setLoading(dish.id);
    try {
      onPickTemplate(await fetchDish(dish.id));
      setDismissed(true);
    } catch (error) {
      toast.show(errorText(error), "error");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="relative">
      <label className="label mb-1 block" htmlFor="dish-name">
        Name
      </label>
      <input
        id="dish-name"
        ref={inputRef}
        value={value}
        autoComplete="off"
        onChange={(event) => {
          onChange(event.target.value);
          setActive(-1);
          if (event.target.value.trim().length < MIN_WORD) setDismissed(false);
        }}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onKeyDown={(event) => {
          if (!open) return;
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((current) => Math.min(current + 1, matches.length - 1));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((current) => Math.max(current - 1, -1));
          } else if (event.key === "Enter" && active >= 0) {
            event.preventDefault();
            void pick(matches[active]);
          } else if (event.key === "Escape") {
            setDismissed(true);
          }
        }}
        placeholder="Hirtenkäse-Reispfanne"
        className="field px-3 py-2 text-lg font-medium"
        aria-autocomplete="list"
        aria-expanded={open}
        required
      />
      {templates && exists && (
        <p className="mt-1 text-2xs text-warn">
          „{value.trim()}“ gibt es schon – ein anderer Name oder das vorhandene bearbeiten.
        </p>
      )}
      {open && (
        <div
          role="listbox"
          className="absolute inset-x-0 top-full z-20 mt-1 overflow-hidden rounded-md border
                     border-line bg-surface shadow-pop"
        >
          <p className="px-3 py-1.5 text-2xs text-ink-faint">
            Ähnliche Gerichte · als Vorlage übernehmen
          </p>
          {matches.map((dish, index) => {
            const side = dish.categories.find((category) => category.axis === "SIDE");
            const protein = dish.categories.find((category) => category.axis === "PROTEIN");
            return (
              <button
                key={dish.id}
                type="button"
                role="option"
                aria-selected={index === active}
                // mousedown statt click: sonst schließt das Blur die Liste vorher.
                onMouseDown={(event) => {
                  event.preventDefault();
                  void pick(dish);
                }}
                onMouseEnter={() => setActive(index)}
                className={[
                  "flex w-full items-center gap-3 border-t border-line px-3 py-2 text-left",
                  index === active ? "bg-accent-soft" : "",
                ].join(" ")}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{dish.name}</span>
                  <span className="block truncate text-2xs text-ink-faint">
                    {[
                      `${dish.ingredient_count} Zutaten`,
                      side?.name,
                      protein?.name,
                      `${dish.portions} ${dish.portions === 1 ? "Portion" : "Portionen"}`,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                <span className="text-xs text-ink-muted">
                  {loading === dish.id ? "lädt …" : index === active ? "↵ übernehmen" : ""}
                </span>
              </button>
            );
          })}
          <p className="border-t border-line bg-sunken/60 px-3 py-1.5 text-2xs text-ink-faint">
            ↑↓ wählen · Esc leer anfangen
          </p>
        </div>
      )}
    </div>
  );
}
