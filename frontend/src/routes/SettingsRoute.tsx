/**
 * Einstellungen: Planer-Gewichte (Spike 4 ohne Deploy), Haushalt, Einkauf - und die
 * Sync-Historie. Letztere macht einen Integrationsbruch sichtbar statt still
 * (ARCHITECTURE.md §8).
 */
import { useEffect, useState } from "react";
import { useHealth, useSaveSettings, useSettings, useSyncRuns } from "../api/hooks";
import { EmptyState, Spinner } from "../components/Primitives";
import { SectionTitle } from "../components/Primitives";
import { errorText, useToast } from "../components/Toast";

/** Gruppiert die Gewichte so, wie general_plan.md §4 sie beschreibt. */
const GROUPS: { title: string; hint: string; keys: string[] }[] = [
  {
    title: "Abwechslung",
    hint: "Abzug, wenn Beilage, Protein oder Küche sich in der Woche wiederholen.",
    keys: [
      "same_side_adjacent",
      "same_side_same_week",
      "same_protein_adjacent",
      "same_protein_same_week",
      "same_cuisine_adjacent",
      "same_cuisine_same_week",
      "variety_span_slots",
    ],
  },
  {
    title: "Rotation",
    hint: "Lange nicht gekocht gibt Bonus, kürzlich gekocht Abzug.",
    keys: ["rotation_per_week", "rotation_cap", "never_cooked_bonus", "cooked_within_two_weeks"],
  },
  {
    title: "Portionen und Reste",
    hint: "Was übrig bleibt und niemand mehr braucht, ist Verschwendung.",
    keys: [
      "exact_portions",
      "waste_per_portion",
      "surplus_usable_per_portion",
      "leftover_covers_demand",
      "leftover_assignment",
      "doubling",
    ],
  },
  {
    title: "Zufall",
    hint:
      "Bei jedem „Woche vorschlagen“ bekommt jedes frische Gericht 0 bis so viele " +
      "Punkte dazu – ähnlich gute wechseln sich ab. Ob Reste drankommen, entscheidet er " +
      "nie. 0 = immer derselbe Plan.",
    keys: ["randomness"],
  },
  {
    title: "Bewertung, Angebote",
    hint: "Angebots-Bonus wirkt erst, wenn Angebotsdaten da sind (Phase 2).",
    keys: [
      "rating_per_star",
      "offer_per_euro",
      "offer_cap",
    ],
  },
];

const LABELS: Record<string, string> = {
  same_side_adjacent: "gleiche Beilage, nah",
  same_side_same_week: "gleiche Beilage, gleiche Woche",
  same_protein_adjacent: "gleiches Protein, nah",
  same_protein_same_week: "gleiches Protein, gleiche Woche",
  same_cuisine_adjacent: "gleiche Küche, nah",
  same_cuisine_same_week: "gleiche Küche, gleiche Woche",
  variety_span_slots: "„nah“ = bis wie viele Slots Abstand",
  rotation_per_week: "Bonus pro Woche ohne Kochen",
  rotation_cap: "Obergrenze Rotations-Bonus",
  never_cooked_bonus: "noch nie gekocht",
  cooked_within_two_weeks: "in den letzten 2 Wochen gekocht",
  exact_portions: "Portionen passen genau",
  waste_per_portion: "Portion bleibt übrig",
  surplus_usable_per_portion: "Rest-Portion ist verwertbar",
  leftover_covers_demand: "Reste-Karte deckt den Slot",
  leftover_assignment: "Reste statt neu kochen",
  doubling: "verdoppeln",
  rating_per_star: "pro Stern über 3",
  offer_per_euro: "pro Euro Ersparnis",
  offer_cap: "Obergrenze Angebots-Bonus",
  randomness: "Zufall: bis zu so viele Punkte",
};

