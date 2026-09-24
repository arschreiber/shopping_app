/**
 * Plan-Warnungen (general_plan.md §5). Drei Stufen, drei Farben, keine Icons-Parade:
 * Fehler rot, Warnung amber, Hinweis grau. Slot-Bezug macht sie anklickbar.
 */
import type { Warning } from "../api/client";
import { DAY_SHORT, } from "../lib/dates";
import { MEAL_LABEL } from "../lib/format";

const TONE = {
  ERROR: "border-danger-line bg-danger-soft text-danger",
  WARN: "border-warn-line bg-warn-soft text-warn",
  INFO: "border-info-line bg-info-soft text-info",
} as const;

export function WarningList({
  warnings,
  onSelect,
  max,
}: {
  warnings: Warning[];
  onSelect?: (day: number, meal: "LUNCH" | "DINNER") => void;
  max?: number;
}) {
  if (warnings.length === 0) return null;
  const order = { ERROR: 0, WARN: 1, INFO: 2 } as const;
  const sorted = [...warnings].sort((a, b) => order[a.level] - order[b.level]);
  const shown = max ? sorted.slice(0, max) : sorted;

  return (
    <ul className="flex flex-col gap-1.5">
      {shown.map((warning, index) => {
        const clickable = onSelect && typeof warning.day === "number" && !!warning.meal;
        const content = (
          <>
            <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-60" />
            <span className="flex-1">{warning.text}</span>
            {typeof warning.day === "number" && warning.meal && (
              <span className="shrink-0 text-2xs opacity-70">
                {DAY_SHORT[warning.day]} {MEAL_LABEL[warning.meal]}
              </span>
            )}
          </>
        );
        const className = `flex items-start gap-2 rounded border px-2.5 py-1.5 text-sm ${TONE[warning.level]}`;
        return (
          <li key={`${warning.code}-${index}`}>
            {clickable ? (
              <button
                type="button"
                onClick={() => onSelect!(warning.day!, warning.meal!)}
                className={`${className} w-full text-left transition-opacity duration-fast hover:opacity-80`}
              >
                {content}
              </button>
            ) : (
              <div className={className}>{content}</div>
            )}
          </li>
        );
      })}
      {max && sorted.length > max && (
        <li className="pl-1 text-xs text-ink-faint">
          … und {sorted.length - max} weitere
        </li>
      )}
    </ul>
  );
}

export function ScoreLines({
  contributions,
}: {
  contributions: { rule: string; delta: number; text: string }[];
}) {
  if (contributions.length === 0) return null;
  return (
    <ul className="flex flex-col gap-0.5">
      {[...contributions]
        .sort((a, b) => b.delta - a.delta)
        .map((contribution) => (
          <li
            key={contribution.rule}
            className="flex items-baseline justify-between gap-3 text-xs"
          >
            <span className="text-ink-muted">{contribution.text}</span>
            <span
              className={[
                "shrink-0 font-mono text-2xs tabular-nums",
                contribution.delta > 0 ? "text-accent" : "text-danger",
              ].join(" ")}
            >
              {contribution.delta > 0 ? "+" : ""}
              {contribution.delta.toFixed(1).replace(".", ",")}
            </span>
          </li>
        ))}
    </ul>
  );
}
