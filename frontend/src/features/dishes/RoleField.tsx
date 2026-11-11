/**
 * Beilage und Protein im Steckbrief: erkannt aus den Zutaten, per Klick überstimmbar.
 *
 * Die Erkennung liegt im Backend (`domain/dish_roles.py`) und lernt aus den gespeicherten
 * Gerichten. Hier steht nur, wie das Ergebnis aussieht und was ein Klick bedeutet:
 *
 * - **auto**: die Kategorie folgt den Zutaten. Ändert sich die Zutatenliste, zieht sie mit.
 * - **manuell**: von Hand gewählt. Bleibt stehen, bis man "zurücksetzen" klickt.
 * - **Vorschlag**: keine Zutat trägt die Rolle, aber eine passt. Erst ein Klick setzt
 *   sie - gespeichert ist sie danach gelernt, beim nächsten Gericht also "auto".
 */
import { useEffect, useRef, useState } from "react";
import type { DishRoles, RoleCandidate, RoleDetection } from "../../api/client";
import { detectRoles, useCategories } from "../../api/hooks";
import { formatNumber } from "../../lib/format";
import type { NutritionSource } from "./NutritionPanel";

export type RoleAxis = "SIDE" | "PROTEIN";
export type RoleMode = "auto" | "manual" | "pending";

export const ROLE_AXES: RoleAxis[] = ["SIDE", "PROTEIN"];

export const ROLE_LABEL: Record<RoleAxis, string> = { SIDE: "Beilage", PROTEIN: "Protein" };
const GRAMS_LABEL: Record<RoleAxis, string> = { SIDE: "g KH", PROTEIN: "g Protein" };

export function detectionFor(roles: DishRoles | null, axis: RoleAxis): RoleDetection | null {
  if (!roles) return null;
  return axis === "SIDE" ? roles.side : roles.protein;
}

/** Was "auto" gerade bedeutet: erkannt, oder ein bestätigter Vorschlag. */
export function autoChoice(
  detection: RoleDetection | null,
  accepted: number | undefined,
): { name: string; from: RoleCandidate } | null {
  if (!detection) return null;
  if (detection.category && detection.source) {
    return { name: detection.category, from: detection.source };
  }
  const suggestion = detection.suggestion;
  if (suggestion && accepted === suggestion.article_id) {
    return { name: suggestion.category, from: suggestion };
  }
  return null;
}

export function sameName(a: string | null | undefined, b: string | null | undefined) {
  return (a ?? "").trim().toLowerCase() === (b ?? "").trim().toLowerCase();
}

/**
 * Entprellte Erkennung, sobald sich Zutaten oder Mengen ändern. `fresh` sagt, ob das
 * Ergebnis zu den aktuellen Zeilen gehört - angezeigt wird auch ein älteres (sonst
 * flackert der Steckbrief bei jedem Tastendruck), übernommen nur ein frisches.
 */
export function useDishRoles(rows: NutritionSource[]): {
  roles: DishRoles | null;
  fresh: boolean;
} {
  const [state, setState] = useState<{ signature: string; roles: DishRoles } | null>(null);
  const signature = JSON.stringify(rows.map((row) => [row.article_id, row.quantity, row.unit]));

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const roles = await detectRoles(
          rows.map((row) => ({
            article_id: row.article_id,
            quantity: row.quantity,
            unit: row.unit,
          })),
        );
        if (!cancelled) setState({ signature, roles });
      } catch {
        if (!cancelled) setState(null);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  return { roles: state?.roles ?? null, fresh: state?.signature === signature };
}

export function RoleField({
  axis,
  detection,
  value,
  mode,
  accepted,
  onChoose,
  onAccept,
  onReset,
}: {
  axis: RoleAxis;
  detection: RoleDetection | null;
  /** Die Kategorie, die gespeichert würde. */
  value: string | null;
  mode: RoleMode;
  accepted: number | undefined;
  /** Von Hand gewählt; `null` = bewusst keine. */
  onChoose: (name: string | null) => void;
  onAccept: (articleId: number) => void;
  onReset: () => void;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const auto = autoChoice(detection, accepted);
  const label = ROLE_LABEL[axis];
  const suggestion =
    mode === "auto" && !auto && detection?.suggestion ? detection.suggestion : null;

  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function choose(name: string | null) {
    onChoose(name);
    setOpen(false);
  }

  return (
    <div ref={wrapRef} className="relative flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="label w-14 shrink-0">{label}</span>
        {suggestion ? (
          <span className="text-xs text-ink-faint">nicht erkannt</span>
        ) : (
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-haspopup="dialog"
            className={[
              "chip px-2.5 text-sm",
              value
                ? mode === "manual"
                  ? "border-line-strong text-ink hover:bg-sunken"
                  : "chip-accent hover:bg-accent-soft/70"
                : "border-dashed hover:border-line-strong hover:text-ink",
            ].join(" ")}
          >
            {value ?? (axis === "SIDE" ? "keine" : "keins")}
            <span className="text-2xs opacity-60">▾</span>
          </button>
        )}
        {!suggestion && (value || mode === "manual") && (
          <span
            className={[
              "text-[10px] font-semibold uppercase tracking-wider",
              mode === "manual" ? "text-ink-muted" : "text-accent/80",
            ].join(" ")}
          >
            {mode === "manual" ? "manuell" : "auto"}
          </span>
        )}
      </div>

      {mode === "auto" && auto && (
        <span className="pl-16 text-2xs text-ink-faint">
          aus {auto.from.article_name}
          {Number(auto.from.grams) > 0 &&
            ` · ${formatNumber(auto.from.grams)} ${GRAMS_LABEL[axis]}`}
        </span>
      )}
      {mode === "manual" && !sameName(value, auto?.name ?? null) && (
        <span className="pl-16 text-2xs text-ink-faint">
          automatisch wäre {auto ? auto.name : axis === "SIDE" ? "keine" : "keins"} ·{" "}
          <button
            type="button"
            onClick={onReset}
            className="underline underline-offset-2 hover:text-ink"
          >
            zurücksetzen
          </button>
        </span>
      )}

      {suggestion && (
        <div className="flex flex-col gap-2 rounded border border-accent-line bg-surface p-2.5">
          <span className="text-xs">
            „{suggestion.article_name}“ war noch nie {label}, liefert hier aber die meisten{" "}
            {axis === "SIDE" ? "Kohlenhydrate" : "Gramm Protein"} (
            {formatNumber(suggestion.grams)} g).
          </span>
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => onAccept(suggestion.article_id)}
              className="btn-primary btn-sm"
            >
              Als {label} „{suggestion.category}“
            </button>
            <button type="button" onClick={() => setOpen(true)} className="btn-secondary btn-sm">
              andere wählen
            </button>
          </div>
          <span className="text-2xs text-ink-faint">
            wird mit dem Gericht gespeichert und beim nächsten Mal erkannt
          </span>
        </div>
      )}

      {open && (
        <RolePopover
          axis={axis}
          detection={detection}
          value={value}
          onChoose={choose}
        />
      )}
    </div>
  );
}

