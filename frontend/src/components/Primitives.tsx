/** Wiederverwendbare Bausteine: Buttons, Selects, Toggles, leere Zustände. */
import type { ReactNode } from "react";

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  size = "md",
  label,
  block = false,
}: {
  value: T;
  options: { value: T; label: string; title?: string }[];
  onChange: (value: T) => void;
  size?: "xs" | "sm" | "md";
  label?: string;
  /** Füllt die Breite des Elternteils - für Rasterzellen, die sich die Woche teilen. */
  block?: boolean;
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className={[
        "overflow-hidden rounded border border-line bg-surface",
        block ? "flex w-full" : "inline-flex",
      ].join(" ")}
    >
      {options.map((option, index) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            title={option.title}
            aria-pressed={active}
            onClick={() => onChange(option.value)}
            className={[
              "transition-colors duration-fast",
              size === "xs"
                ? `${block ? "px-0.5" : "px-1.5"} py-px text-2xs`
                : size === "sm"
                  ? "px-2 py-1 text-xs"
                  : "px-2.5 py-1.5 text-sm",
              // Breite nach Inhalt, Rest gleich verteilt: "vorgekocht|frisch" passt so in
              // eine schmale Zelle, wo zwei gleich breite Hälften "frisch" abschneiden.
              block ? "flex-auto whitespace-nowrap" : "",
              index > 0 ? "border-l border-line" : "",
              active
                ? "bg-accent-soft font-medium text-accent"
                : "text-ink-muted hover:bg-sunken hover:text-ink",
            ].join(" ")}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

export function Stepper({
  value,
  min = 0,
  max = 2,
  onChange,
  label,
}: {
  value: number;
  min?: number;
  max?: number;
  onChange: (value: number) => void;
  label: string;
}) {
  return (
    <div className="inline-flex items-center rounded border border-line bg-surface">
      <button
        type="button"
        aria-label={`${label} verringern`}
        disabled={value <= min}
        onClick={() => onChange(value - 1)}
        className="px-2 py-1 text-ink-muted transition-colors duration-fast hover:bg-sunken
                   hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
      >
        −
      </button>
      <span className="min-w-6 border-x border-line px-1 py-1 text-center text-sm">{value}</span>
      <button
        type="button"
        aria-label={`${label} erhöhen`}
        disabled={value >= max}
        onClick={() => onChange(value + 1)}
        className="px-2 py-1 text-ink-muted transition-colors duration-fast hover:bg-sunken
                   hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent"
      >
        +
      </button>
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="group inline-flex items-center gap-2 text-sm text-ink"
    >
      <span
        className={[
          "relative h-4 w-7 rounded-full border transition-colors duration-fast",
          checked ? "border-accent bg-accent" : "border-line-strong bg-sunken",
        ].join(" ")}
      >
        <span
          className={[
            "absolute top-0.5 h-2.5 w-2.5 rounded-full bg-surface transition-all duration-fast",
            checked ? "left-3.5" : "left-0.5",
          ].join(" ")}
        />
      </span>
      {label}
    </button>
  );
}

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-line
                    bg-surface px-6 py-12 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="max-w-sm text-sm text-ink-muted">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-ink-muted" role="status">
      <span className="h-3 w-3 animate-spin rounded-full border border-line-strong border-t-accent" />
      {label ?? "lädt …"}
    </div>
  );
}

export function SectionTitle({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      <h2 className="label">{children}</h2>
      {action}
    </div>
  );
}
