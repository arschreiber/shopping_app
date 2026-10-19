/**
 * Das Gerüst der Woche: 7 Tage x 2 Mahlzeiten, ohne zu wissen, was in den Zellen steht.
 *
 * Laptop: Spalten pro Tag. Handy und Tablet: pro Tag ein Block, Mittag und Abend
 * nebeneinander. Das Wochenboard füllt es mit Gerichten oder Raster-Einstellungen, die
 * Standardwoche in den Einstellungen mit Raster-Einstellungen - beide sehen so gleich aus.
 */
import { Fragment, type ReactNode } from "react";
import type { Meal } from "../../api/client";
import { DAY_SHORT, formatDay, isToday } from "../../lib/dates";
import { MEAL_LABEL } from "../../lib/format";

const MEALS: Meal[] = ["LUNCH", "DINNER"];

export function WeekGrid({
  iso,
  renderCell,
  dayAction,
  wide = "columns",
}: {
  /** Mit Woche: Datum und "heute" an den Tagen. Ohne (Standardwoche): nur Wochentage. */
  iso?: string;
  /**
   * Laptop-Ansicht: Tagesspalten wie im Board, oder eine Zeile pro Tag - für schmale
   * Container wie die Einstellungen, wo sieben Spalten "2 zu Hause" umbrechen.
   */
  wide?: "columns" | "rows";
  /** `wide` = Laptop-Raster - dort gibt es Drag & Drop. */
  renderCell: (day: number, meal: Meal, wide: boolean) => ReactNode;
  /** Etwas für den ganzen Tag, rechts neben dem Tagesnamen. */
  dayAction?: (day: number) => ReactNode;
}) {
  const today = (day: number) => (iso ? isToday(iso, day) : false);

  return (
    <>
      {wide === "rows" && (
        <div
          className="hidden items-center gap-x-2 gap-y-2 lg:grid
                     lg:grid-cols-[3rem_minmax(0,1fr)_minmax(0,1fr)_auto]"
        >
          <div />
          {MEALS.map((meal) => (
            <span key={meal} className="label">
              {MEAL_LABEL[meal]}
            </span>
          ))}
          <div />
          {DAY_SHORT.map((name, day) => (
            <Fragment key={day}>
              <span className="text-sm font-semibold text-ink">{name}</span>
              {MEALS.map((meal) => (
                <div key={meal} className="min-w-0">
                  {renderCell(day, meal, true)}
                </div>
              ))}
              <div>{dayAction?.(day)}</div>
            </Fragment>
          ))}
        </div>
      )}

      {/* Laptop: echtes Raster mit Tagesspalten */}
      {wide === "columns" && (
        <div className="hidden lg:block">
          <div className="grid grid-cols-[4.5rem_repeat(7,minmax(0,1fr))] gap-x-2">
            <div />
            {DAY_SHORT.map((name, day) => (
              <div
                key={day}
                className={[
                  "flex items-baseline gap-1.5 border-b px-1 pb-1.5",
                  today(day) ? "border-accent" : "border-line",
                ].join(" ")}
              >
                <span
                  className={[
                    "text-2xs font-semibold uppercase tracking-wider",
                    today(day) ? "text-accent" : "text-ink-faint",
                  ].join(" ")}
                >
                  {name}
                </span>
                {iso && <span className="text-2xs text-ink-faint">{formatDay(iso, day)}</span>}
                {dayAction && <span className="ml-auto self-center">{dayAction(day)}</span>}
              </div>
            ))}

            {MEALS.map((meal) => (
              <div key={meal} className="col-span-8 grid grid-cols-subgrid gap-x-2 py-1.5">
                <div className="flex items-center justify-end pr-1">
                  <span className="label">{MEAL_LABEL[meal]}</span>
                </div>
                {DAY_SHORT.map((_, day) => (
                  <div key={day} className="min-w-0">
                    {renderCell(day, meal, true)}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Handy und Tablet: pro Tag ein Block, Mittag und Abend nebeneinander */}
      <div className="flex flex-col gap-3 lg:hidden">
        {DAY_SHORT.map((name, day) => (
          <section key={day}>
            <div
              className={[
                "mb-1.5 flex items-center gap-2 border-b pb-1",
                today(day) ? "border-accent" : "border-line",
              ].join(" ")}
            >
              <h3
                className={[
                  "text-sm font-semibold",
                  today(day) ? "text-accent" : "text-ink",
                ].join(" ")}
              >
                {name}
              </h3>
              {iso && <span className="text-xs text-ink-faint">{formatDay(iso, day)}</span>}
              <div className="ml-auto flex items-center gap-2">
                {today(day) && <span className="chip chip-accent">heute</span>}
                {dayAction?.(day)}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {MEALS.map((meal) => (
                <div key={meal} className="min-w-0">
                  <span className="label mb-1 block">{MEAL_LABEL[meal]}</span>
                  {renderCell(day, meal, false)}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
