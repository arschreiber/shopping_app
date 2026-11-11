/**
 * Nährwerte: welche Artikel tragen am meisten von einem Nährstoff?
 *
 * Links die Nährstoffe (gruppiert wie in den Nährwert-Tabellen), rechts alle Artikel
 * von viel nach wenig. Verglichen wird je 100 g / 100 ml - oder, umgeschaltet, je
 * 100 kcal (Nährstoffdichte). Gerechnet wird im Backend (`domain/nutrient_ranking.py`).
 *
 * Nährstoff und Basis stehen in der URL (`?code=FE&basis=kcal`), damit die Tabellen bei
 * Gericht und Woche direkt hierher verlinken können.
 */
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type { NutrientDef, NutrientRanking } from "../api/client";
import { useNutrientDefs, useNutrientRanking } from "../api/hooks";
import { EmptyState, Segmented, Spinner } from "../components/Primitives";
import { ArticleTabs } from "../features/articles/ArticleTabs";
import { formatNumber } from "../lib/format";

type Basis = "mass" | "kcal";
const DEFAULT_CODE = "protein_g";

export function NutrientsRoute() {
  const [params, setParams] = useSearchParams();
  const defs = useNutrientDefs();
  const code = params.get("code") ?? DEFAULT_CODE;
  const basis: Basis = params.get("basis") === "kcal" ? "kcal" : "mass";
  const ranking = useNutrientRanking(code, basis);
  const selected = defs.data?.find((nutrient) => nutrient.code === code);

  function update(next: { code?: string; basis?: Basis }) {
    const merged = { code, basis, ...next };
    setParams(
      merged.basis === "kcal" ? { code: merged.code, basis: "kcal" } : { code: merged.code },
      { replace: true },
    );
  }

  const groups = groupBy(defs.data ?? []);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 p-4 sm:p-6">
      <ArticleTabs />
      <header className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-xl font-semibold">Nährwerte</h1>
          <p className="text-sm text-ink-muted">
            Welche Artikel tragen am meisten – Klick auf einen Nährstoff sortiert alle.
          </p>
        </div>
        <div className="ml-auto">
          <Segmented
            label="Bezugsgröße"
            size="sm"
            value={basis}
            options={[
              { value: "mass", label: "je 100 g/ml", title: "Wie viel steckt in der Menge" },
              {
                value: "kcal",
                label: "je 100 kcal",
                title: "Nährstoffdichte: was bekomme ich für meine Kalorien",
              },
            ]}
            onChange={(value) => update({ basis: value })}
          />
        </div>
      </header>

      {/* Handy: Auswahlliste statt Spalte */}
      <select
        value={code}
        onChange={(event) => update({ code: event.target.value })}
        aria-label="Nährstoff"
        className="field lg:hidden"
      >
        {groups.map(([group, nutrients]) => (
          <optgroup key={group} label={group}>
            {nutrients.map((nutrient) => (
              <option key={nutrient.code} value={nutrient.code}>
                {nutrient.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>

      <div className="grid items-start gap-4 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <nav className="card hidden flex-col gap-3 p-3 lg:sticky lg:top-16 lg:flex" aria-label="Nährstoffe">
          {defs.isLoading && <Spinner />}
          {groups.map(([group, nutrients]) => (
            <div key={group}>
              <span className="label mb-1 block px-2">{group}</span>
              <ul>
                {nutrients.map((nutrient) => (
                  <li key={nutrient.code}>
                    <button
                      type="button"
                      onClick={() => update({ code: nutrient.code })}
                      aria-current={nutrient.code === code ? "true" : undefined}
                      className={[
                        "flex w-full items-baseline justify-between rounded px-2 py-1 text-left",
                        "text-sm transition-colors duration-fast",
                        nutrient.code === code
                          ? "bg-accent-soft font-medium text-accent"
                          : "text-ink hover:bg-sunken",
                      ].join(" ")}
                    >
                      {nutrient.label}
                      <span className="text-2xs text-ink-faint">{nutrient.unit}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <section className="card min-w-0 p-4">
          {ranking.isLoading && <Spinner label="sortiert …" />}
          {ranking.isError && (
            <EmptyState title="Nährstoff unbekannt" hint="Bitte links einen auswählen." />
          )}
          {ranking.data && selected && <RankingList data={ranking.data} nutrient={selected} />}
        </section>
      </div>
    </div>
  );
}

function RankingList({ data, nutrient }: { data: NutrientRanking; nutrient: NutrientDef }) {
  const [showMissing, setShowMissing] = useState(false);
  const top = Math.max(...data.entries.map((entry) => Number(entry.amount)), 0);
  const perLabel = data.basis === "kcal" ? "je 100 kcal" : "je 100 g bzw. 100 ml";
  const limit = nutrient.kind === "limit";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-base font-semibold">{nutrient.label}</h2>
        <span className="text-xs text-ink-muted">
          {perLabel} · {data.entries.length} Artikel
          {nutrient.reference && (
            <>
              {" "}
              · Tageswert {formatNumber(nutrient.reference)} {nutrient.unit}
              {limit && " (Obergrenze)"}
            </>
          )}
        </span>
      </div>

      {data.entries.length === 0 ? (
        <p className="text-sm text-ink-muted">Kein Artikel hat hierzu einen Wert.</p>
      ) : (
        <ol className="flex flex-col">
          {data.entries.map((entry, index) => {
            const percent =
              entry.share !== null && entry.share !== undefined ? Number(entry.share) : null;
            // Ohne Tageswert (Makros, Zucker): Balken relativ zum Spitzenreiter.
            const width =
              percent !== null ? percent : top > 0 ? (Number(entry.amount) / top) * 100 : 0;
            return (
              <li
                key={entry.article_id}
                className="grid grid-cols-[1.75rem_minmax(0,1fr)_auto] items-center gap-x-2
                           border-t border-line py-1.5 first:border-t-0"
              >
                <span className="text-right text-2xs tabular-nums text-ink-faint">
                  {index + 1}
                </span>
                <div className="min-w-0">
                  <Link
                    to={`/articles?edit=${entry.article_id}`}
                    className="block truncate text-sm hover:text-accent hover:underline"
                  >
                    {entry.name}
                  </Link>
                  <div className="mt-0.5 h-1 rounded-full bg-sunken">
                    <div
                      className={[
                        "h-1 rounded-full",
                        limit && percent !== null && percent > 33 ? "bg-warn" : "bg-accent",
                      ].join(" ")}
                      style={{ width: `${Math.min(width, 100)}%` }}
                    />
                  </div>
                </div>
                <span className="text-right text-sm tabular-nums">
                  {formatNumber(entry.amount)}
                  <span className="text-2xs text-ink-faint"> {nutrient.unit}</span>
                  {entry.per !== "100 g" && data.basis === "mass" && (
                    <span className="text-2xs text-ink-faint"> /{entry.per}</span>
                  )}
                  <span className="ml-1.5 inline-block w-10 text-2xs text-ink-faint">
                    {percent !== null ? `${percent} %` : ""}
                  </span>
                  <span
                    className="inline-block w-3 text-2xs font-medium text-accent"
                    title={entry.source === "label" ? "vom Etikett" : "aus dem BLS"}
                  >
                    {entry.source === "label" ? "E" : ""}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>
      )}

      {data.missing.length > 0 && (
        <div className="border-t border-line pt-2">
          <button
            type="button"
            onClick={() => setShowMissing(!showMissing)}
            aria-expanded={showMissing}
            className="text-xs text-ink-muted hover:text-ink"
          >
            {showMissing ? "▾" : "▸"} ohne Wert: {data.missing.length} Artikel
          </button>
          {showMissing && (
            <ul className="mt-1.5 flex flex-wrap gap-1.5">
              {data.missing.map((entry) => (
                <li key={entry.article_id}>
                  <Link
                    to={`/articles?edit=${entry.article_id}`}
                    className="chip hover:border-line-strong hover:text-ink"
                    title={entry.reason}
                  >
                    {entry.name}
                    <span className="text-2xs opacity-60">{entry.reason}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <p className="text-2xs text-ink-faint">
        % = Anteil am Tageswert ({data.reference_person}) {perLabel}. E = vom Etikett, sonst
        BLS. Ohne Tageswert ist der Balken relativ zum Spitzenreiter. Quelle: {data.attribution}
      </p>
    </div>
  );
}

function groupBy(nutrients: NutrientDef[]): [string, NutrientDef[]][] {
  const groups = new Map<string, NutrientDef[]>();
  for (const nutrient of nutrients) {
    groups.set(nutrient.group, [...(groups.get(nutrient.group) ?? []), nutrient]);
  }
  return [...groups.entries()];
}
