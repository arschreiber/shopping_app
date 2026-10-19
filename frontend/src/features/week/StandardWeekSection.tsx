/**
 * Standardwoche: das Raster, mit dem jede neue Woche anfängt. Vorher startete jede Woche
 * mit "überall 2 zu Hause", und das freie Wochenende musste jedes Mal neu geklickt werden.
 * Schon angelegte Wochen ändert das nicht - für Ausnahmen gibt es "wie letzte Woche".
 *
 * Gespeichert wird über die Speichern-Leiste der Einstellungen, nicht hier: ein Knopf für
 * die ganze Seite, und er steht unten, wo man nach dem Wochenende gerade ist.
 */
import type { Meal, SlotIn, StandardSlot } from "../../api/client";
import { SectionTitle, Spinner } from "../../components/Primitives";
import { errorText } from "../../components/Toast";
import { DayOffButton, SlotSettings } from "./SlotSettings";
import { WeekGrid } from "./WeekGrid";

// Die Zellen arbeiten auf SlotIn wie im Wochenraster; Pins und Sonderfälle gibt es in der
// Standardwoche nicht.
export function toCells(standard: StandardSlot[]): SlotIn[] {
  return standard.map((slot) => ({ ...slot, special: "NONE", pinned: false }));
}

export function toStandard(cells: SlotIn[]): StandardSlot[] {
  return cells.map(({ day, meal, eaters_home, packed_portions, packed_fresh, time_budget }) => ({
    day,
    meal,
    eaters_home,
    packed_portions,
    packed_fresh: packed_fresh ?? false,
    time_budget,
  }));
}

export function StandardWeekSection({
  cells,
  error,
  onChange,
}: {
  cells: SlotIn[] | null;
  error?: unknown;
  onChange: (day: number, meal: Meal, changes: Partial<SlotIn>) => void;
}) {
  return (
    <section className="card p-4">
      <SectionTitle>Standardwoche</SectionTitle>
      <p className="mb-3 text-sm text-ink-muted">
        Mit diesem Raster startet jede neue Woche. Schon angelegte Wochen bleiben, wie sie
        sind.
      </p>
      {cells ? (
        <WeekGrid
          wide="rows"
          renderCell={(day, meal) => {
            const cell = cells.find((slot) => slot.day === day && slot.meal === meal);
            return cell ? (
              <SlotSettings
                slot={cell}
                dense
                onChange={(changes) => onChange(day, meal, changes)}
              />
            ) : null;
          }}
          dayAction={(day) => (
            <DayOffButton
              cells={cells}
              day={day}
              onChange={(meal, changes) => onChange(day, meal, changes)}
            />
          )}
        />
      ) : error ? (
        <p className="text-sm text-danger">{errorText(error)}</p>
      ) : (
        <Spinner />
      )}
    </section>
  );
}
