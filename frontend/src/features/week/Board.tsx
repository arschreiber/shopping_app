/**
 * Das Wochenboard: 7 Tage x 2 Mahlzeiten.
 *
 * Laptop: Spalten pro Tag, Drag & Drop zum Tauschen zweier Slots (general_plan.md §8 Nr. 6).
 * Handy: eine Karte pro Tag untereinander, Antippen öffnet das Kandidaten-Sheet.
 */
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import type { Meal, Slot, Warning, Week } from "../../api/client";
import { DAY_SHORT, formatDay, isToday } from "../../lib/dates";
import { MEAL_LABEL } from "../../lib/format";
import { SlotCard } from "./SlotCard";

export function Board({
  week,
  iso,
  onOpen,
  onPin,
  onReroll,
  onSwap,
}: {
  week: Week;
  iso: string;
  onOpen: (slot: Slot) => void;
  onPin: (slot: Slot, pinned: boolean) => void;
  onReroll: (slot: Slot) => void;
  onSwap: (from: { day: number; meal: Meal }, to: { day: number; meal: Meal }) => void;
}) {
  const sensors = useSensors(
    // 6px Schwelle: sonst wird jeder Tipp am Handy als Drag gewertet.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const byKey = new Map(week.slots.map((slot) => [`${slot.day}-${slot.meal}`, slot]));
  const meals: Meal[] = ["LUNCH", "DINNER"];

  // Warnungen einmal pro Slot bündeln, statt sie in jeder Karte zu filtern.
  const warningsBySlot = new Map<string, Warning[]>();
  for (const warning of week.warnings) {
    if (typeof warning.day !== "number" || !warning.meal) continue;
    const key = `${warning.day}-${warning.meal}`;
    warningsBySlot.set(key, [...(warningsBySlot.get(key) ?? []), warning]);
  }

  function handleDragEnd(event: DragEndEvent) {
    const from = event.active.data.current as { day: number; meal: Meal } | undefined;
    const to = event.over?.data.current as { day: number; meal: Meal } | undefined;
    if (!from || !to) return;
    if (from.day === to.day && from.meal === to.meal) return;
    onSwap(from, to);
  }

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      {/* Laptop: echtes Raster mit Tagesspalten */}
      <div className="hidden lg:block">
        <div className="grid grid-cols-[4.5rem_repeat(7,minmax(0,1fr))] gap-x-2">
          <div />
          {DAY_SHORT.map((name, day) => (
            <div
              key={day}
              className={[
                "flex items-baseline gap-1.5 border-b px-1 pb-1.5",
                isToday(iso, day) ? "border-accent" : "border-line",
              ].join(" ")}
            >
              <span
                className={[
                  "text-2xs font-semibold uppercase tracking-wider",
                  isToday(iso, day) ? "text-accent" : "text-ink-faint",
                ].join(" ")}
              >
                {name}
              </span>
              <span className="text-2xs text-ink-faint">{formatDay(iso, day)}</span>
            </div>
          ))}

          {meals.map((meal) => (
            <div key={meal} className="col-span-8 grid grid-cols-subgrid gap-x-2 py-1.5">
              <div className="flex items-center justify-end pr-1">
                <span className="label">{MEAL_LABEL[meal]}</span>
              </div>
              {DAY_SHORT.map((_, day) => {
                const slot = byKey.get(`${day}-${meal}`);
                if (!slot) return <div key={day} />;
                return (
                  <SlotCard
                    key={day}
                    slot={slot}
                    iso={iso}
                    warnings={warningsBySlot.get(`${day}-${meal}`) ?? []}
                    dragEnabled
                    onOpen={() => onOpen(slot)}
                    onPin={(pinned) => onPin(slot, pinned)}
                    onReroll={() => onReroll(slot)}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Handy und Tablet: pro Tag ein Block, Mittag und Abend nebeneinander */}
      <div className="flex flex-col gap-3 lg:hidden">
        {DAY_SHORT.map((name, day) => (
          <section key={day}>
            <div
              className={[
                "mb-1.5 flex items-baseline gap-2 border-b pb-1",
                isToday(iso, day) ? "border-accent" : "border-line",
              ].join(" ")}
            >
              <h3
                className={[
                  "text-sm font-semibold",
                  isToday(iso, day) ? "text-accent" : "text-ink",
                ].join(" ")}
              >
                {name}
              </h3>
              <span className="text-xs text-ink-faint">{formatDay(iso, day)}</span>
              {isToday(iso, day) && <span className="chip chip-accent ml-auto">heute</span>}
            </div>
            <div className="grid grid-cols-2 gap-2">
              {meals.map((meal) => {
                const slot = byKey.get(`${day}-${meal}`);
                if (!slot) return <div key={meal} />;
                return (
                  <div key={meal}>
                    <span className="label mb-1 block">{MEAL_LABEL[meal]}</span>
                    <SlotCard
                      slot={slot}
                      iso={iso}
                      warnings={warningsBySlot.get(`${day}-${meal}`) ?? []}
                      dragEnabled={false}
                      onOpen={() => onOpen(slot)}
                      onPin={(pinned) => onPin(slot, pinned)}
                      onReroll={() => onReroll(slot)}
                    />
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </DndContext>
  );
}
