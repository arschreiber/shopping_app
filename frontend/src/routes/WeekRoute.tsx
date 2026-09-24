/**
 * Die Seite des Montags-Rituals (general_plan.md §9): Raster ausfüllen → Vorschlag →
 * zwei, drei Tauschs → Liste prüfen → Bring!. Alles auf einer Seite, ohne Seitenwechsel.
 */
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { Candidate, Meal, Slot, SlotIn } from "../api/client";
import {
  useAssign,
  useCandidates,
  useClearSlot,
  useClearWeek,
  useCopyWeek,
  usePin,
  usePropose,
  useReroll,
  useSaveGrid,
  useWeek,
} from "../api/hooks";
import { IconChevronLeft, IconChevronRight, IconDice } from "../components/Icons";
import { EmptyState, Spinner } from "../components/Primitives";
import { errorText, useToast } from "../components/Toast";
import { WarningList } from "../components/Warnings";
import { Board } from "../features/week/Board";
import { CandidateSheet } from "../features/week/CandidateSheet";
import { GridEditor } from "../features/week/GridEditor";
import { currentIsoWeek, formatRange, parseIso, shiftIsoWeek } from "../lib/dates";

export function WeekRoute() {
  const params = useParams<{ iso?: string }>();
  const iso = params.iso ?? currentIsoWeek();
  const navigate = useNavigate();
  const toast = useToast();

  const [gridOpen, setGridOpen] = useState(false);
  const [selected, setSelected] = useState<{ day: number; meal: Meal } | null>(null);

  const week = useWeek(iso);
  const candidates = useCandidates(iso, selected?.day ?? 0, selected?.meal ?? "LUNCH", !!selected);

  const saveGrid = useSaveGrid(iso);
  const propose = usePropose(iso);
  const reroll = useReroll(iso);
  const assign = useAssign(iso);
  const clearSlot = useClearSlot(iso);
  const pin = usePin(iso);
  const clearWeek = useClearWeek(iso);
  const copyWeek = useCopyWeek(iso);

  const busy =
    propose.isPending ||
    reroll.isPending ||
    assign.isPending ||
    clearSlot.isPending ||
    clearWeek.isPending;

  function fail(error: unknown) {
    toast.show(errorText(error), "error");
  }

  const selectedSlot: Slot | null =
    (selected && week.data?.slots.find((s) => s.day === selected.day && s.meal === selected.meal)) ||
    null;

  function choose(candidate: Candidate) {
    if (!selected) return;
    const assignment = candidate.assignment;
    assign.mutate(
      {
        day: selected.day,
        meal: selected.meal,
        kind: assignment.kind as "DISH" | "LEFTOVER",
        dish_id: assignment.dish_id,
        doubled: assignment.doubled,
        leftover_source_day: assignment.leftover_source_day,
        leftover_source_meal: assignment.leftover_source_meal,
        portions_used: assignment.portions_used,
      },
      { onSuccess: () => setSelected(null), onError: fail },
    );
  }

  /** Drag & Drop: zwei Slots tauschen. Zwei Zuweisungen, sequenziell. */
  function swap(from: { day: number; meal: Meal }, to: { day: number; meal: Meal }) {
    const slots = week.data?.slots ?? [];
    const source = slots.find((s) => s.day === from.day && s.meal === from.meal);
    const target = slots.find((s) => s.day === to.day && s.meal === to.meal);
    if (!source?.assignment) return;

    const moveSource = {
      day: to.day,
      meal: to.meal,
      kind: source.assignment.kind as "DISH" | "LEFTOVER",
      dish_id: source.assignment.dish_id,
      doubled: source.assignment.doubled,
    };
    // Zuerst den Zielslot freimachen, damit die "einmal pro Woche"-Regel nicht greift.
    clearSlot.mutate(
      { day: from.day, meal: from.meal },
      {
        onError: fail,
        onSuccess: () =>
          assign.mutate(moveSource, {
            onError: fail,
            onSuccess: () => {
              if (!target?.assignment) return;
              assign.mutate(
                {
                  day: from.day,
                  meal: from.meal,
                  kind: target.assignment.kind as "DISH" | "LEFTOVER",
                  dish_id: target.assignment.dish_id,
                  doubled: target.assignment.doubled,
                },
                { onError: fail },
              );
            },
          }),
      },
    );
  }

  if (week.isLoading) {
    return (
      <div className="p-6">
        <Spinner label="Woche wird geladen …" />
      </div>
    );
  }
  if (week.isError || !week.data) {
    return (
      <div className="p-6">
        <EmptyState
          title="Woche konnte nicht geladen werden"
          hint={errorText(week.error)}
          action={
            <button type="button" onClick={() => week.refetch()} className="btn-secondary btn-sm">
              Nochmal versuchen
            </button>
          }
        />
      </div>
    );
  }

  const data = week.data;
  const { week: weekNumber } = parseIso(iso);
  const errors = data.warnings.filter((warning) => warning.level === "ERROR");
  const others = data.warnings.filter((warning) => warning.level !== "ERROR");

  return (
    <div className="flex flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="flex items-center gap-0.5">
          <button
            type="button"
            aria-label="Vorige Woche"
            onClick={() => navigate(`/week/${shiftIsoWeek(iso, -1)}`)}
            className="btn-ghost btn-sm"
          >
            <IconChevronLeft />
          </button>
          <button
            type="button"
            aria-label="Nächste Woche"
            onClick={() => navigate(`/week/${shiftIsoWeek(iso, 1)}`)}
            className="btn-ghost btn-sm"
          >
            <IconChevronRight />
          </button>
        </div>

        <div className="min-w-0">
          <h1 className="text-xl font-semibold">Woche {weekNumber}</h1>
          <p className="text-sm text-ink-muted">{formatRange(iso)}</p>
        </div>

        <span className="chip ml-1">
          {data.planned_count} von {data.needed_count} Slots
        </span>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setGridOpen(!gridOpen)}
            aria-expanded={gridOpen}
            className="btn-secondary btn-sm"
          >
            Raster {gridOpen ? "schließen" : "bearbeiten"}
          </button>
          <button
            type="button"
            onClick={() =>
              copyWeek.mutate(
                { sourceIso: shiftIsoWeek(iso, -1) },
                {
                  onError: fail,
                  onSuccess: () => toast.show("Raster der Vorwoche übernommen", "ok"),
                },
              )
            }
            disabled={copyWeek.isPending}
            className="btn-secondary btn-sm"
            title="Bürotage und Zeitbudget der Vorwoche übernehmen (nicht die Gerichte)"
          >
            wie letzte Woche
          </button>
          <button
            type="button"
            onClick={() =>
              propose.mutate(
                { onlyEmpty: data.planned_count > 0 },
                {
                  onError: fail,
                  onSuccess: (result) =>
                    toast.show(
                      `${result.planned_count} von ${result.needed_count} Slots belegt`,
                      "ok",
                    ),
                },
              )
            }
            disabled={busy}
            className="btn-primary btn-sm order-first sm:order-none"
          >
            <IconDice className="h-3.5 w-3.5" />
            {data.planned_count > 0 ? "Lücken füllen" : "Woche vorschlagen"}
          </button>
          {data.planned_count > 0 && (
            <button
              type="button"
              onClick={() => clearWeek.mutate({ keepPinned: true }, { onError: fail })}
              disabled={busy}
              className="btn-ghost btn-sm"
              title="Alles außer gepinnten Slots leeren"
            >
              leeren
            </button>
          )}
        </div>
      </header>

      {gridOpen && (
        <div className="card overflow-hidden">
          <GridEditor
            week={data}
            iso={iso}
            saving={saveGrid.isPending}
            onSave={(slots: SlotIn[], version: number) =>
              saveGrid.mutate(
                { slots, version },
                {
                  onError: (error) => {
                    fail(error);
                    week.refetch();
                  },
                  onSuccess: () => toast.show("Raster gespeichert", "ok"),
                },
              )
            }
          />
        </div>
      )}

      {errors.length > 0 && (
        <WarningList warnings={errors} onSelect={(day, meal) => setSelected({ day, meal })} />
      )}

      <Board
        week={data}
        iso={iso}
        onOpen={(slot) => setSelected({ day: slot.day, meal: slot.meal })}
        onPin={(slot, pinned) =>
          pin.mutate({ day: slot.day, meal: slot.meal, pinned }, { onError: fail })
        }
        onReroll={(slot) =>
          reroll.mutate({ day: slot.day, meal: slot.meal }, { onError: fail })
        }
        onSwap={swap}
      />

      {others.length > 0 && (
        <section>
          <h2 className="label mb-2">Hinweise zum Plan</h2>
          <WarningList
            warnings={others}
            max={6}
            onSelect={(day, meal) => setSelected({ day, meal })}
          />
        </section>
      )}

      <CandidateSheet
        open={!!selected}
        slot={selectedSlot}
        candidates={candidates.data ?? []}
        loading={candidates.isLoading}
        busy={assign.isPending || clearSlot.isPending}
        onClose={() => setSelected(null)}
        onChoose={choose}
        onClear={() => {
          if (!selected) return;
          clearSlot.mutate(selected, { onError: fail, onSuccess: () => setSelected(null) });
        }}
      />
    </div>
  );
}
