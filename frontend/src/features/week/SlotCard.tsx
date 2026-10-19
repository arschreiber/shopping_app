/**
 * Eine Slot-Karte im Wochenboard. Flach, Haarlinie, ein Akzent für Pins.
 * Reste-Portionen sind sichtbar anders (gestrichelte Kante, eigenes Icon), weil sie
 * fachlich etwas anderes sind: schon gekauft, schon gekocht. Ein ausgefallenes Gericht
 * bleibt stehen, aber durchgestrichen - so sieht man, warum es nicht als gekocht zählt.
 * Unten rechts die Zeit (TimeMark): Uhr bei wenig Zeit, Reste-Schale bei keiner.
 */
import { useDraggable, useDroppable } from "@dnd-kit/core";
import type { Slot, Warning } from "../../api/client";
import {
  IconClose,
  IconDice,
  IconLeftover,
  IconPin,
  IconPlus,
} from "../../components/Icons";
import { TimeMark } from "./TimeMark";

export function SlotCard({
  slot,
  iso,
  warnings,
  onOpen,
  onPin,
  onReroll,
  onClear,
  dragEnabled,
}: {
  slot: Slot;
  iso: string;
  /** Warnungen *dieses* Slots - der Punkt auf der Karte, Details im Sheet. */
  warnings: Warning[];
  onOpen: () => void;
  onPin: (pinned: boolean) => void;
  onReroll: () => void;
  onClear: () => void;
  dragEnabled: boolean;
}) {
  const id = `${slot.day}-${slot.meal}`;
  const assignment = slot.assignment;
  const isLeftover = assignment?.kind === "LEFTOVER";
  const cancelled = assignment?.cancelled ?? false;
  const timed = slot.time_budget !== "NORMAL";
  // Auf der Karte steht *ob* etwas nicht stimmt, nicht wie viel es kostet. Die Zahl ohne
  // ihre Begruendung liest sich als Note - und eine Woche voller "-11,0" entmutigt, ohne
  // etwas zu erklaeren. Der Score gehoert dorthin, wo auch seine Beitraege stehen: ins
  // Kandidaten-Sheet.
  const level = warnings.some((warning) => warning.level === "ERROR")
    ? "ERROR"
    : warnings.some((warning) => warning.level === "WARN")
      ? "WARN"
      : null;

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `drop-${id}`,
    data: { day: slot.day, meal: slot.meal },
    disabled: !dragEnabled || slot.demand === 0 || slot.special === "EATING_OUT",
  });
  const {
    attributes,
    listeners,
    setNodeRef: setDragRef,
    isDragging,
  } = useDraggable({
    id: `drag-${id}`,
    data: { day: slot.day, meal: slot.meal, assignment },
    disabled: !dragEnabled || !assignment || slot.pinned,
  });

  // "auswärts" gibt es nur noch als Abkürzung im Raster - es heißt "niemand da".
  if (slot.demand === 0 || slot.special === "EATING_OUT") {
    // Schraffiert statt gestrichelt: der leere Slot daneben wartet auf ein Gericht, dieser
    // hier nicht. Vorher sahen beide gleich blass aus.
    return (
      <div className="hatch flex min-h-[4.5rem] flex-col justify-center rounded-md border
                      border-line-strong bg-sunken px-2.5 py-2 text-center">
        <span className="mx-auto rounded bg-sunken px-1.5 text-xs font-medium text-ink-muted">
          {slot.packed_portions > 0 ? "mitgenommen" : "niemand da"}
        </span>
      </div>
    );
  }

  const empty = !assignment;

  return (
    <div
      ref={setDropRef}
      title={warnings.map((warning) => warning.text).join("\n") || undefined}
      className={[
        "group relative flex min-h-[4.5rem] flex-col rounded-md border transition-colors duration-fast",
        empty
          ? "border-dashed border-line bg-sunken/40 hover:border-accent-line hover:bg-accent-soft/40"
          : isLeftover
            ? "border-dashed border-accent-line bg-accent-soft/50"
            : cancelled
              ? "border-line bg-sunken/60 hover:border-line-strong"
              : "border-line bg-surface hover:border-line-strong",
        isOver ? "border-accent bg-accent-soft" : "",
        isDragging ? "opacity-40" : "",
        slot.special === "FROM_PANTRY" ? "ring-1 ring-inset ring-warn-line" : "",
      ].join(" ")}
    >
      <button
        type="button"
        onClick={onOpen}
        ref={assignment ? setDragRef : undefined}
        {...(assignment ? attributes : {})}
        {...(assignment ? listeners : {})}
        className="flex flex-1 cursor-pointer flex-col items-start gap-1 px-2.5 py-2 text-left"
        aria-label={`${slot.day}/${slot.meal}: ${assignment?.dish_name ?? "leer"}`}
      >
        {empty ? (
          <span className="m-auto flex items-center gap-1 text-xs text-ink-faint
                           group-hover:text-accent">
            <IconPlus className="h-3.5 w-3.5" />
            {slot.special === "FROM_PANTRY"
              ? "aus Vorhandenem"
              : slot.time_budget === "NONE"
                ? "Reste wählen"
                : "wählen"}
          </span>
        ) : (
          <>
            <span className="flex w-full items-start gap-1">
              {isLeftover && <IconLeftover className="mt-[3px] h-3.5 w-3.5 text-accent" />}
              <span
                className={[
                  "line-clamp-2 flex-1 text-sm font-medium leading-snug",
                  cancelled ? "text-ink-muted line-through" : "",
                ].join(" ")}
              >
                {assignment!.dish_name}
              </span>
            </span>
            <span className="flex w-full items-center gap-1.5 text-2xs text-ink-faint">
              {isLeftover ? (
                <span>Reste {assignment!.leftover_source_label}</span>
              ) : (
                <>
                  <span>{assignment!.portions} P</span>
                  {assignment!.factor > 1 && (
                    <span className="text-accent">×{assignment!.factor}</span>
                  )}
                  {cancelled && <span className="text-ink-muted">ausgefallen</span>}
                </>
              )}
              {(timed || level) && (
                <span className="ml-auto flex items-center gap-1">
                  <TimeMark budget={slot.time_budget} />
                  {level && (
                    <span
                      className={[
                        "h-1.5 w-1.5 rounded-full",
                        level === "ERROR" ? "bg-danger" : "bg-warn",
                      ].join(" ")}
                      aria-label={level === "ERROR" ? "Fehler" : "Hinweis"}
                    />
                  )}
                </span>
              )}
            </span>
          </>
        )}
      </button>

      {empty && timed && (
        <span className="pointer-events-none absolute bottom-1.5 right-2">
          <TimeMark budget={slot.time_budget} />
        </span>
      )}

      <div className="absolute right-1 top-1 flex gap-0.5 opacity-0 transition-opacity
                      duration-fast focus-within:opacity-100 group-hover:opacity-100">
        {assignment && (
          <button
            type="button"
            title="Neu würfeln"
            aria-label={`${id} neu würfeln`}
            onClick={(event) => {
              event.stopPropagation();
              onReroll();
            }}
            className="rounded p-1 text-ink-faint hover:bg-sunken hover:text-ink"
          >
            <IconDice className="h-3.5 w-3.5" />
          </button>
        )}
        {assignment && (
          <button
            type="button"
            title="Mahlzeit leeren"
            aria-label={`${id} leeren`}
            onClick={(event) => {
              event.stopPropagation();
              onClear();
            }}
            className="rounded p-1 text-ink-faint hover:bg-danger-soft hover:text-danger"
          >
            <IconClose className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          type="button"
          title={slot.pinned ? "Pin lösen" : "Pinnen - bleibt beim Neu-Vorschlagen stehen"}
          aria-label={`${id} ${slot.pinned ? "Pin lösen" : "pinnen"}`}
          aria-pressed={slot.pinned}
          onClick={(event) => {
            event.stopPropagation();
            onPin(!slot.pinned);
          }}
          className={[
            "rounded p-1 hover:bg-sunken",
            slot.pinned
              ? "text-accent opacity-100"
              : "text-ink-faint hover:text-ink",
          ].join(" ")}
        >
          <IconPin className="h-3.5 w-3.5" />
        </button>
      </div>

      {slot.pinned && (
        <span
          className="pointer-events-none absolute left-0 top-0 h-full w-[3px] rounded-l-md bg-accent"
          aria-hidden="true"
          title="gepinnt"
        />
      )}
      <span className="sr-only">{iso}</span>
    </div>
  );
}

