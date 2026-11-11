/**
 * Die Seite des Montags-Rituals (general_plan.md §9): Raster ausfüllen → Vorschlag →
 * zwei, drei Tauschs → Liste prüfen → Bring!. Alles auf einer Seite, ohne Seitenwechsel.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
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
  useSetCancelled,
  useWeek,
  useWeekNutrition,
} from "../api/hooks";
import { IconChevronLeft, IconChevronRight, IconDice } from "../components/Icons";
import { EmptyState, Segmented, Spinner } from "../components/Primitives";
import { errorText, useToast } from "../components/Toast";
import { WarningList } from "../components/Warnings";
import { Board } from "../features/week/Board";
import { CandidateSheet } from "../features/week/CandidateSheet";
import { toSlotInputs } from "../features/week/SlotSettings";
import { NutritionDetail, scaleSum } from "../features/week/WeekNutrition";
import { currentIsoWeek, formatRange, parseIso, shiftIsoWeek } from "../lib/dates";

export function WeekRoute() {
  const params = useParams<{ iso?: string }>();
  const iso = params.iso ?? currentIsoWeek();
  const navigate = useNavigate();
  const toast = useToast();

  // Raster bearbeiten: `null` = das Board zeigt Gerichte, sonst die Einstellungen im
  // Entwurf. Gespeichert wird erst per Knopf, mit `version` gegen den Konflikt
  // Laptop/Handy.
  const [gridDraft, setGridDraft] = useState<SlotIn[] | null>(null);
  const editing = gridDraft !== null;

  // Ansicht "Gerichte" oder "Nährwerte" - je Gerät gemerkt.
  const [view, setView] = useState<BoardView>(readView);
  const [nutritionDay, setNutritionDay] = useState<number | null>(null);
  // Ø je Portion (1×) oder hochgerechnet auf einen Tag mit Mittag + Abend (2×).
  const [averageFactor, setAverageFactor] = useState<"1" | "2">("1");
  const showNutrition = view === "nutrition" && !editing;
  const nutrition = useWeekNutrition(iso, showNutrition);
  useEffect(() => setNutritionDay(null), [iso]);
  // Am Handy steht das Detail weit unter dem angetippten Tag - dorthin scrollen.
  useEffect(() => {
    if (nutritionDay === null) return;
    const timer = window.setTimeout(
      () =>
        document
          .getElementById("day-nutrition")
          ?.scrollIntoView({ behavior: "smooth", block: "nearest" }),
      50,
    );
    return () => window.clearTimeout(timer);
  }, [nutritionDay]);
  const [selected, setSelected] = useState<{ day: number; meal: Meal } | null>(null);

  const week = useWeek(iso);

  // Andere Woche = anderer Entwurf. Den alten stehen zu lassen, hieße ihn auf die neue
  // Woche zu speichern.
  useEffect(() => setGridDraft(null), [iso]);
  // Fremde Änderungen (anderes Gerät, "wie letzte Woche") während des Bearbeitens
  // übernehmen, sonst würde der Entwurf gegen eine veraltete Version gespeichert.
  useEffect(() => {
    if (week.data) setGridDraft((current) => (current ? toSlotInputs(week.data) : current));
  }, [week.data?.version]);
  const candidates = useCandidates(iso, selected?.day ?? 0, selected?.meal ?? "LUNCH", !!selected);

  const saveGrid = useSaveGrid(iso);
  const propose = usePropose(iso);
  const reroll = useReroll(iso);
  const assign = useAssign(iso);
  const clearSlot = useClearSlot(iso);
  const pin = usePin(iso);
  const setCancelled = useSetCancelled(iso);
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
        factor: assignment.factor,
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
      factor: source.assignment.factor,
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
                  factor: target.assignment.factor,
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
  const gridDirty =
    gridDraft !== null && JSON.stringify(gridDraft) !== JSON.stringify(toSlotInputs(data));

  function saveGridDraft() {
    if (!gridDraft) return;
    if (!gridDirty) {
      setGridDraft(null);
      return;
    }
    saveGrid.mutate(
      { slots: gridDraft, version: data.version },
      {
        onError: (error) => {
          fail(error);
          week.refetch();
        },
        onSuccess: () => {
          toast.show("Raster gespeichert", "ok");
          setGridDraft(null);
        },
      },
    );
  }
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

        {!editing && (
          <Segmented
            label="Ansicht"
            size="sm"
            value={view}
            options={[
              { value: "dishes", label: "Gerichte" },
              { value: "nutrition", label: "Nährwerte", title: "je Portion und je Tag" },
            ]}
            onChange={(next) => {
              setView(next);
              writeView(next);
            }}
          />
        )}

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {!editing && (
            <button
              type="button"
              onClick={() => setGridDraft(toSlotInputs(data))}
              className="btn-secondary btn-sm"
            >
              Raster bearbeiten
            </button>
          )}
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
            title="Raster der Vorwoche übernehmen: wer isst, mitnehmen, Zeit (nicht die Gerichte)"
          >
            wie letzte Woche
          </button>
          {editing && (
            <>
              <button
                type="button"
                onClick={() => setGridDraft(null)}
                className="btn-ghost btn-sm"
              >
                abbrechen
              </button>
              <button
                type="button"
                onClick={saveGridDraft}
                disabled={saveGrid.isPending}
                className="btn-primary btn-sm order-first sm:order-none"
              >
                {saveGrid.isPending ? "speichert …" : "Raster speichern"}
              </button>
            </>
          )}
          {!editing && (
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
              {/* Der Optimierer rechnet ein, zwei Sekunden - sichtbar, dass etwas passiert. */}
              {propose.isPending
                ? "plant …"
                : data.planned_count > 0
                  ? "Lücken füllen"
                  : "Woche vorschlagen"}
            </button>
          )}
          {!editing && data.planned_count > 0 && (
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

      {editing && <GridHint />}

      {!editing && errors.length > 0 && (
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
        onClear={(slot) =>
          clearSlot.mutate({ day: slot.day, meal: slot.meal }, { onError: fail })
        }
        onSwap={swap}
        nutrition={showNutrition ? (nutrition.data ?? null) : undefined}
        selectedDay={nutritionDay}
        onSelectDay={(day) => setNutritionDay((current) => (current === day ? null : day))}
        editing={
          gridDraft
            ? {
                draft: gridDraft,
                onChange: (day, meal, changes) =>
                  setGridDraft((current) =>
                    current
                      ? current.map((slot) =>
                          slot.day === day && slot.meal === meal ? { ...slot, ...changes } : slot,
                        )
                      : current,
                  ),
              }
            : undefined
        }
      />

      {showNutrition && nutrition.isLoading && <Spinner label="Nährwerte werden berechnet …" />}

      {showNutrition && nutrition.data && nutritionDay !== null && (
        <NutritionDetail
          id="day-nutrition"
          title={`${DAY_NAME[nutritionDay]} · je Person`}
          subtitle={
            nutrition.data.days[nutritionDay].meal_count < nutrition.data.meals_per_day
              ? `nur ${nutrition.data.days[nutritionDay].meal_count} von ${nutrition.data.meals_per_day} Mahlzeiten erfasst`
              : "Mittag + Abend"
          }
          sum={nutrition.data.days[nutritionDay]}
          footnote={`Balken: Anteil am Tageswert (${nutrition.data.reference_person}) – ohne Frühstück und Snacks. Quelle: ${nutrition.data.attribution}`}
          onClose={() => setNutritionDay(null)}
        />
      )}

      {showNutrition && nutrition.data && (
        nutrition.data.average.meal_count > 0 ? (
          <NutritionDetail
            title={
              averageFactor === "2"
                ? "Ø je Tag diese Woche (2 Portionen)"
                : "Ø je Portion diese Woche"
            }
            subtitle={`aus ${nutrition.data.average.meal_count} ${
              nutrition.data.average.meal_count === 1 ? "Mahlzeit" : "Mahlzeiten"
            } · jede Mahlzeit zählt einmal`}
            sum={scaleSum(nutrition.data.average, Number(averageFactor))}
            action={
              <Segmented
                label="Hochrechnen"
                size="sm"
                value={averageFactor}
                options={[
                  { value: "1", label: "1×", title: "eine Portion" },
                  { value: "2", label: "2×", title: "ein Tag: Mittag + Abend" },
                ]}
                onChange={setAverageFactor}
              />
            }
            footnote={
              averageFactor === "2"
                ? `Zwei Ø-Portionen, also ein Tag mit Mittag und Abend. Balken: Anteil am Tageswert einer Person (${nutrition.data.reference_person}) – ohne Frühstück und Snacks.`
                : `Balken: Anteil am Tageswert einer Person (${nutrition.data.reference_person}) – eine Portion, nicht der ganze Tag. Auswärts, Vorrat und ausgefallene Mahlzeiten zählen nicht mit.`
            }
          />
        ) : (
          <EmptyState
            title="Noch keine Nährwerte"
            hint="Sobald Gerichte mit Nährwerten geplant sind, stehen hier Tagessummen und der Ø je Portion."
          />
        )
      )}

      {!editing && others.length > 0 && (
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
        busy={assign.isPending || clearSlot.isPending || setCancelled.isPending}
        onClose={() => setSelected(null)}
        onChoose={choose}
        onClear={() => {
          if (!selected) return;
          clearSlot.mutate(selected, { onError: fail, onSuccess: () => setSelected(null) });
        }}
        onCancel={(cancelled) => {
          if (!selected) return;
          setCancelled.mutate(
            { ...selected, cancelled },
            {
              onError: fail,
              onSuccess: () => {
                setSelected(null);
                toast.show(
                  cancelled ? "Ausgefallen – zählt nicht als gekocht" : "Zählt wieder als gekocht",
                  "ok",
                );
              },
            },
          );
        }}
      />
    </div>
  );
}

/** Eine Zeile reicht zum Loslegen; was "frisch" und "vorgekocht" heißt, steht dahinter. */
function GridHint() {
  const [more, setMore] = useState(false);
  return (
    <div className="rounded-md border border-accent-line bg-accent-soft/50 px-3 py-2 text-xs
                    text-ink-muted">
      <p className="flex items-center gap-2">
        <span>Tippe eine Mahlzeit an und wähle, wer isst.</span>
        <button
          type="button"
          aria-expanded={more}
          aria-label={more ? "Erklärung ausblenden" : "Mehr erklären"}
          onClick={() => setMore((open) => !open)}
          className="ml-auto inline-flex h-5 min-w-5 items-center justify-center rounded-full border
                     border-accent-line bg-surface px-1.5 text-2xs font-medium text-accent
                     hover:bg-accent-soft"
        >
          {more ? "weniger" : "?"}
        </button>
      </p>
      {more && (
        <p className="mt-1.5">
          <span className="font-medium text-ink">Mitnehmen</span> trägst du bei der Mahlzeit
          ein, die unterwegs gegessen wird: <span className="font-medium text-ink">frisch</span>{" "}
          wird in dieser Mahlzeit mitgekocht, <span className="font-medium text-ink">vorgekocht</span>{" "}
          kommt bevorzugt aus Resten. Bei <span className="font-medium text-ink">wenig Zeit</span>{" "}
          kommen nur schnelle Gerichte oder Reste, bei{" "}
          <span className="font-medium text-ink">keiner Zeit</span> nur Reste – dafür kocht der
          Planer vorher mehr. Neue Wochen starten mit der{" "}
          <Link to="/settings" className="font-medium text-accent underline-offset-2 hover:underline">
            Standardwoche
          </Link>
          .
        </p>
      )}
    </div>
  );
}

type BoardView = "dishes" | "nutrition";
const VIEW_KEY = "week.view";
const DAY_NAME = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"];

function readView(): BoardView {
  try {
    return localStorage.getItem(VIEW_KEY) === "nutrition" ? "nutrition" : "dishes";
  } catch {
    return "dishes";
  }
}

function writeView(view: BoardView) {
  try {
    localStorage.setItem(VIEW_KEY, view);
  } catch {
    // privates Fenster o. Ä. - dann eben nicht gemerkt
  }
}