export function SettingsRoute() {
  const settings = useSettings();
  const save = useSaveSettings();
  const health = useHealth();
  const runs = useSyncRuns();
  const toast = useToast();

  const [weights, setWeights] = useState<Record<string, number>>({});
  const [shelfLife, setShelfLife] = useState(2);
  const [threshold, setThreshold] = useState(5);

  useEffect(() => {
    if (!settings.data) return;
    setWeights(settings.data.planner_weights);
    setShelfLife(Number(settings.data.shopping.leftover_shelf_life_days ?? 2));
    setThreshold(Number(settings.data.shopping.split_threshold_eur ?? 5));
  }, [settings.data]);

  if (settings.isLoading) {
    return (
      <div className="p-6">
        <Spinner />
      </div>
    );
  }
  if (!settings.data) {
    return (
      <div className="p-6">
        <EmptyState title="Einstellungen nicht ladbar" hint={errorText(settings.error)} />
      </div>
    );
  }

  const dirty =
    JSON.stringify(weights) !== JSON.stringify(settings.data.planner_weights) ||
    shelfLife !== Number(settings.data.shopping.leftover_shelf_life_days ?? 2) ||
    threshold !== Number(settings.data.shopping.split_threshold_eur ?? 5);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold">Einstellungen</h1>
        <p className="text-sm text-ink-muted">
          Die Gewichte steuern die Reihenfolge der Vorschläge. Sie liegen in der Datenbank,
          nicht im Code – Änderungen wirken sofort beim nächsten Vorschlag.
        </p>
      </header>

      <section className="card p-4">
        <SectionTitle>Status</SectionTitle>
        {health.data ? (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-4">
            <Stat label="Gerichte" value={String(health.data.dishes)} />
            <Stat label="Artikel" value={String(health.data.articles)} />
            <Stat
              label="Sync"
              value={health.data.sync_adapter === "bring" ? "Bring!" : "nur Text"}
            />
            <Stat
              label="Bring!-Katalog"
              value={health.data.catalog_cached ? "gecacht" : "fehlt"}
            />
            <Stat
              label="letzter Push"
              value={
                health.data.last_bring_push
                  ? new Date(health.data.last_bring_push).toLocaleString("de-DE")
                  : "nie"
              }
            />
            <Stat
              label="letzte Angebote"
              value={
                health.data.last_offer_fetch
                  ? new Date(health.data.last_offer_fetch).toLocaleString("de-DE")
                  : "nie"
              }
            />
          </dl>
        ) : (
          <Spinner />
        )}
      </section>

      <section className="card p-4">
        <SectionTitle>Einkauf</SectionTitle>
        <div className="flex flex-wrap gap-6">
          <label className="flex flex-col gap-1">
            <span className="text-sm">Haltbarkeit von Resten (Tage)</span>
            <input
              type="number"
              min={0}
              max={6}
              value={shelfLife}
              onChange={(event) => setShelfLife(Number(event.target.value))}
              className="field w-24"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-sm">Schwelle für zweiten Laden (€)</span>
            <input
              type="number"
              min={0}
              step={0.5}
              value={threshold}
              onChange={(event) => setThreshold(Number(event.target.value))}
              className="field w-24"
            />
          </label>
        </div>
      </section>

      {GROUPS.map((group) => (
        <section key={group.title} className="card p-4">
          <SectionTitle>{group.title}</SectionTitle>
          <p className="mb-3 text-xs text-ink-muted">{group.hint}</p>
          <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {group.keys
              .filter((key) => key in weights)
              .map((key) => (
                <label key={key} className="flex items-center justify-between gap-3">
                  <span className="text-sm text-ink-muted">{LABELS[key] ?? key}</span>
                  <input
                    type="number"
                    step={key === "variety_span_slots" ? 1 : 0.5}
                    value={weights[key]}
                    onChange={(event) =>
                      setWeights((current) => ({
                        ...current,
                        [key]: Number(event.target.value),
                      }))
                    }
                    className="field w-20 py-1 text-right"
                  />
                </label>
              ))}
          </div>
        </section>
      ))}

      <div className="sticky bottom-0 flex items-center gap-2 border-t border-line
                      bg-ground/95 py-3 backdrop-blur">
        <button
          type="button"
          disabled={!dirty || save.isPending}
          onClick={() =>
            save.mutate(
              {
                planner_weights: weights,
                shopping: {
                  ...settings.data!.shopping,
                  leftover_shelf_life_days: shelfLife,
                  split_threshold_eur: threshold,
                },
              },
              {
                onError: (error) => toast.show(errorText(error), "error"),
                onSuccess: () => toast.show("Einstellungen gespeichert", "ok"),
              },
            )
          }
          className="btn-primary"
        >
          {save.isPending ? "speichert …" : dirty ? "Speichern" : "gespeichert"}
        </button>
        <button
          type="button"
          onClick={() =>
            save.mutate(
              { planner_weights: {} },
              {
                onError: (error) => toast.show(errorText(error), "error"),
                onSuccess: () => toast.show("Auf Standardwerte zurückgesetzt", "ok"),
              },
            )
          }
          className="btn-secondary"
        >
          Standardwerte
        </button>
      </div>

      <section>
        <SectionTitle>Sync-Historie</SectionTitle>
        {runs.data && runs.data.length > 0 ? (
          <div className="card overflow-hidden">
            <ul className="divide-y divide-line">
              {runs.data.map((run) => (
                <li key={run.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                  <span
                    className={[
                      "chip py-0 text-2xs",
                      run.status === "OK"
                        ? "chip-accent"
                        : run.status === "PARTIAL"
                          ? "border-warn-line bg-warn-soft text-warn"
                          : "border-danger-line bg-danger-soft text-danger",
                    ].join(" ")}
                  >
                    {run.status}
                  </span>
                  <span className="text-ink-muted">
                    {run.kind === "BRING_PUSH" ? "Bring!-Push" : "Angebots-Abruf"}
                  </span>
                  <span className="ml-auto text-xs text-ink-faint">
                    {new Date(run.started_at).toLocaleString("de-DE")}
                  </span>
                  {run.error && (
                    <span className="w-full text-xs text-danger sm:w-auto">{run.error}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="text-sm text-ink-faint">Noch kein Sync gelaufen.</p>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  );
}
