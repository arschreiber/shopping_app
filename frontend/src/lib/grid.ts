/**
 * Das Wochenraster als Auswahl statt als Schalterwand. In fünf Wochen echter Nutzung
 * kamen vier Einstellungen vor: 2 zu Hause, 1 zu Hause, niemand da, 1 + 1 mitnehmen.
 * Die stehen als Vorlagen im Menü einer Zelle, alles Seltenere unter "Anpassen".
 */
import type { Meal, SlotIn, Week } from "../api/client";
import { DAY_SHORT } from "./dates";
import { MEAL_LABEL } from "./format";

/** Was eine Rasterzelle einstellt - Wochenraster und Standardwoche teilen sich das. */
export type GridCell = Pick<
  SlotIn,
  "eaters_home" | "packed_portions" | "packed_fresh" | "time_budget"
>;

export type PresetKey = "two" | "one" | "nobody" | "packed";

export const PRESETS: { key: PresetKey; label: string; eaters: number; packed: number }[] = [
  { key: "two", label: "2 zu Hause", eaters: 2, packed: 0 },
  { key: "one", label: "1 zu Hause", eaters: 1, packed: 0 },
  { key: "nobody", label: "niemand da", eaters: 0, packed: 0 },
  { key: "packed", label: "1 zu Hause + 1 mitnehmen", eaters: 1, packed: 1 },
];

export function isNobody(cell: Pick<GridCell, "eaters_home" | "packed_portions">): boolean {
  return cell.eaters_home === 0 && cell.packed_portions === 0;
}

/** Welche Vorlage eine Zelle gerade hat - `null` heißt: etwas Eigenes, "Anpassen". */
export function presetOf(cell: GridCell): PresetKey | null {
  const match = PRESETS.find(
    (preset) => preset.eaters === cell.eaters_home && preset.packed === cell.packed_portions,
  );
  return match?.key ?? null;
}

/**
 * Die Änderung, die eine Vorlage auslöst. Mitnehmen startet "frisch" - so wird es
 * genutzt; wer schon eine Mitnehm-Portion hatte, behält, woher sie kommt.
 */
export function applyPreset(cell: GridCell, key: PresetKey): Partial<SlotIn> {
  const preset = PRESETS.find((candidate) => candidate.key === key)!;
  const changes: Partial<SlotIn> = {
    eaters_home: preset.eaters,
    packed_portions: preset.packed,
    packed_fresh: preset.packed > 0 && (cell.packed_portions > 0 ? cell.packed_fresh : true),
  };
  // "auswärts" ist nur noch "niemand da" - kein Sonderfall, der daneben weiterlebt.
  if (key === "nobody") changes.special = "NONE";
  return changes;
}

/** Was in der Zelle steht: eine Zeile, wer isst, und eine fürs Mitnehmen. */
export function describeCell(cell: GridCell): { main: string; extra: string | null } {
  if (isNobody(cell)) return { main: "niemand da", extra: null };
  if (cell.packed_portions === 0) return { main: `${cell.eaters_home} zu Hause`, extra: null };
  const origin = cell.packed_fresh ? "frisch" : "vorgekocht";
  if (cell.eaters_home === 0) {
    const portions = cell.packed_portions === 1 ? "1 Portion" : `${cell.packed_portions} Portionen`;
    return { main: "nur mitnehmen", extra: `${portions}, ${origin}` };
  }
  return {
    main: `${cell.eaters_home} zu Hause`,
    extra: `+ ${cell.packed_portions} mitnehmen, ${origin}`,
  };
}

const keyOf = (day: number, meal: Meal) => `${day}-${meal}`;

/**
 * Welche Gerichte beim Speichern wegfallen - dieselbe Regel wie `weeks.update_grid`: wo
 * niemand mehr isst, und Reste, deren Quelle dabei wegfällt. Schlüssel `Tag-Mahlzeit`.
 */
export function droppedOnSave(week: Week, draft: SlotIn[]): Set<string> {
  const nobody = new Set(draft.filter(isNobody).map((slot) => keyOf(slot.day, slot.meal)));
  const cleared = new Set(
    week.slots
      .filter((slot) => slot.assignment && nobody.has(keyOf(slot.day, slot.meal)))
      .map((slot) => keyOf(slot.day, slot.meal)),
  );
  const dropped = new Set(cleared);
  for (const slot of week.slots) {
    const assignment = slot.assignment;
    if (
      assignment?.kind === "LEFTOVER" &&
      typeof assignment.leftover_source_day === "number" &&
      assignment.leftover_source_meal &&
      cleared.has(keyOf(assignment.leftover_source_day, assignment.leftover_source_meal))
    ) {
      dropped.add(keyOf(slot.day, slot.meal));
    }
  }
  return dropped;
}

/** Was wegfiele, wenn hier niemand mehr isst: das Gericht selbst und Reste davon. */
export function dropsIfNobody(week: Week, day: number, meal: Meal): string[] {
  const own = week.slots.find((slot) => slot.day === day && slot.meal === meal)?.assignment;
  if (!own) return [];
  const names = [own.dish_name ?? "das Gericht"];
  for (const slot of week.slots) {
    const assignment = slot.assignment;
    if (
      assignment?.kind === "LEFTOVER" &&
      assignment.leftover_source_day === day &&
      assignment.leftover_source_meal === meal
    ) {
      names.push(`die Reste am ${DAY_SHORT[slot.day]} ${MEAL_LABEL[slot.meal]}`);
    }
  }
  return names;
}

/** Ganzer Tag frei: beide Mahlzeiten "niemand da". */
export function isDayOff(cells: SlotIn[], day: number): boolean {
  const ofDay = cells.filter((slot) => slot.day === day);
  return ofDay.length > 0 && ofDay.every(isNobody);
}
