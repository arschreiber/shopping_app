/**
 * Nährwerte eines Gerichts, je Portion (nur im Gerichte-Tab - der Wochenplan bleibt frei
 * davon).
 *
 * Gerechnet wird auf dem Server, auch für das noch nicht gespeicherte Formular: die
 * Logik steht in `domain/nutrition.py` und soll hier nicht ein zweites Mal existieren
 * (ARCHITECTURE.md §7).
 *
 * Wichtiger als die Zahlen ist ihre Verlässlichkeit: fehlen Angaben oder steht eine
 * Zutat ohne Menge im Rezept, ist die Summe eine *Untergrenze*. Das steht dann dabei,
 * statt eine zu niedrige Zahl als Wahrheit auszugeben.
 */
import { useEffect, useState } from "react";
import type { DishNutrition, Unit } from "../../api/client";
import { previewNutrition } from "../../api/hooks";
import { formatNumber } from "../../lib/format";

export type NutritionSource = {
  article_id: number;
  article_name: string;
  quantity: string | null;
  unit: Unit;
};

export function NutritionPanel({
  rows,
  portions,
}: {
  rows: NutritionSource[];
  portions: number;
}) {
  const [data, setData] = useState<DishNutrition | null>(null);
  const signature = JSON.stringify([
    portions,
    rows.map((row) => [row.article_id, row.quantity, row.unit]),
  ]);

  useEffect(() => {
    if (rows.length === 0) {
      setData(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const result = await previewNutrition(
          portions,
          rows.map((row) => ({
            article_id: row.article_id,
            quantity: row.quantity,
            unit: row.unit,
          })),
        );
        if (!cancelled) setData(result);
      } catch {
        if (!cancelled) setData(null);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  if (!data || !data.has_any) return null;

  const byId = new Map(rows.map((row) => [row.article_id, row.article_name]));
  const missing = data.missing_article_ids.map((id) => byId.get(id) ?? `#${id}`);
  const open = data.open_quantity_article_ids.map((id) => byId.get(id) ?? `#${id}`);

  return (
    <div className="rounded-md border border-line bg-sunken/40 px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
        <span className="label">je Portion</span>
        <Figure value={data.per_portion.kcal} unit="kcal" strong />
        <Figure value={data.per_portion.carbs_g} unit="g" label="Kohlenhydrate" />
        <Figure value={data.per_portion.fat_g} unit="g" label="Fett" />
        <Figure value={data.per_portion.protein_g} unit="g" label="Eiweiß" />
        <span className="ml-auto text-2xs text-ink-faint">
          gesamt {formatNumber(data.total.kcal)} kcal
        </span>
      </div>

      {!data.is_complete && (
        <p className="mt-1.5 text-2xs text-warn">
          Mindestens so viel – {missing.length > 0 && <>ohne Angabe: {missing.join(", ")}</>}
          {missing.length > 0 && open.length > 0 && "; "}
          {open.length > 0 && <>ohne Menge im Rezept: {open.join(", ")}</>}
        </p>
      )}
    </div>
  );
}

function Figure({
  value,
  unit,
  label,
  strong,
}: {
  value: string | number;
  unit: string;
  label?: string;
  strong?: boolean;
}) {
  return (
    <span className="flex items-baseline gap-1">
      <span
        className={[
          "tabular-nums",
          strong ? "text-base font-semibold" : "text-sm font-medium",
        ].join(" ")}
      >
        {formatNumber(value)}
      </span>
      <span className="text-2xs text-ink-muted">
        {unit}
        {label ? ` ${label}` : ""}
      </span>
    </span>
  );
}

/** Kompakte Variante für die Gerichte-Liste. */
export function NutritionCell({ nutrition }: { nutrition: DishNutrition | null | undefined }) {
  if (!nutrition?.has_any) return <span className="text-ink-faint">–</span>;
  return (
    <span className="whitespace-nowrap">
      <span className="tabular-nums">{formatNumber(nutrition.per_portion.kcal)}</span>
      <span className="text-2xs text-ink-faint"> kcal</span>
      <span className="ml-2 tabular-nums text-ink-muted">
        {formatNumber(nutrition.per_portion.protein_g)}
      </span>
      <span className="text-2xs text-ink-faint"> g E</span>
      {!nutrition.is_complete && (
        <span className="ml-1 text-warn" title="unvollständig – mindestens so viel">
          +
        </span>
      )}
    </span>
  );
}
