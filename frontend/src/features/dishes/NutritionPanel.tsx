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
import type { DishMicros, DishNutrition, IngredientShare, Unit } from "../../api/client";
import { previewNutrition } from "../../api/hooks";
import { formatNumber } from "../../lib/format";
import { Breakdown, type BreakdownTarget } from "../nutrition/Breakdown";
import { MicroBar } from "../nutrition/MicroBar";

export type NutritionSource = {
  article_id: number;
  article_name: string;
  quantity: string | null;
  unit: Unit;
};

/**
 * Server-Vorschau der Nährwerte, entprellt. Eigener Hook, weil das Formular dieselben
 * Zahlen zweimal zeigt (Steckbrief und Detail) - abgefragt werden sie einmal.
 */
export function useNutritionPreview(
  rows: NutritionSource[],
  portions: number,
): DishNutrition | null {
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

  return rows.length === 0 ? null : data;
}

export function NutritionPanel({
  rows,
  data,
  microsOpen = false,
}: {
  rows: NutritionSource[];
  data: DishNutrition | null;
  /** Vitamine & Mineralstoffe gleich aufgeklappt (im Formular: ja). */
  microsOpen?: boolean;
}) {
  // Angeklickter Nährwert - darunter klappt "woher kommt das?" auf.
  const [target, setTarget] = useState<BreakdownTarget | null>(null);
  const toggle = (next: BreakdownTarget) =>
    setTarget((current) => (current?.code === next.code ? null : next));

  if (!data || !data.has_any) return null;

  const byId = new Map(rows.map((row) => [row.article_id, row.article_name]));
  const missing = data.missing_article_ids.map((id) => byId.get(id) ?? `#${id}`);
  const open = data.open_quantity_article_ids.map((id) => byId.get(id) ?? `#${id}`);

  return (
    <div className="rounded-md border border-line bg-sunken/40 px-3 py-2">
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1">
        <span className="label">je Portion</span>
        {MACROS.map((macro) => (
          <Figure
            key={macro.code}
            value={data.per_portion[macro.code]}
            unit={macro.unit}
            label={macro.code === "kcal" ? undefined : macro.label}
            strong={macro.code === "kcal"}
            selected={target?.code === macro.code}
            onClick={data.breakdown?.length ? () => toggle(macro) : undefined}
          />
        ))}
        <span className="ml-auto text-2xs text-ink-faint">
          gesamt {formatNumber(data.total.kcal)} kcal
        </span>
      </div>

      {target && isMacro(target.code) && data.breakdown && (
        <Breakdown
          target={target}
          breakdown={data.breakdown}
          names={byId}
          onClose={() => setTarget(null)}
        />
      )}

      {!data.is_complete && (
        <p className="mt-1.5 text-2xs text-warn">
          Mindestens so viel – {missing.length > 0 && <>ohne Angabe: {missing.join(", ")}</>}
          {missing.length > 0 && open.length > 0 && "; "}
          {open.length > 0 && <>ohne Menge im Rezept: {open.join(", ")}</>}
        </p>
      )}

      {data.micros?.has_any && (
        <MicroSection
          micros={data.micros}
          names={byId}
          breakdown={data.breakdown ?? []}
          target={target && !isMacro(target.code) ? target : null}
          onSelect={toggle}
          onClose={() => setTarget(null)}
          initiallyOpen={microsOpen}
        />
      )}
    </div>
  );
}

const GROUPS = ["Allgemein", "Mineralstoffe", "Vitamine"];

const MACROS = [
  { code: "kcal", label: "Energie", unit: "kcal" },
  { code: "carbs_g", label: "Kohlenhydrate", unit: "g" },
  { code: "fat_g", label: "Fett", unit: "g" },
  { code: "protein_g", label: "Eiweiß", unit: "g" },
] as const;

function isMacro(code: string) {
  return MACROS.some((macro) => macro.code === code);
}

