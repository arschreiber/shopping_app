/**
 * Das Wochenraster (general_plan.md §5 Phase 1): wer isst wann zu Hause, was wird
 * mitgenommen, wie viel Zeit ist da. Ziel laut Plan: in 30 Sekunden ausgefüllt.
 *
 * Darum: eine Zeile pro Slot, alles per Klick, kein Speichern-Dialog. Gespeichert wird
 * beim Schließen - mit `version` gegen den Konflikt Laptop/Handy.
 */
import { useEffect, useState } from "react";
import type { SlotIn, SlotSpecial, TimeBudget, Week } from "../../api/client";
import { Segmented, Stepper } from "../../components/Primitives";
import { DAY_SHORT, formatDay } from "../../lib/dates";
import { MEAL_LABEL, SPECIAL_LABEL, TIME_SHORT } from "../../lib/format";

const TIME_OPTIONS: { value: TimeBudget; label: string; title: string }[] = [
  { value: "PLENTY", label: TIME_SHORT.PLENTY, title: "viel Zeit - jeder Aufwand" },
  { value: "LITTLE", label: TIME_SHORT.LITTLE, title: "wenig Zeit - nur schnelle Gerichte" },
  { value: "NONE", label: TIME_SHORT.NONE, title: "keine Zeit - nur Reste oder Vorhandenes" },
];

const SPECIAL_OPTIONS: { value: SlotSpecial; label: string; title: string }[] = [
  { value: "NONE", label: "normal", title: "normal geplant" },
  { value: "EATING_OUT", label: "auswärts", title: "auswärts - nichts zu planen" },
  {
    value: "FROM_PANTRY",
    label: "Vorrat",
    title: "aus Vorhandenem - Zutaten kommen nicht auf die Einkaufsliste",
  },
];

export function toSlotInputs(week: Week): SlotIn[] {
  return week.slots.map((slot) => ({
    day: slot.day,
    meal: slot.meal,
    eaters_home: slot.eaters_home,
    packed_portions: slot.packed_portions,
    time_budget: slot.time_budget,
    special: slot.special,
    pinned: slot.pinned,
  }));
}

export function GridEditor({
  week,
  iso,
  onSave,
  saving,
}: {
  week: Week;
  iso: string;
  onSave: (slots: SlotIn[], version: number) => void;
  saving: boolean;
}) {
  const [draft, setDraft] = useState<SlotIn[]>(() => toSlotInputs(week));

  // Fremde Änderungen (anderes Gerät) übernehmen, solange nichts Eigenes offen ist.
  useEffect(() => setDraft(toSlotInputs(week)), [week.version, week.iso]);

  const dirty = JSON.stringify(draft) !== JSON.stringify(toSlotInputs(week));

  function patch(index: number, changes: Partial<SlotIn>) {
    setDraft((current) =>
      current.map((slot, position) => (position === index ? { ...slot, ...changes } : slot)),
    );
  }

  return (
    <div className="flex flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line
                      bg-sunken/50 px-4 py-2">
        <p className="text-xs text-ink-muted">
          <span className="font-medium text-ink">Mitnehmen</span> heißt: hier wird
          mitgekocht und am Folgetag mitgenommen.
        </p>
        <button
          type="button"
          disabled={!dirty || saving}
          onClick={() => onSave(draft, week.version)}
          className="btn-primary btn-sm"
        >
          {saving ? "speichert …" : dirty ? "Raster speichern" : "gespeichert"}
        </button>
      </div>

      <div className="divide-y divide-line">
        {draft.map((slot, index) => {
          const isLunch = slot.meal === "LUNCH";
          const disabled = slot.special === "EATING_OUT";
          return (
            <div
              key={`${slot.day}-${slot.meal}`}
              className={[
                "flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2",
                isLunch ? "" : "bg-sunken/30",
              ].join(" ")}
            >
              <div className="w-28 shrink-0">
                <span className="text-sm font-medium">
                  {DAY_SHORT[slot.day]} {formatDay(iso, slot.day)}
                </span>
                <span className="ml-1.5 text-xs text-ink-faint">{MEAL_LABEL[slot.meal]}</span>
              </div>

              <label className="flex items-center gap-1.5">
                <span className="label">zu Hause</span>
                <Stepper
                  value={slot.eaters_home}
                  onChange={(value) => patch(index, { eaters_home: value })}
                  label="Esser zu Hause"
                />
              </label>

              <label className="flex items-center gap-1.5">
                <span className="label">mitnehmen</span>
                <Stepper
                  value={slot.packed_portions}
                  onChange={(value) => patch(index, { packed_portions: value })}
                  label="Mitnehm-Portionen"
                />
              </label>

              <div className={disabled ? "pointer-events-none opacity-40" : ""}>
                <Segmented
                  size="sm"
                  label="Zeitbudget"
                  value={slot.time_budget}
                  options={TIME_OPTIONS}
                  onChange={(value) => patch(index, { time_budget: value })}
                />
              </div>

              <div className="ml-auto">
                <Segmented
                  size="sm"
                  label="Sonderfall"
                  value={slot.special}
                  options={SPECIAL_OPTIONS}
                  onChange={(value) =>
                    patch(index, {
                      special: value,
                      ...(value === "EATING_OUT"
                        ? { eaters_home: 0, packed_portions: 0 }
                        : {}),
                    })
                  }
                />
              </div>

              {slot.special !== "NONE" && (
                <span className="w-full text-2xs text-ink-faint sm:w-auto">
                  {slot.special === "FROM_PANTRY"
                    ? "Zutaten dieses Slots kommen nicht auf die Einkaufsliste"
                    : SPECIAL_LABEL[slot.special]}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
