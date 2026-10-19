/**
 * Vorlagen und Wegfall-Hinweis des Rasters. Der Hinweis muss dieselbe Regel treffen wie
 * das Backend beim Speichern - sonst warnt er vor dem Falschen oder schweigt.
 */
import { describe, expect, it } from "vitest";
import type { Slot, SlotIn, Week } from "../api/client";
import {
  applyPreset,
  describeCell,
  droppedOnSave,
  dropsIfNobody,
  isDayOff,
  presetOf,
} from "./grid";

function cell(day: number, meal: "LUNCH" | "DINNER", over: Partial<SlotIn> = {}): SlotIn {
  return {
    day,
    meal,
    eaters_home: 2,
    packed_portions: 0,
    packed_fresh: false,
    time_budget: "NORMAL",
    special: "NONE",
    pinned: false,
    ...over,
  };
}

function week(slots: Partial<Slot>[]): Week {
  return { slots } as Week;
}

describe("Vorlagen", () => {
  it("erkennt die vier üblichen Einstellungen und sonst keine", () => {
    expect(presetOf(cell(0, "LUNCH"))).toBe("two");
    expect(presetOf(cell(0, "LUNCH", { eaters_home: 0 }))).toBe("nobody");
    expect(presetOf(cell(0, "LUNCH", { eaters_home: 1, packed_portions: 1 }))).toBe("packed");
    expect(presetOf(cell(0, "LUNCH", { eaters_home: 2, packed_portions: 1 }))).toBeNull();
  });

  it("mitnehmen startet frisch, behält aber ein schon gewähltes vorgekocht", () => {
    expect(applyPreset(cell(1, "DINNER"), "packed").packed_fresh).toBe(true);
    const prepared = cell(1, "DINNER", { eaters_home: 2, packed_portions: 1, packed_fresh: false });
    expect(applyPreset(prepared, "packed").packed_fresh).toBe(false);
  });

  it("ohne Mitnehm-Portion bleibt kein verstecktes frisch stehen", () => {
    const fresh = cell(1, "DINNER", { eaters_home: 1, packed_portions: 1, packed_fresh: true });
    expect(applyPreset(fresh, "two")).toMatchObject({ packed_portions: 0, packed_fresh: false });
  });

  it("beschreibt die Zelle so, wie man sie liest", () => {
    expect(describeCell(cell(0, "LUNCH", { eaters_home: 0 })).main).toBe("niemand da");
    expect(
      describeCell(cell(1, "DINNER", { eaters_home: 1, packed_portions: 1, packed_fresh: true })),
    ).toEqual({ main: "1 zu Hause", extra: "+ 1 mitnehmen, frisch" });
    expect(describeCell(cell(2, "LUNCH", { eaters_home: 0, packed_portions: 2 }))).toEqual({
      main: "nur mitnehmen",
      extra: "2 Portionen, vorgekocht",
    });
  });

  it("ein Tag ist frei, wenn beide Mahlzeiten niemand da sind", () => {
    const cells = [cell(5, "LUNCH", { eaters_home: 0 }), cell(5, "DINNER", { eaters_home: 0 })];
    expect(isDayOff(cells, 5)).toBe(true);
    expect(isDayOff([cells[0], cell(5, "DINNER")], 5)).toBe(false);
  });
});

describe("Wegfall beim Speichern", () => {
  // Mo Abend Lasagne doppelt, Di Mittag die Reste davon, Mi Mittag Chili.
  const plan = week([
    { day: 0, meal: "DINNER", assignment: { kind: "DISH", dish_name: "Lasagne" } as Slot["assignment"] },
    {
      day: 1,
      meal: "LUNCH",
      assignment: {
        kind: "LEFTOVER",
        dish_name: "Lasagne",
        leftover_source_day: 0,
        leftover_source_meal: "DINNER",
      } as Slot["assignment"],
    },
    { day: 2, meal: "LUNCH", assignment: { kind: "DISH", dish_name: "Chili" } as Slot["assignment"] },
  ]);

  it("nimmt das Gericht und die Reste davon mit", () => {
    const draft = [cell(0, "DINNER", { eaters_home: 0 }), cell(1, "LUNCH"), cell(2, "LUNCH")];
    expect([...droppedOnSave(plan, draft)].sort()).toEqual(["0-DINNER", "1-LUNCH"]);
  });

  it("lässt alles stehen, solange noch jemand isst", () => {
    const draft = [cell(0, "DINNER", { eaters_home: 1 }), cell(1, "LUNCH"), cell(2, "LUNCH")];
    expect(droppedOnSave(plan, draft).size).toBe(0);
  });

  it("sagt vorher, was wegfiele", () => {
    expect(dropsIfNobody(plan, 0, "DINNER")).toEqual(["Lasagne", "die Reste am Di Mittag"]);
    expect(dropsIfNobody(plan, 2, "LUNCH")).toEqual(["Chili"]);
    expect(dropsIfNobody(plan, 3, "LUNCH")).toEqual([]);
  });
});
