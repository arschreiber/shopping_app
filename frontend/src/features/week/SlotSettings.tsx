/**
 * Raster-Einstellungen *einer* Mahlzeit (general_plan.md §5 Phase 1: wer isst wann zu
 * Hause, was wird mitgenommen - in 30 Sekunden ausgefüllt).
 *
 * Die Zelle zeigt nur, was eingestellt ist; Antippen öffnet ein kleines Menü mit den
 * üblichen Vorlagen (lib/grid.ts). Vorher standen in jeder der 14 Zellen drei bis vier
 * Umschalter - eine Wand aus Knöpfen für Entscheidungen, die selten anders ausfallen.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { Meal, SlotIn, Week } from "../../api/client";
import { IconCheck } from "../../components/Icons";
import { Segmented } from "../../components/Primitives";
import { DAY_SHORT } from "../../lib/dates";
import { MEAL_LABEL, TIME_HINT, TIME_LABEL, TIME_SHORT } from "../../lib/format";
import {
  PRESETS,
  applyPreset,
  describeCell,
  isDayOff,
  isNobody,
  presetOf,
  type PresetKey,
} from "../../lib/grid";
import { TimeMark } from "./TimeMark";

const COUNTS = ["0", "1", "2"].map((value) => ({ value, label: value }));

const TIME_OPTIONS = (["NORMAL", "LITTLE", "NONE"] as const).map((value) => ({
  value,
  label: TIME_SHORT[value],
  title: `${TIME_LABEL[value]} - ${TIME_HINT[value]}`,
}));

// Woher die Mitnehm-Portion kommt: frisch in dieser Mahlzeit mitgekocht - etwa fürs
// Abendessen, das zu einem Termin mitgeht - oder vorgekocht, bevorzugt aus Resten.
const ORIGIN_OPTIONS = [
  { value: "fresh", label: "frisch", title: "frisch - wird in dieser Mahlzeit mitgekocht" },
  { value: "prepared", label: "vorgekocht", title: "vorgekocht - gern aus Resten" },
];

const MENU_WIDTH = 256; // w-64

export function toSlotInputs(week: Week): SlotIn[] {
  return week.slots.map((slot) => ({
    day: slot.day,
    meal: slot.meal,
    eaters_home: slot.eaters_home,
    packed_portions: slot.packed_portions,
    packed_fresh: slot.packed_fresh,
    time_budget: slot.time_budget,
    special: slot.special,
    pinned: slot.pinned,
  }));
}

export function slotLabel(day: number, meal: Meal): string {
  return `${DAY_SHORT[day]} ${MEAL_LABEL[meal]}`;
}

export function SlotSettings({
  slot,
  onChange,
  dish,
  dropped = false,
  dropsIfNobody = [],
  dense = false,
}: {
  slot: SlotIn;
  onChange: (changes: Partial<SlotIn>) => void;
  /** Das geplante Gericht - beim Bearbeiten sichtbar, damit nichts unbemerkt wegfällt. */
  dish?: string | null;
  /** Fällt das Gericht beim Speichern weg? */
  dropped?: boolean;
  /** Was wegfiele, wenn hier "niemand da" gewählt wird - für den Hinweis im Menü. */
  dropsIfNobody?: string[];
  /** Ohne Gericht darunter (Standardwoche) reicht eine niedrigere Zelle. */
  dense?: boolean;
}) {
  const [menu, setMenu] = useState<"left" | "right" | null>(null);
  const anchor = useRef<HTMLButtonElement>(null);
  const where = slotLabel(slot.day, slot.meal);
  const nobody = isNobody(slot);
  const timed = slot.time_budget !== "NORMAL";
  const { main, extra } = describeCell(slot);

  function open() {
    // Rechts ist kein Platz mehr? Dann klappt das Menü nach links auf.
    const rect = anchor.current?.getBoundingClientRect();
    setMenu(rect && rect.left + MENU_WIDTH > window.innerWidth - 16 ? "right" : "left");
  }

  // Stabil, weil das Menü damit seinen Escape-Listener anmeldet - sonst würde es bei
  // jeder Änderung neu anmelden und den Fokus auf die erste Zeile zurückholen.
  const close = useCallback(() => {
    setMenu(null);
    anchor.current?.focus();
  }, []);

  return (
    <div className="relative">
      <button
        ref={anchor}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={menu !== null}
        aria-label={`${where}: ${main}${extra ? ` ${extra}` : ""}${
          timed ? `, ${TIME_LABEL[slot.time_budget]}` : ""
        }`}
        onClick={open}
        className={[
          "flex w-full flex-col items-start gap-0.5 rounded-md border px-2.5 py-2",
          // Im Board so hoch wie die Gericht-Karten, damit nichts springt beim Umschalten.
          dense ? "min-h-[3rem]" : "min-h-[4.5rem]",
          "text-left transition-colors duration-fast",
          // Eine Randfarbe pro Zustand - zwei border-Klassen nebeneinander entscheidet
          // die Reihenfolge im CSS, nicht die hier.
          menu ? "border-accent" : nobody ? "border-line-strong" : "border-line",
          nobody ? "hatch bg-sunken" : "bg-surface",
          "hover:border-accent-line",
        ].join(" ")}
      >
        <span className="flex w-full items-start gap-1">
          <span
            className={[
              "text-sm leading-snug",
              // Auf der Schraffur braucht die Schrift einen Grund, sonst flimmert sie - aber
              // nur so breit wie das Wort, nicht als Band über die ganze Zelle.
              nobody ? "mr-auto rounded bg-sunken px-1 -ml-1 text-ink-muted" : "flex-1 font-medium",
            ].join(" ")}
          >
            {main}
          </span>
          <TimeMark budget={slot.time_budget} className="mt-[3px]" />
        </span>
        {extra && <span className="text-2xs text-ink-muted">{extra}</span>}
        {dish && (
          <span
            className={[
              "mt-auto w-full text-2xs",
              dropped ? "rounded bg-warn-soft px-1 -ml-1 text-warn" : "line-clamp-1 text-ink-faint",
            ].join(" ")}
          >
            {dropped ? (
              <>
                <s>{dish}</s> fällt weg
              </>
            ) : (
              dish
            )}
          </span>
        )}
      </button>

      {menu && (
        <SlotMenu
          slot={slot}
          where={where}
          align={menu}
          dropsIfNobody={dropsIfNobody}
          onChange={onChange}
          onClose={close}
        />
      )}
    </div>
  );
}

