/**
 * Raster-Einstellungen *einer* Mahlzeit (general_plan.md §5 Phase 1: wer isst wann zu
 * Hause, was wird mitgenommen - in 30 Sekunden ausgefüllt).
 *
 * Im Bearbeiten-Modus steht diese Zelle im Board genau dort, wo sonst das Gericht steht.
 * Deshalb kompakt: sie teilt sich die Breite mit sechs Nachbartagen. Die Zahlen sind
 * 0|1|2 statt Plus/Minus - ein Klick statt zwei -, und "auswärts" ist die Abkürzung für
 * "niemand da": beides heißt, hier wird nicht gekocht. Die Zeit hat zwei Stufen: bei
 * "wenig" kommen nur schnelle Gerichte oder Reste.
 */
import type { ReactNode } from "react";
import type { SlotIn, TimeBudget, Week } from "../../api/client";
import { Segmented } from "../../components/Primitives";
import { DAY_SHORT } from "../../lib/dates";
import { MEAL_LABEL, TIME_SHORT } from "../../lib/format";

const COUNTS = ["0", "1", "2"].map((value) => ({ value, label: value }));

const TIME_OPTIONS: { value: TimeBudget; label: string; title: string }[] = [
  { value: "NORMAL", label: TIME_SHORT.NORMAL, title: "normale Zeit - jedes Gericht" },
  { value: "LITTLE", label: TIME_SHORT.LITTLE, title: "wenig Zeit - nur schnelle Gerichte oder Reste" },
];

// Woher die Mitnehm-Portion kommt: vorgekocht (bevorzugt Reste) oder frisch in dieser
// Mahlzeit gekocht - etwa fürs Abendessen, das zu einem Termin mitgeht.
const ORIGIN_OPTIONS = [
  { value: "prepared", label: "vorgekocht", title: "vorgekocht - gern aus Resten" },
  { value: "fresh", label: "frisch", title: "frisch - wird in dieser Mahlzeit gekocht" },
];

// Wer "auswärts" wieder abwählt, meint eine normale Mahlzeit. Also zurück auf den
// Standard einer neuen Woche statt auf die Nullen von eben.
const DEFAULT_EATERS = 2;

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

export function SlotSettings({
  slot,
  onChange,
}: {
  slot: SlotIn;
  onChange: (changes: Partial<SlotIn>) => void;
}) {
  const where = `${DAY_SHORT[slot.day]} ${MEAL_LABEL[slot.meal]}`;
  // Dieselbe Schraffur wie die "niemand da"-Karte: beim Einstellen sieht man schon, wie
  // der Slot danach im Board aussieht.
  const nobody = slot.eaters_home === 0 && slot.packed_portions === 0;

  return (
    <div
      className={[
        "flex min-h-[4.5rem] flex-col gap-1 rounded-md border px-2 py-1.5",
        nobody ? "hatch border-line-strong bg-sunken" : "border-line bg-surface",
      ].join(" ")}
    >
      <div className="flex flex-col gap-1">
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
            onChange({ packed_portions, ...(packed_portions === 0 && { packed_fresh: false }) })
          }
        />
        {slot.packed_portions > 0 && (
          <Segmented
            size="xs"
            block
            label={`Mitnehmen ${where}`}
            value={slot.packed_fresh ? "fresh" : "prepared"}
            options={ORIGIN_OPTIONS}
            onChange={(origin) => onChange({ packed_fresh: origin === "fresh" })}
          />
        )}
        <Labeled label="Zeit">
          <Segmented
            size="xs"
            block
            label={`Zeit ${where}`}
            value={slot.time_budget}
            options={TIME_OPTIONS}
            onChange={(time_budget) => onChange({ time_budget })}
          />
        </Labeled>
      </div>

      <button
        type="button"
        aria-pressed={nobody}
        aria-label={`auswärts ${where}`}
        title="auswärts - niemand da, nichts zu planen"
        onClick={() =>
          onChange(
            nobody
              ? { special: "NONE", eaters_home: DEFAULT_EATERS }
              : { special: "NONE", eaters_home: 0, packed_portions: 0, packed_fresh: false },
          )
        }
        className={[
          "rounded border px-1.5 py-px text-2xs transition-colors duration-fast",
          nobody
            ? "border-accent-line bg-accent-soft font-medium text-accent"
            : "border-line bg-surface text-ink-muted hover:bg-sunken hover:text-ink",
        ].join(" ")}
      >
        auswärts
      </button>
    </div>
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
    <Labeled label={label}>
      <Segmented
        size="xs"
        block
        label={`${label} ${where}`}
        value={String(value)}
        options={COUNTS}
        onChange={(next) => onChange(Number(next))}
      />
    </Labeled>
  );
}

function Labeled({ label, children }: { label: string; children: ReactNode }) {
  // Beschriftung über statt neben der Auswahl: so bekommen beide die volle Zellbreite,
  // statt sich gegenseitig abzuschneiden ("zu Ha…", halbe "2").
  return (
    <div className="flex flex-col gap-0.5">
      <span
        className="self-start rounded bg-surface/80 px-0.5 text-2xs leading-tight
                   text-ink-muted"
      >
        {label}
      </span>
      {children}
    </div>
  );
}
