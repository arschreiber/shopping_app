/**
 * Vitamine und Mineralstoffe vom Etikett. Sie gelten je Nährstoff vor dem BLS - für
 * Produkte, die der BLS nicht kennt (Proteinpulver) oder die angereichert sind.
 *
 * Gespeichert wird mit dem Artikel ("Speichern" darunter), wie die Makros. Leere Felder
 * heißen "steht nicht drauf" - dann zählt der BLS-Wert, falls es einen gibt.
 */
import { useState } from "react";
import { useMicroFields } from "../../api/hooks";

export function LabelMicros({
  values,
  onChange,
  basis,
}: {
  values: Record<string, string>;
  onChange: (next: Record<string, string>) => void;
  basis: string;
}) {
  const fields = useMicroFields();
  const filled = Object.values(values).filter((value) => String(value).trim() !== "").length;
  const [open, setOpen] = useState(filled > 0);
  const groups = [...new Set((fields.data ?? []).map((field) => field.group))];

  return (
    <fieldset className="rounded border border-line bg-sunken/40 px-2.5 py-2">
      <legend className="label px-1">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="uppercase"
        >
          Mikros vom Etikett {basis} {open ? "▾" : "▸"}
        </button>{" "}
        <span className="font-normal normal-case tracking-normal text-ink-faint">
          (optional – gilt vor dem BLS{filled > 0 ? `, ${filled} erfasst` : ""})
        </span>
      </legend>

      {open && (
        <div className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
          {groups.map((group) => (
            <div key={group} className="flex flex-col gap-1">
              <span className="text-2xs font-medium uppercase tracking-wide text-ink-faint">
                {group}
              </span>
              {(fields.data ?? [])
                .filter((field) => field.group === group)
                .map((field) => (
                  <label key={field.code} className="grid grid-cols-[1fr_5rem_2rem] items-center gap-1.5">
                    <span
                      className="truncate text-xs text-ink-muted"
                      title={
                        field.code === "FOLAC"
                          ? "Synthetische Folsäure, wie auf Etiketten – zählt 1,7-fach als Folat"
                          : undefined
                      }
                    >
                      {field.label}
                    </span>
                    <input
                      type="number"
                      min={0}
                      step="any"
                      inputMode="decimal"
                      value={values[field.code] ?? ""}
                      onChange={(event) =>
                        onChange({ ...values, [field.code]: event.target.value })
                      }
                      className="field py-0.5 text-right"
                      aria-label={`${field.label} ${basis} in ${field.unit}`}
                    />
                    <span className="text-2xs text-ink-faint">{field.unit}</span>
                  </label>
                ))}
            </div>
          ))}
        </div>
      )}
    </fieldset>
  );
}

/** Für den Request: Komma zu Punkt, leere Felder raus, ganz leer heißt `null`. */
export function labelMicrosBody(values: Record<string, string>): Record<string, string> | null {
  const entries = Object.entries(values)
    .map(([code, value]) => [code, String(value).trim().replace(",", ".")] as const)
    .filter(([, value]) => value !== "");
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}