function SlotMenu({
  slot,
  where,
  align,
  dropsIfNobody,
  onChange,
  onClose,
}: {
  slot: SlotIn;
  where: string;
  align: "left" | "right";
  dropsIfNobody: string[];
  onChange: (changes: Partial<SlotIn>) => void;
  onClose: () => void;
}) {
  const active = presetOf(slot);
  // Seltene Kombinationen (2 + 1, nur mitnehmen ...) gleich offen zeigen - sonst stünde
  // im Menü kein Haken, und man wüsste nicht, was gerade gilt.
  const [custom, setCustom] = useState(active === null);
  const first = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    first.current?.focus({ preventScroll: true });
    // Am Handy öffnet die letzte Zeile des Tages unten am Rand - dann ganz hineinrollen,
    // über der Navigationsleiste (scroll-mb).
    panel.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  function choose(key: PresetKey) {
    onChange(applyPreset(slot, key));
    // Mitnehmen bleibt offen: darunter erscheint frisch | vorgekocht.
    if (key !== "packed") onClose();
  }

  const origin = (
    <Segmented
      size="sm"
      block
      label={`Mitnehmen ${where}`}
      value={slot.packed_fresh ? "fresh" : "prepared"}
      options={ORIGIN_OPTIONS}
      onChange={(value) => onChange({ packed_fresh: value === "fresh" })}
    />
  );

  return (
    <>
      <button
        type="button"
        tabIndex={-1}
        aria-label="Menü schließen"
        onClick={onClose}
        className="fixed inset-0 z-30 cursor-default"
      />
      <div
        ref={panel}
        role="dialog"
        aria-label={`Raster ${where}`}
        className={[
          "absolute top-full z-40 mt-1 w-64 scroll-mb-20 rounded-lg border border-line bg-surface",
          "p-1 shadow-pop",
          align === "right" ? "right-0" : "left-0",
        ].join(" ")}
      >
        <p className="px-2.5 pb-1 pt-1.5 text-2xs text-ink-faint">{where}</p>

        {PRESETS.map((preset, index) => {
          const selected = active === preset.key;
          const warnDrop = preset.key === "nobody" && !selected && dropsIfNobody.length > 0;
          return (
            <div key={preset.key}>
              <button
                ref={index === 0 ? first : undefined}
                type="button"
                aria-pressed={selected}
                onClick={() => choose(preset.key)}
                className={[
                  "flex w-full items-center gap-2 rounded px-2.5 py-1.5 text-left text-sm",
                  "transition-colors duration-fast",
                  selected ? "bg-accent-soft font-medium text-accent" : "text-ink hover:bg-sunken",
                ].join(" ")}
              >
                <span className="flex-1">{preset.label}</span>
                {selected && <IconCheck className="h-3.5 w-3.5" />}
              </button>
              {warnDrop && (
                <p className="px-2.5 pb-1 text-2xs text-warn">
                  {joinNames(dropsIfNobody)} {dropsIfNobody.length > 1 ? "fallen" : "fällt"} dann
                  weg
                </p>
              )}
              {preset.key === "packed" && selected && (
                <div className="px-2.5 pb-1.5 pt-1">{origin}</div>
              )}
            </div>
          );
        })}

        <div className="my-1 border-t border-line" />

        <div className="flex flex-col gap-1 px-2.5 py-1.5">
          <span className="text-xs text-ink-muted">Zeit</span>
          <Segmented
            size="sm"
            block
            label={`Zeit ${where}`}
            value={slot.time_budget}
            options={TIME_OPTIONS}
            onChange={(time_budget) => onChange({ time_budget })}
          />
          {slot.time_budget !== "NORMAL" && (
            <span className="text-2xs text-ink-faint">{TIME_HINT[slot.time_budget]}</span>
          )}
        </div>

        <button
          type="button"
          aria-expanded={custom}
          onClick={() => setCustom((open) => !open)}
          className="w-full rounded px-2.5 py-1.5 text-left text-sm text-ink-muted transition-colors
                     duration-fast hover:bg-sunken hover:text-ink"
        >
          Anpassen …
        </button>
        {custom && (
          <div className="flex flex-col gap-2 px-2.5 pb-2 pt-1">
            <Count
              label="zu Hause"
              value={slot.eaters_home}
              where={where}
              onChange={(eaters_home) => onChange({ eaters_home })}
            />
            <Count
              label="mitnehmen"
              value={slot.packed_portions}
              where={where}
              onChange={(packed_portions) =>
                onChange({
                  packed_portions,
                  packed_fresh: packed_portions > 0 && (slot.packed_portions > 0 ? slot.packed_fresh : true),
                })
              }
            />
            {slot.packed_portions > 0 && active !== "packed" && origin}
          </div>
        )}
      </div>
    </>
  );
}