/**
 * Vitamine und Mineralstoffe aus dem BLS. Eingeklappt, weil sie beim Planen selten
 * zählen - aufgeklappt sollen sie auf einen Blick zeigen, was das Gericht *trägt*.
 * Der Balken ist der Anteil am Tageswert, nicht an einem Ziel pro Mahlzeit.
 */
function MicroSection({
  micros,
  names,
  breakdown,
  target,
  onSelect,
  onClose,
  initiallyOpen,
}: {
  micros: DishMicros;
  names: Map<number, string>;
  breakdown: IngredientShare[];
  target: BreakdownTarget | null;
  onSelect: (target: BreakdownTarget) => void;
  onClose: () => void;
  initiallyOpen: boolean;
}) {
  const [expanded, setExpanded] = useState(initiallyOpen);
  const name = (id: number) => names.get(id) ?? `#${id}`;
  const gaps = [
    micros.missing_article_ids.length > 0 &&
      `ohne Referenz: ${micros.missing_article_ids.map(name).join(", ")}`,
    micros.skipped_article_ids.length > 0 &&
      `nicht im BLS: ${micros.skipped_article_ids.map(name).join(", ")}`,
    micros.open_quantity_article_ids.length > 0 &&
      `ohne Menge/Stückgewicht: ${micros.open_quantity_article_ids.map(name).join(", ")}`,
  ].filter(Boolean);

  return (
    <div className="mt-2 border-t border-line pt-1.5">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
        className="flex w-full items-baseline gap-2 text-left"
      >
        <span className="label">Vitamine &amp; Mineralstoffe</span>
        <span className="text-2xs text-ink-faint">
          aus {micros.counted} von {micros.ingredient_count} Zutaten
        </span>
        <span className="ml-auto text-xs text-ink-muted">{expanded ? "▾" : "▸"}</span>
      </button>

      {expanded && (
        <>
          <div className="mt-2 grid gap-x-6 gap-y-3 sm:grid-cols-3">
            {GROUPS.map((group) => (
              <dl key={group} className="flex flex-col gap-1">
                <dt className="text-2xs font-medium uppercase tracking-wide text-ink-faint">
                  {group}
                </dt>
                {micros.values
                  .filter((value) => value.group === group)
                  .map((value) => (
                    <MicroBar
                      key={value.code}
                      label={value.label}
                      unit={value.unit}
                      amount={value.amount}
                      share={value.share}
                      kind={value.kind}
                      partial={value.partial}
                      selected={target?.code === value.code}
                      onClick={
                        breakdown.length
                          ? () =>
                              onSelect({ code: value.code, label: value.label, unit: value.unit })
                          : undefined
                      }
                    />
                  ))}
              </dl>
            ))}
          </div>
          {target && (
            <Breakdown target={target} breakdown={breakdown} names={names} onClose={onClose} />
          )}
          {gaps.length > 0 && (
            <p className="mt-2 text-2xs text-warn">Mindestens so viel – {gaps.join("; ")}</p>
          )}
          <p className="mt-1.5 text-2xs text-ink-faint">
            Balken: Anteil am Tageswert ({micros.reference_person}). Klick auf einen Wert
            zeigt, welche Zutat wie viel beiträgt. * nicht für jede Zutat bekannt. Quelle:{" "}
            {micros.attribution}
          </p>
        </>
      )}
    </div>
  );
}

function Figure({
  value,
  unit,
  label,
  strong,
  selected = false,
  onClick,
}: {
  value: string | number;
  unit: string;
  label?: string;
  strong?: boolean;
  selected?: boolean;
  onClick?: () => void;
}) {
  const body = (
    <>
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
    </>
  );
  if (!onClick) return <span className="flex items-baseline gap-1">{body}</span>;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      title="Zeigt, welche Zutat wie viel beiträgt"
      className={[
        "-mx-1 flex items-baseline gap-1 rounded px-1 hover:bg-accent-soft",
        selected ? "bg-accent-soft" : "",
      ].join(" ")}
    >
      {body}
    </button>
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
