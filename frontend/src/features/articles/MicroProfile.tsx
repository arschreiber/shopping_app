/**
 * Was ein Artikel je 100 g / 100 ml / Stück an Vitaminen und Mineralstoffen trägt -
 * nur lesend, gerechnet auf dem Server nach "Etikett vor BLS". Das kleine "E" sagt, dass
 * der Wert vom Etikett kommt; ohne Markierung stammt er aus dem BLS.
 *
 * Zeigt den gespeicherten Stand: Etikettwerte erscheinen hier nach "Speichern".
 */
import { useState } from "react";
import type { Article } from "../../api/client";
import { useMicroFields } from "../../api/hooks";
import { MicroBar } from "../nutrition/MicroBar";

export function MicroProfile({ article, basis }: { article: Article; basis: string }) {
  const fields = useMicroFields();
  const [open, setOpen] = useState(false);
  const micros = article.micros ?? [];
  if (micros.length === 0 || !fields.data) return null;
  const fromLabel = micros.filter((value) => value.source === "label").length;

  const byCode = new Map(micros.map((value) => [value.code, value]));
  const shown = fields.data.filter((field) => field.code !== "FOLAC");
  const groups = [...new Set(shown.map((field) => field.group))];

  return (
    <div className="mt-2 border-t border-line pt-1.5">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-baseline gap-2 text-left"
      >
        <span className="label">Nährstoffprofil {basis}</span>
        <span className="text-2xs text-ink-faint">
          {micros.length} Werte
          {fromLabel > 0 ? `, ${fromLabel} vom Etikett (E)` : " aus dem BLS"}
          {open ? " · Balken: % vom Tageswert" : ""}
        </span>
        <span className="ml-auto text-xs text-ink-muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
      <div className="mt-2 grid gap-x-6 gap-y-3 sm:grid-cols-3">
        {groups.map((group) => (
          <dl key={group} className="flex flex-col gap-1">
            <dt className="text-2xs font-medium uppercase tracking-wide text-ink-faint">
              {group}
            </dt>
            {shown
              .filter((field) => field.group === group)
              .map((field) => {
                const value = byCode.get(field.code);
                if (!value) {
                  return (
                    <dd key={field.code} className="flex items-baseline gap-2 text-xs">
                      <span className="min-w-0 flex-1 truncate text-ink-muted">{field.label}</span>
                      <span className="text-2xs text-ink-faint">unbekannt</span>
                    </dd>
                  );
                }
                return (
                  <MicroBar
                    key={field.code}
                    label={field.label}
                    unit={field.unit}
                    amount={value.amount}
                    share={value.share}
                    kind={field.kind}
                    badge={value.source === "label" ? "E" : ""}
                    badgeTitle={value.source === "label" ? "vom Etikett" : "aus dem BLS"}
                  />
                );
              })}
          </dl>
        ))}
      </div>
      )}
    </div>
  );
}