function Count({
  label,
  value,
  where,
  onChange,
}: {
  label: string;
  value: number;
  where: string;
  onChange: (value: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 text-xs text-ink-muted">{label}</span>
      <div className="flex-1">
        <Segmented
          size="sm"
          block
          label={`${label} ${where}`}
          value={String(value)}
          options={COUNTS}
          onChange={(next) => onChange(Number(next))}
        />
      </div>
    </div>
  );
}

/** Ganzen Tag auf "niemand da" - oder, ist er das schon, zurück auf zwei zu Hause. */
export function DayOffButton({
  cells,
  day,
  onChange,
}: {
  cells: SlotIn[];
  day: number;
  onChange: (meal: Meal, changes: Partial<SlotIn>) => void;
}) {
  const off = isDayOff(cells, day);
  return (
    <button
      type="button"
      aria-pressed={off}
      title={off ? "ganzen Tag zurück auf 2 zu Hause" : "ganzer Tag: niemand da"}
      aria-label={`${DAY_SHORT[day]}: ganzer Tag niemand da`}
      onClick={() => {
        for (const slot of cells.filter((cell) => cell.day === day)) {
          onChange(slot.meal, applyPreset(slot, off ? "two" : "nobody"));
        }
      }}
      className={[
        "rounded border px-1.5 py-px text-2xs transition-colors duration-fast",
        off
          ? "border-accent-line bg-accent-soft font-medium text-accent"
          : "border-line bg-surface text-ink-muted hover:bg-sunken hover:text-ink",
      ].join(" ")}
    >
      niemand da
    </button>
  );
}

function joinNames(names: string[]): string {
  if (names.length < 2) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} und ${names[names.length - 1]}`;
}