function RolePopover({
  axis,
  detection,
  value,
  onChoose,
}: {
  axis: RoleAxis;
  detection: RoleDetection | null;
  value: string | null;
  onChoose: (name: string | null) => void;
}) {
  const categories = useCategories();
  const [draft, setDraft] = useState("");
  const label = ROLE_LABEL[axis];
  const candidates = (detection?.candidates ?? [])
    .filter((candidate) => Number(candidate.grams) > 0 || candidate.known)
    .slice(0, 5);
  const shown = new Set(candidates.map((candidate) => candidate.category.toLowerCase()));
  const others = (categories.data ?? []).filter(
    (category) => category.axis === axis && !shown.has(category.name.toLowerCase()),
  );

  return (
    <div
      role="dialog"
      aria-label={`${label} wählen`}
      className="absolute left-0 top-8 z-20 w-72 max-w-[calc(100vw-2rem)] rounded-md border
                 border-line bg-surface shadow-pop"
    >
      {candidates.length > 0 && (
        <>
          <div className="flex items-baseline justify-between border-b border-line px-3 py-2">
            <span className="text-sm font-medium">{label}</span>
            <span className="text-2xs text-ink-faint">
              nach {axis === "SIDE" ? "g KH" : "g Protein"} im Gericht
            </span>
          </div>
          <ul className="py-1">
            {candidates.map((candidate) => {
              const selected = sameName(candidate.category, value);
              const disabled = candidate.is_side;
              return (
                <li key={candidate.article_id}>
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onChoose(candidate.category)}
                    className={[
                      "grid w-full grid-cols-[12px_minmax(0,1fr)_auto] items-center gap-2 px-3",
                      "py-1.5 text-left text-sm",
                      selected ? "bg-accent-soft" : "hover:bg-sunken",
                      disabled ? "cursor-not-allowed text-ink-faint hover:bg-transparent" : "",
                    ].join(" ")}
                  >
                    <span
                      className={[
                        "h-3 w-3 rounded-full border",
                        selected ? "border-[4px] border-accent" : "border-line-strong",
                      ].join(" ")}
                    />
                    <span className="min-w-0">
                      <span className="block truncate">{candidate.category}</span>
                      <span className="block truncate text-2xs text-ink-faint">
                        {candidate.is_side
                          ? "ist schon Beilage"
                          : candidate.known
                            ? `aus ${candidate.article_name}`
                            : `${candidate.article_name} · neue Zuordnung`}
                      </span>
                    </span>
                    <span className="text-xs tabular-nums text-ink-muted">
                      {Number(candidate.grams) > 0 ? `${formatNumber(candidate.grams)} g` : "–"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}
      <div className="flex flex-col gap-1.5 border-t border-line px-3 py-2 first:border-t-0">
        <span className="text-2xs text-ink-faint">Andere Kategorie</span>
        <div className="flex flex-wrap gap-1">
          {others.slice(0, 12).map((category) => (
            <button
              key={category.id}
              type="button"
              onClick={() => onChoose(category.name)}
              className={
                sameName(category.name, value)
                  ? "chip chip-accent"
                  : "chip hover:border-line-strong hover:text-ink"
              }
            >
              {category.name}
            </button>
          ))}
        </div>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              if (draft.trim()) onChoose(draft.trim());
            }
          }}
          placeholder="neu … (Enter)"
          aria-label={`Neue ${label}`}
          className="field py-1 text-xs"
        />
        <button
          type="button"
          onClick={() => onChoose(null)}
          className="self-start text-xs text-ink-muted underline underline-offset-2
                     hover:text-ink"
        >
          {axis === "SIDE" ? "keine Beilage" : "kein Protein"}
        </button>
      </div>
    </div>
  );
}
