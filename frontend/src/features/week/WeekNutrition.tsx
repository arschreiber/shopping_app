/**
 * Nährwerte im Wochenboard (Ansicht "Nährwerte"): eine Zeile je Gericht, eine Summe je
 * Tag und ein Ø je Portion für die Woche. Gerechnet wird im Backend
 * (`domain/week_nutrition.py`): ein Tag ist Mittag plus Abend für *eine* Person, der Ø
 * zählt jede geplante Mahlzeit einmal.
 */
import type { ReactNode } from "react";
import type { DayNutrition, Nutrients, NutritionSum } from "../../api/client";
import { formatNumber } from "../../lib/format";
import { MicroGrid } from "../nutrition/MicroGrid";

/** "898 kcal · 47 g P" - kurz genug für eine Slot-Karte. */
export function MacroLine({
  nutrients,
  complete = true,
  className = "",
}: {
  nutrients: Nutrients;
  complete?: boolean;
  className?: string;
}) {
  return (
    <span className={["tabular-nums", className].join(" ")}>
      {!complete && (
        <span className="text-warn" title="unvollständig – mindestens so viel">
          ≥{" "}
        </span>
      )}
      {formatNumber(nutrients.kcal)} kcal · {formatNumber(Math.round(Number(nutrients.protein_g)))} g P
    </span>
  );
}

/** Summe eines Tages unter den beiden Mahlzeiten - Klick öffnet die Details. */
export function DayTotal({
  day,
  mealsPerDay,
  selected,
  onSelect,
}: {
  day: DayNutrition;
  mealsPerDay: number;
  selected: boolean;
  onSelect: () => void;
}) {
  if (day.meal_count === 0) {
    return (
      <div className="rounded-md border border-dashed border-line px-2.5 py-1.5 text-2xs
                      text-ink-faint">
        nichts erfasst
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      title="Nährwerte des Tages je Person anzeigen"
      className={[
        "flex w-full flex-col items-start rounded-md border px-2.5 py-1.5 text-left",
        "transition-colors duration-fast",
        selected
          ? "border-accent-line bg-accent-soft"
          : "border-line bg-sunken/60 hover:border-line-strong",
      ].join(" ")}
    >
      <span className="text-xs font-medium tabular-nums text-ink">
        {!day.complete && (
          <span className="text-warn" title="unvollständig – mindestens so viel">
            ≥{" "}
          </span>
        )}
        {formatNumber(day.nutrients.kcal)} kcal
      </span>
      <span className="text-2xs tabular-nums text-ink-muted">
        {formatNumber(Math.round(Number(day.nutrients.protein_g)))} g Protein
      </span>
      <span className="text-2xs text-ink-faint">
        {day.meal_count < mealsPerDay
          ? `nur ${day.meal_count} von ${mealsPerDay} Mahlzeiten`
          : "Mittag + Abend"}
      </span>
    </button>
  );
}

const MACROS = [
  { code: "kcal", label: "kcal", unit: "" },
  { code: "carbs_g", label: "Kohlenhydrate", unit: "g" },
  { code: "fat_g", label: "Fett", unit: "g" },
  { code: "protein_g", label: "Eiweiß", unit: "g" },
] as const;

/** Makros plus Vitamine und Mineralstoffe mit Balken - für einen Tag oder den Ø. */
export function NutritionDetail({
  title,
  subtitle,
  sum,
  footnote,
  onClose,
  id,
  action,
}: {
  id?: string;
  /** Rechts neben dem Titel, z. B. der 1×/2×-Schalter. */
  action?: ReactNode;
  title: string;
  subtitle: string;
  sum: NutritionSum;
  footnote: string;
  onClose?: () => void;
}) {
  return (
    <section id={id} className="card flex scroll-mt-16 flex-col gap-3 p-4">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-sm font-semibold">{title}</h2>
        <span className="text-xs text-ink-muted">{subtitle}</span>
        {action && <span className="ml-auto">{action}</span>}
        {onClose && (
          <button type="button" onClick={onClose} className="btn-ghost btn-sm ml-auto">
            schließen
          </button>
        )}
      </div>
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
        {MACROS.map((macro) => (
          <span key={macro.code} className="flex items-baseline gap-1">
            <span
              className={[
                "tabular-nums",
                macro.code === "kcal" ? "text-base font-semibold" : "text-sm font-medium",
              ].join(" ")}
            >
              {formatNumber(sum.nutrients[macro.code])}
            </span>
            <span className="text-2xs text-ink-muted">
              {macro.unit} {macro.label}
            </span>
          </span>
        ))}
      </div>
      {!sum.complete && (
        <p className="text-2xs text-warn">
          Mindestens so viel – nicht jede Zutat hat Nährwerte oder eine Menge.
        </p>
      )}
      {sum.micros.length > 0 && <MicroGrid values={sum.micros} />}
      <p className="text-2xs text-ink-faint">{footnote}</p>
    </section>
  );
}

/** Dezimalzahl als String vervielfachen, mit so vielen Nachkommastellen wie vorher. */
function times(value: string, factor: number): string {
  const places = (value.split(".")[1] ?? "").length;
  return (Number(value) * factor).toFixed(places);
}

/**
 * Ø je Portion -> Ø je Tag: zwei Portionen (Mittag + Abend). Reine Vervielfachung - auch
 * die Balken, denn der Anteil am Tageswert wächst linear mit der Menge.
 */
export function scaleSum(sum: NutritionSum, factor: number): NutritionSum {
  if (factor === 1) return sum;
  return {
    ...sum,
    nutrients: {
      kcal: times(sum.nutrients.kcal, factor),
      carbs_g: times(sum.nutrients.carbs_g, factor),
      fat_g: times(sum.nutrients.fat_g, factor),
      protein_g: times(sum.nutrients.protein_g, factor),
    },
    micros: sum.micros.map((value) => ({
      ...value,
      amount: times(value.amount, factor),
      share: value.share === null || value.share === undefined ? value.share : times(value.share, factor),
    })),
  };
}
