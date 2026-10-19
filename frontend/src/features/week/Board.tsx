/**
 * Das Wochenboard: 7 Tage x 2 Mahlzeiten.
 *
 * Laptop: Spalten pro Tag, Drag & Drop zum Tauschen zweier Slots (general_plan.md §8 Nr. 6).
 * Handy: eine Karte pro Tag untereinander, Antippen öffnet das Kandidaten-Sheet.
 *
 * Mit `editing` zeigen dieselben Zellen die Raster-Einstellungen der jeweiligen Mahlzeit -
 * das Raster hat keine eigene Tabelle, es *ist* diese hier. Das geplante Gericht bleibt
 * klein darunter stehen, damit "niemand da" es nicht unbemerkt vom Plan nimmt.
 */
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import type { ReactNode } from "react";
import type { Meal, Slot, SlotIn, Warning, Week } from "../../api/client";
import { droppedOnSave, dropsIfNobody } from "../../lib/grid";
import { SlotCard } from "./SlotCard";
import { DayOffButton, SlotSettings } from "./SlotSettings";
import { WeekGrid } from "./WeekGrid";

export type BoardEditing = {
  draft: SlotIn[];
  onChange: (day: number, meal: Meal, changes: Partial<SlotIn>) => void;
};

export function Board({
  week,
  iso,
  onOpen,
  onPin,
  onReroll,
  onClear,
  onSwap,
  editing,
}: {
  week: Week;
  iso: string;
  onOpen: (slot: Slot) => void;
  onPin: (slot: Slot, pinned: boolean) => void;
  onReroll: (slot: Slot) => void;
  onClear: (slot: Slot) => void;
  onSwap: (from: { day: number; meal: Meal }, to: { day: number; meal: Meal }) => void;
  /** Gesetzt = Raster bearbeiten: Einstellungen statt Gerichte in den Zellen. */
  editing?: BoardEditing;
}) {
  const sensors = useSensors(
    // 6px Schwelle: sonst wird jeder Tipp am Handy als Drag gewertet.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
  );

  const byKey = new Map(week.slots.map((slot) => [`${slot.day}-${slot.meal}`, slot]));

  // Warnungen einmal pro Slot bündeln, statt sie in jeder Karte zu filtern.
  const warningsBySlot = new Map<string, Warning[]>();
  for (const warning of week.warnings) {
    if (typeof warning.day !== "number" || !warning.meal) continue;
    const key = `${warning.day}-${warning.meal}`;
    warningsBySlot.set(key, [...(warningsBySlot.get(key) ?? []), warning]);
  }

  // Beim Bearbeiten: was das Speichern vom Plan nehmen würde.
  const dropped = editing ? droppedOnSave(week, editing.draft) : new Set<string>();

  /** Eine Zelle des Boards - Gericht oder, beim Bearbeiten, die Einstellungen dazu. */
  function cell(day: number, meal: Meal, dragEnabled: boolean): ReactNode {
    const slot = byKey.get(`${day}-${meal}`);
    if (editing) {
      const settings = editing.draft.find((draft) => draft.day === day && draft.meal === meal);
      if (!settings) return <div />;
      return (
        <SlotSettings
          slot={settings}
          dish={slot?.assignment?.dish_name}
          dropped={dropped.has(`${day}-${meal}`)}
          dropsIfNobody={dropsIfNobody(week, day, meal)}
          onChange={(changes) => editing.onChange(day, meal, changes)}
        />
      );
    }
    if (!slot) return <div />;
    return (
      <SlotCard
        slot={slot}
        iso={iso}
        warnings={warningsBySlot.get(`${day}-${meal}`) ?? []}
        dragEnabled={dragEnabled}
        onOpen={() => onOpen(slot)}
        onPin={(pinned) => onPin(slot, pinned)}
        onReroll={() => onReroll(slot)}
        onClear={() => onClear(slot)}
      />
    );
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
      <WeekGrid
        iso={iso}
        renderCell={cell}
        dayAction={
          editing
            ? (day) => (
                <DayOffButton
                  cells={editing.draft}
                  day={day}
                  onChange={(meal, changes) => editing.onChange(day, meal, changes)}
                />
              )
            : undefined
        }
      />
    </DndContext>
  );
}
