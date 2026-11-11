/**
 * Eine Zeile "Nährstoff - Menge - % vom Tageswert" mit Balken. Dieselbe Darstellung im
 * Gericht (je Portion) und im Artikel (je Bezugsgröße), damit beides gleich gelesen wird.
 */
import { formatNumber } from "../../lib/format";

export function MicroBar({
  label,
  unit,
  amount,
  share,
  kind,
  partial = false,
  badge,
  badgeTitle,
  onClick,
  selected = false,
  clickTitle = "Zeigt, welche Zutat wie viel beiträgt",
}: {
  label: string;
  unit: string;
  amount: string | number;
  share?: string | number | null;
  kind?: "target" | "limit" | null;
  partial?: boolean;
  badge?: string; // z. B. "E" für "vom Etikett"
  badgeTitle?: string;
  onClick?: () => void; // klickbar: z. B. Aufschlüsselung nach Zutaten
  clickTitle?: string;
  selected?: boolean;
}) {
  const percent = share === null || share === undefined ? null : Number(share);
  // Bei Obergrenzen (Salz, gesättigte Fette) ist "voll" kein Erfolg.
  const over = kind === "limit" && percent !== null && percent > 33;
  const body = (
    <>
      <span className="truncate text-xs text-ink-muted">
        {label}
        {kind === "limit" && <span className="text-ink-faint"> (max.)</span>}
      </span>
      <span className="text-xs tabular-nums">
        {formatNumber(amount)}
        <span className="text-2xs text-ink-faint"> {unit}</span>
        {partial && (
          <span className="text-warn" title="nicht für jede Zutat bekannt">
            *
          </span>
        )}
        {percent !== null && (
          <span className="ml-1.5 inline-block w-9 text-right text-2xs text-ink-faint">
            {percent} %
          </span>
        )}
        {badge !== undefined && (
          <span
            className="ml-1 inline-block w-2 text-2xs font-medium text-accent"
            title={badgeTitle}
          >
            {badge}
          </span>
        )}
      </span>
      {percent !== null && (
        <span className="col-span-2 h-1 overflow-hidden rounded-full bg-line">
          <span
            className={["block h-full rounded-full", over ? "bg-warn" : "bg-accent"].join(" ")}
            style={{ width: `${Math.min(percent, 100)}%` }}
          />
        </span>
      )}
    </>
  );
  if (!onClick) {
    return <dd className="grid grid-cols-[1fr_auto] items-baseline gap-x-2">{body}</dd>;
  }
  return (
    <dd>
      <button
        type="button"
        onClick={onClick}
        aria-pressed={selected}
        title={clickTitle}
        className={[
          "-mx-1 grid w-[calc(100%+0.5rem)] grid-cols-[1fr_auto] items-baseline gap-x-2",
          "rounded px-1 py-0.5 text-left hover:bg-accent-soft",
          selected ? "bg-accent-soft" : "",
        ].join(" ")}
      >
        {body}
      </button>
    </dd>
  );
}
