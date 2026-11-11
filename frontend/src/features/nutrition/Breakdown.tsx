/**
 * "Woher kommt das?" - die Zutaten eines Gerichts, sortiert nach ihrem Beitrag zu
 * einem Nährwert, je Portion. Der Balken ist der Anteil an der Summe des Gerichts.
 *
 * Gerechnet wird auf dem Server (`breakdown` in DishNutritionOut); hier wird nur
 * sortiert und beschriftet.
 */
import { Link } from "react-router-dom";
import type { IngredientShare } from "../../api/client";
import { formatNumber } from "../../lib/format";

export type BreakdownTarget = { code: string; label: string; unit: string };

export function Breakdown({
  target,
  breakdown,
  names,
  onClose,
}: {
  target: BreakdownTarget;
  breakdown: IngredientShare[];
  names: Map<number, string>;
  onClose: () => void;
}) {
  const known = breakdown
    .filter((part) => part.values[target.code] !== undefined)
    .map((part) => ({ id: part.article_id, amount: Number(part.values[target.code]) }))
    .sort((a, b) => b.amount - a.amount);
  const total = known.reduce((sum, part) => sum + part.amount, 0);
  const counted = new Set(breakdown.map((part) => part.article_id));
  const unknown = [
    ...breakdown.filter((part) => part.values[target.code] === undefined).map((p) => p.article_id),
    ...[...names.keys()].filter((id) => !counted.has(id)),
  ];
  const name = (id: number) => names.get(id) ?? `#${id}`;

  return (
    <div className="mt-2 rounded border border-line bg-surface px-2.5 py-2">
      <div className="flex items-baseline gap-2">
        <span className="text-xs font-medium">{target.label} je Portion – woher?</span>
        <span className="text-2xs text-ink-faint">
          {formatNumber(total)} {target.unit} gesamt
        </span>
        <Link
          to={`/nutrients?code=${encodeURIComponent(target.code)}`}
          className="ml-auto text-2xs text-ink-muted underline-offset-2 hover:text-accent
                     hover:underline"
          title="Alle Artikel nach diesem Nährstoff sortiert"
        >
          alle Artikel →
        </Link>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-ink-muted hover:text-ink"
          aria-label="Aufschlüsselung schließen"
        >
          ✕
        </button>
      </div>
      <ul className="mt-1.5 flex flex-col gap-1">
        {known.map((part) => {
          const percent = total > 0 ? Math.round((part.amount / total) * 100) : 0;
          return (
            <li key={part.id} className="grid grid-cols-[1fr_auto] items-baseline gap-x-2">
              <span className="truncate text-xs text-ink-muted">{name(part.id)}</span>
              <span className="text-xs tabular-nums">
                {formatNumber(part.amount)}
                <span className="text-2xs text-ink-faint"> {target.unit}</span>
                <span className="ml-1.5 inline-block w-9 text-right text-2xs text-ink-faint">
                  {percent} %
                </span>
              </span>
              <span className="col-span-2 h-1 overflow-hidden rounded-full bg-line">
                <span
                  className="block h-full rounded-full bg-accent"
                  style={{ width: `${percent}%` }}
                />
              </span>
            </li>
          );
        })}
      </ul>
      {unknown.length > 0 && (
        <p className="mt-1.5 text-2xs text-ink-faint">
          Unbekannt für: {unknown.map(name).join(", ")}
        </p>
      )}
    </div>
  );
}
