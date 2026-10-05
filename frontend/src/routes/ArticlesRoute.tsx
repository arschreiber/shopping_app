/**
 * Artikelkorpus (~100-200 Stück). Wichtig sind drei Dinge pro Artikel: die kanonische
 * Einheit, der Bring!-Katalogname (nur damit gibt es Icon und Kategorie) und die
 * Flags Grundvorrat / Watchlist.
 */
import { useState } from "react";
import type { Article, Unit } from "../api/client";
import { suggestCatalog, useArticles, useMergeArticles, useSaveArticle } from "../api/hooks";
import { IconCheck, IconPlus } from "../components/Icons";
import { EmptyState, Segmented, Spinner, Toggle } from "../components/Primitives";
import { errorText, useToast } from "../components/Toast";
import { UNIT_LABEL, formatNumber } from "../lib/format";

const UNITS: Unit[] = ["G", "ML", "STUECK"];

/** Die Bezugsgröße steckt in der Einheit - kein eigenes Feld nötig. */
const BASIS_LABEL: Record<Unit, string> = {
  G: "je 100 g",
  ML: "je 100 ml",
  STUECK: "je Stück",
  KG: "je 100 g",
  L: "je 100 ml",
};

const NUTRITION_FIELDS: [string, string, string][] = [
  ["kcal", "Energie", "kcal"],
  ["carbs_g", "Kohlenhydrate", "g"],
  ["fat_g", "Fett", "g"],
  ["protein_g", "Eiweiß", "g"],
];

export function ArticlesRoute() {
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  // Aufräum-Modus: mehrere versehentlich doppelt angelegte Zutaten auswählen und auf
  // eine zusammenführen. Bewusst von Hand ausgelöst - ob "Süßkartoffeln" dasselbe wie
  // "Kartoffeln" ist, kann nur der Haushalt wissen.
  const [picked, setPicked] = useState<number[]>([]);
  const articles = useArticles(query || undefined);
  const merge = useMergeArticles();
  const mergeToast = useToast();

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-xl font-semibold">Artikel</h1>
          <p className="text-sm text-ink-muted">
            {articles.data
              ? `${articles.data.length} im Korpus · ${
                  articles.data.filter((entry) => entry.kcal !== null).length
                } mit Nährwerten`
              : "…"}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="suchen …"
            className="field w-40 sm:w-56"
            aria-label="Artikel suchen"
          />
          <button
            type="button"
            onClick={() => setCreating(!creating)}
            className={creating ? "btn-secondary btn-sm" : "btn-primary btn-sm"}
          >
            <IconPlus className="h-3.5 w-3.5" />
            Artikel
          </button>
        </div>
      </header>

      <p className="rounded-md border border-line bg-sunken/50 px-3 py-2 text-xs text-ink-muted">
        Zutaten <span className="font-medium text-ink">sind</span> Artikel: jede
        Zutatenzeile eines Gerichts zeigt auf einen von hier, und jede Zutat hat genau
        einen Namen. Beim Erfassen wird gesucht, bevor etwas Neues entsteht – so bleibt
        es bei einem „Reis“. Die <span className="font-medium text-ink">Einheit</span>{" "}
        gilt für alle Zeilen dieser Zutat, Gramm und Stück lassen sich nicht mischen. Der{" "}
        <span className="font-medium text-ink">Bring!-Name</span> muss exakt dem Katalog
        entsprechen, sonst fehlen Icon und Kategorie in der App.
      </p>

      {picked.length > 0 && (
        <MergeBar
          ids={picked}
          articles={articles.data ?? []}
          pending={merge.isPending}
          onCancel={() => setPicked([])}
          onMerge={(targetId) =>
            merge.mutate(
              { target_id: targetId, source_ids: picked.filter((id) => id !== targetId) },
              {
                onError: (error) => mergeToast.show(errorText(error), "error"),
                onSuccess: (article) => {
                  mergeToast.show(
                    `${picked.length} Zutaten sind jetzt „${article.canonical_name}“`,
                    "ok",
                  );
                  setPicked([]);
                },
              },
            )
          }
        />
      )}

      {creating && <ArticleEditor onDone={() => setCreating(false)} />}

      {articles.isLoading && <Spinner />}
      {articles.data?.length === 0 && (
        <EmptyState
          title="Kein Artikel gefunden"
          hint="Artikel entstehen normalerweise nebenbei beim Erfassen der Gerichte."
        />
      )}

      {articles.data && articles.data.length > 0 && (
        <div className="card overflow-hidden">
          <ul className="divide-y divide-line">
            {articles.data.map((article) =>
              editing === article.id ? (
                <li key={article.id} className="bg-sunken/40 p-3">
                  <ArticleEditor article={article} onDone={() => setEditing(null)} />
                </li>
              ) : (
                <li key={article.id} className="flex items-center gap-3 px-3 py-2 hover:bg-sunken/40">
                  <input
                    type="checkbox"
                    checked={picked.includes(article.id)}
                    onChange={(event) =>
                      setPicked((current) =>
                        event.target.checked
                          ? [...current, article.id]
                          : current.filter((id) => id !== article.id),
                      )
                    }
                    aria-label={`${article.canonical_name} zum Zusammenführen auswählen`}
                    title="Zum Zusammenführen auswählen"
                    className="h-3.5 w-3.5 shrink-0 accent-accent"
                  />
                  <button
                    type="button"
                    onClick={() => setEditing(article.id)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <span className="text-sm font-medium">{article.canonical_name}</span>
                    {(article.aliases ?? []).length > 0 && (
                      <span
                        className="ml-2 text-2xs text-ink-faint"
                        title="Angebots-Aliase (Phase 2) – für die Zutaten-Suche irrelevant"
                      >
                        {(article.aliases ?? []).join(", ")}
                      </span>
                    )}
                  </button>
                  <span className="w-12 shrink-0 text-right text-xs text-ink-muted">
                    {UNIT_LABEL[article.unit]}
                  </span>
                  <span
                    className="hidden w-24 shrink-0 text-right text-xs tabular-nums
                               text-ink-faint sm:block"
                    title={
                      article.kcal === null
                        ? "keine Nährwerte erfasst"
                        : `${article.kcal} kcal ${BASIS_LABEL[article.unit]}`
                    }
                  >
                    {article.kcal === null ? "– kcal" : `${formatNumber(article.kcal)} kcal`}
                  </span>
                  <span className="hidden w-36 shrink-0 truncate text-xs text-ink-faint sm:block">
                    {article.bring_catalog_name ?? "– kein Bring!-Name"}
                  </span>
                  <span className="flex w-24 shrink-0 justify-end gap-1">
                    {article.is_staple && (
                      <span className="chip py-0 text-2xs" title="Grundvorrat – nur auf Wunsch auf der Liste">
                        Vorrat
                      </span>
                    )}
                    {article.is_watchlist && (
                      <span className="chip chip-accent py-0 text-2xs" title="Angebots-Watchlist">
                        ★
                      </span>
                    )}
                  </span>
                </li>
              ),
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

function ArticleEditor({
  article,
  onDone,
}: {
  article?: Article;
  onDone: () => void;
}) {
  const save = useSaveArticle();
  const toast = useToast();
  const [name, setName] = useState(article?.canonical_name ?? "");
  const [unit, setUnit] = useState<Unit>(article?.unit ?? "G");
  const [bringName, setBringName] = useState(article?.bring_catalog_name ?? "");
  const [staple, setStaple] = useState(article?.is_staple ?? false);
  const [watchlist, setWatchlist] = useState(article?.is_watchlist ?? false);
  const [aliases, setAliases] = useState((article?.aliases ?? []).join(", "));
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [nutrition, setNutrition] = useState({
    kcal: article?.kcal ?? "",
    carbs_g: article?.carbs_g ?? "",
    fat_g: article?.fat_g ?? "",
    protein_g: article?.protein_g ?? "",
  });

  async function loadSuggestions() {
    if (!name.trim()) return;
    try {
      const hits = await suggestCatalog(name);
      setSuggestions(hits.map((hit) => hit.name));
    } catch {
      setSuggestions([]);
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate(
          {
            id: article?.id,
            body: {
              canonical_name: name,
              unit,
              bring_catalog_name: bringName || null,
              is_staple: staple,
              is_watchlist: watchlist,
              aliases: aliases
                .split(",")
                .map((entry) => entry.trim())
                .filter(Boolean),
              // Leeres Feld heißt "nicht erfasst", eine 0 heißt "enthält nichts davon".
              ...Object.fromEntries(
                Object.entries(nutrition).map(([field, value]) => [
                  field,
                  String(value).trim() === "" ? null : String(value).replace(",", "."),
                ]),
              ),
            },
          },
          {
            onError: (error) => toast.show(errorText(error), "error"),
            onSuccess: () => {
              toast.show("Artikel gespeichert", "ok");
              onDone();
            },
          },
        );
      }}
      className="flex flex-col gap-3"
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48 flex-1">
          <label className="label mb-1 block">Name</label>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            onBlur={loadSuggestions}
            className="field"
            required
            autoFocus
          />
        </div>
        <div>
          <span className="label mb-1 block">Einheit</span>
          <Segmented
            label="Einheit"
            value={unit}
            options={UNITS.map((value) => ({ value, label: UNIT_LABEL[value] }))}
            onChange={setUnit}
          />
        </div>
        <div className="min-w-48 flex-1">
          <label className="label mb-1 block">Bring!-Katalogname</label>
          <input
            value={bringName}
            onChange={(event) => setBringName(event.target.value)}
            placeholder="z. B. Feta"
            className="field"
          />
          {suggestions.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {suggestions.slice(0, 4).map((suggestion) => (
                <button
                  key={suggestion}
                  type="button"
                  onClick={() => setBringName(suggestion)}
                  className={
                    bringName === suggestion ? "chip chip-accent" : "chip hover:border-line-strong"
                  }
                >
                  {bringName === suggestion && <IconCheck className="h-3 w-3" />}
                  {suggestion}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div>
        <label className="label mb-1 block">
          Angebots-Aliase{" "}
          <span className="font-normal normal-case tracking-normal">
            (nur für den Angebotsabgleich in Phase 2, Komma-getrennt – für die
            Zutaten-Suche zählt allein der Name oben)
          </span>
        </label>
        <input
          value={aliases}
          onChange={(event) => setAliases(event.target.value)}
          placeholder="Feta, Schafskäse, Weichkäse in Salzlake"
          className="field"
        />
      </div>

      <fieldset className="rounded border border-line bg-sunken/40 px-2.5 py-2">
        <legend className="label px-1">
          Nährwerte {BASIS_LABEL[unit]}{" "}
          <span className="font-normal normal-case tracking-normal text-ink-faint">
            (optional – leer heißt „nicht erfasst“)
          </span>
        </legend>
        <div className="flex flex-wrap gap-3">
          {NUTRITION_FIELDS.map(([field, label, suffix]) => (
            <label key={field} className="flex items-center gap-1.5">
              <span className="text-xs text-ink-muted">{label}</span>
              <input
                type="number"
                min={0}
                step="0.1"
                inputMode="decimal"
                value={String(nutrition[field as keyof typeof nutrition] ?? "")}
                onChange={(event) =>
                  setNutrition((current) => ({ ...current, [field]: event.target.value }))
                }
                className="field w-20 py-1 text-right"
                aria-label={`${label} ${BASIS_LABEL[unit]}`}
              />
              <span className="text-2xs text-ink-faint">{suffix}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-wrap items-center gap-5">
        <Toggle checked={staple} onChange={setStaple} label="Grundvorrat" />
        <Toggle checked={watchlist} onChange={setWatchlist} label="Angebots-Watchlist" />
        <div className="ml-auto flex gap-2">
          <button type="submit" disabled={save.isPending} className="btn-primary btn-sm">
            {save.isPending ? "speichert …" : "Speichern"}
          </button>
          <button type="button" onClick={onDone} className="btn-secondary btn-sm">
            Abbrechen
          </button>
        </div>
      </div>
    </form>
  );
}


/**
 * Leiste für das Zusammenführen. Sie erscheint erst, wenn etwas ausgewählt ist, und
 * verlangt eine ausdrückliche Entscheidung, welcher Name bleibt - der Vorgang ist
 * nicht rückholbar.
 */
function MergeBar({
  ids,
  articles,
  pending,
  onMerge,
  onCancel,
}: {
  ids: number[];
  articles: Article[];
  pending: boolean;
  onMerge: (targetId: number) => void;
  onCancel: () => void;
}) {
  const selected = articles.filter((article) => ids.includes(article.id));
  const [targetId, setTargetId] = useState<number | null>(null);
  const effective = targetId ?? selected[0]?.id ?? null;
  const dimensions = new Set(
    selected.map((article) => (article.unit === "STUECK" ? "Stück" : article.unit)),
  );

  if (selected.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border
                    border-accent-line bg-accent-soft/50 px-3 py-2">
      <span className="text-sm">
        {selected.length === 1
          ? "Eine Zutat ausgewählt"
          : `${selected.length} Zutaten ausgewählt`}
        <span className="ml-1.5 text-xs text-ink-muted">
          {selected.map((article) => article.canonical_name).join(", ")}
        </span>
      </span>

      {selected.length > 1 && (
        <>
          <label className="flex items-center gap-1.5 text-sm">
            <span className="label">Name behalten</span>
            <select
              value={effective ?? undefined}
              onChange={(event) => setTargetId(Number(event.target.value))}
              className="field w-auto py-1"
            >
              {selected.map((article) => (
                <option key={article.id} value={article.id}>
                  {article.canonical_name}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={pending || effective === null || dimensions.size > 1}
            onClick={() => effective !== null && onMerge(effective)}
            className="btn-primary btn-sm"
            title={
              dimensions.size > 1
                ? "Verschiedene Einheiten lassen sich nicht zusammenführen"
                : "Die anderen Namen verschwinden, ihre Zutatenzeilen wandern mit"
            }
          >
            {pending ? "führt zusammen …" : "Zusammenführen"}
          </button>
        </>
      )}

      {dimensions.size > 1 && (
        <span className="text-xs text-danger">
          {[...dimensions].join(" und ")} lassen sich nicht zusammenführen.
        </span>
      )}

      <button type="button" onClick={onCancel} className="btn-ghost btn-sm ml-auto">
        Auswahl aufheben
      </button>
    </div>
  );
}
