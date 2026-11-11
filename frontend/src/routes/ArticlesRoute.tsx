/**
 * Artikelkorpus (~100-200 Stück). Wichtig sind drei Dinge pro Artikel: die kanonische
 * Einheit, der Bring!-Katalogname (nur damit gibt es Icon und Kategorie) und die
 * Flags Grundvorrat / Watchlist.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { Article, ArticleMicro, Unit } from "../api/client";
import {
  suggestCatalog,
  useArticles,
  useMergeArticles,
  useMicroFields,
  useSaveArticle,
} from "../api/hooks";
import { IconCheck, IconPlus } from "../components/Icons";
import { EmptyState, Segmented, Spinner, Toggle } from "../components/Primitives";
import { BlsReference } from "../features/articles/BlsReference";
import { LabelMicros, labelMicrosBody } from "../features/articles/LabelMicros";
import { MicroProfile } from "../features/articles/MicroProfile";
import { ArticleTabs } from "../features/articles/ArticleTabs";
import { errorText, useToast } from "../components/Toast";
import { PRICE_UNIT, UNIT_LABEL, formatNumber, formatUnitPrice } from "../lib/format";

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
  // `?edit=ID` öffnet einen Artikel direkt - z. B. aus der Nährwert-Rangliste.
  const [params] = useSearchParams();
  const [editing, setEditing] = useState<number | null>(
    () => Number(params.get("edit")) || null,
  );
  const [creating, setCreating] = useState(false);
  // Aufräum-Modus: mehrere versehentlich doppelt angelegte Zutaten auswählen und auf
  // eine zusammenführen. Bewusst von Hand ausgelöst - ob "Süßkartoffeln" dasselbe wie
  // "Kartoffeln" ist, kann nur der Haushalt wissen.
  const [picked, setPicked] = useState<number[]>([]);
  const articles = useArticles(query || undefined);
  const merge = useMergeArticles();
  const mergeToast = useToast();
  // Eine wählbare Nährstoff-Spalte statt 23: "Was bringt am meisten Eisen?" Gewählt,
  // sortiert die Liste absteigend danach - je Bezugsgröße des Artikels.
  const microFields = useMicroFields();
  const [column, setColumn] = useState("");
  const columnField = microFields.data?.find((field) => field.code === column);
  const microOf = (article: Article) =>
    article.micros?.find((value) => value.code === column) ?? null;
  const rows =
    column && articles.data
      ? [...articles.data].sort(
          (a, b) => Number(microOf(b)?.amount ?? -1) - Number(microOf(a)?.amount ?? -1),
        )
      : articles.data;

  // Der geöffnete Artikel kann weit unten stehen - einmal hinscrollen, wenn er da ist.
  const loaded = Boolean(articles.data);
  useEffect(() => {
    const id = Number(params.get("edit"));
    if (!id || !loaded) return;
    document.getElementById(`article-${id}`)?.scrollIntoView({ block: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded]);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 p-4 sm:p-6">
      <ArticleTabs />
      <header className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-xl font-semibold">Artikel</h1>
          <p className="text-sm text-ink-muted">
            {articles.data
              ? `${articles.data.length} im Korpus · ${
                  articles.data.filter((entry) => entry.kcal !== null).length
                } mit Nährwerten · ${
                  articles.data.filter((entry) => entry.bls_code).length
                } mit BLS-Referenz`
              : "…"}
          </p>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select
            value={column}
            onChange={(event) => setColumn(event.target.value)}
            className="field w-40"
            aria-label="Nährstoff-Spalte wählen"
            title="Zeigt einen Nährstoff je 100 g / 100 ml / Stück und sortiert danach"
          >
            <option value="">Spalte: kcal</option>
            {(microFields.data ?? [])
              .filter((field) => field.code !== "FOLAC")
              .map((field) => (
                <option key={field.code} value={field.code}>
                  Spalte: {field.label}
                </option>
              ))}
          </select>
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

      {rows && rows.length > 0 && (
        <div className="card overflow-hidden">
          <ul className="divide-y divide-line">
            {rows.map((article) =>
              editing === article.id ? (
                <li key={article.id} id={`article-${article.id}`} className="bg-sunken/40 p-3">
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
                  {columnField ? (
                    <MicroCell
                      value={microOf(article)}
                      unit={columnField.unit}
                      basis={BASIS_LABEL[article.unit]}
                    />
                  ) : (
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
                  )}
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

function MicroCell({
  value,
  unit,
  basis,
}: {
  value: ArticleMicro | null;
  unit: string;
  basis: string;
}) {
  return (
    <span
      className="w-28 shrink-0 text-right text-xs tabular-nums text-ink-muted"
      title={
        value
          ? `${basis}, ${value.source === "label" ? "vom Etikett" : "aus dem BLS"}`
          : "unbekannt"
      }
    >
      {value ? (
        <>
          {formatNumber(value.amount)}
          <span className="text-2xs text-ink-faint"> {unit}</span>
          {value.share !== null && value.share !== undefined && (
            <span className="ml-1 text-2xs text-ink-faint">{value.share} %</span>
          )}
        </>
      ) : (
        <span className="text-ink-faint">–</span>
      )}
    </span>
  );
}

function decimalOrNull(value: string | number): string | null {
  const text = String(value).trim().replace(",", ".");
  return text === "" ? null : text;
}

/** "250 g für 1,29 €" -> "5,16 €/kg"; "1 Stück für 0,79 €" bei 200 g -> "3,95 €/kg" */
function packPreview(
  amount: string | number,
  price: string | number,
  unit: Unit,
  inPieces: boolean,
  pieceSize: string | number,
): string | null {
  const number = (value: string | number) => Number(String(value).replace(",", "."));
  let quantity = number(amount);
  const euros = number(price);
  if (!(quantity > 0) || !(euros > 0)) return null;
  if (inPieces && unit !== "STUECK") {
    const size = number(pieceSize);
    if (!(size > 0)) return null;
    quantity *= size;
  }
  const perUnit = (euros * (unit === "STUECK" ? 1 : 1000)) / quantity;
  return formatUnitPrice(perUnit, PRICE_UNIT[unit]);
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
  const [target, setTarget] = useState(article?.max_unit_price ?? "");
  const [minAmount, setMinAmount] = useState(article?.min_offer_amount ?? "");
  const [regularAmount, setRegularAmount] = useState(article?.regular_pack_amount ?? "");
  const [regularPrice, setRegularPrice] = useState(article?.regular_pack_price ?? "");
  const [regularInPieces, setRegularInPieces] = useState(article?.regular_pack_unit === "STUECK");
  const [pieceSize, setPieceSize] = useState(article?.piece_size ?? "");
  // Stückgewicht und "pro Stück" gibt es nur bei Gramm- und Milliliter-Artikeln.
  const weighed = unit !== "STUECK";
  // Nur die Vorschau beim Tippen - gespeichert und verglichen wird der Wert des Servers.
  const regularPreview = packPreview(
    regularAmount,
    regularPrice,
    unit,
    weighed && regularInPieces,
    pieceSize,
  );
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [nutrition, setNutrition] = useState({
    kcal: article?.kcal ?? "",
    carbs_g: article?.carbs_g ?? "",
    fat_g: article?.fat_g ?? "",
    protein_g: article?.protein_g ?? "",
  });

  const [labelMicros, setLabelMicros] = useState<Record<string, string>>(
    Object.fromEntries(
      Object.entries(article?.label_micros ?? {}).map(([code, value]) => [code, String(value)]),
    ),
  );

  // Bring!-Vorschläge gleich beim Öffnen laden (und beim Tippen nachziehen) - früher
  // kamen sie erst beim Verlassen des Namensfelds und schoben dann das Formular.
  useEffect(() => {
    const query = name.trim();
    if (!query) {
      setSuggestions([]);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(
      async () => {
        try {
          const hits = await suggestCatalog(query);
          if (!cancelled) setSuggestions(hits.map((hit) => hit.name));
        } catch {
          if (!cancelled) setSuggestions([]);
        }
      },
      article && query === article.canonical_name ? 0 : 300,
    );
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [name, article]);

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
              // Leer heißt: jedes Angebot zählt, egal wie teuer.
              max_unit_price: decimalOrNull(target),
              // Leer heißt: jede Packungsgröße zählt.
              min_offer_amount: decimalOrNull(minAmount),
              regular_pack_amount: decimalOrNull(regularAmount),
              regular_pack_price: decimalOrNull(regularPrice),
              regular_pack_unit: weighed && regularInPieces ? "STUECK" : null,
              piece_size: weighed ? decimalOrNull(pieceSize) : null,
              label_micros: labelMicrosBody(labelMicros),
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
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-48 flex-1">
          <label className="label mb-1 block">Name</label>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
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
          Preise{" "}
          <span className="font-normal normal-case tracking-normal text-ink-faint">
            (optional – für die Angebote)
          </span>
        </legend>
        <div className="flex flex-wrap gap-x-8 gap-y-3">
          {weighed && (
            <div className="flex flex-col gap-1">
              <span className="text-xs text-ink-muted">
                Stückgewicht – für Angebote pro Stück (Avocado, Gurke)
              </span>
              <span className="flex items-center gap-1.5">
                <span className="text-sm text-ink-muted">1 Stück ≈</span>
                <input
                  type="number"
                  min={0}
                  step="any"
                  inputMode="decimal"
                  value={String(pieceSize)}
                  onChange={(event) => setPieceSize(event.target.value)}
                  placeholder="–"
                  aria-label={`Stückgewicht in ${UNIT_LABEL[unit]}`}
                  className="field w-20 py-1 text-right"
                />
                <span className="text-sm text-ink-muted">{UNIT_LABEL[unit]}</span>
              </span>
            </div>
          )}
          <div className="flex flex-col gap-1">
            <span className="text-xs text-ink-muted">
              Normalpreis – was ihr ohne Angebot zahlt, z. B. für die Eigenmarke
            </span>
            <span className="flex flex-wrap items-center gap-1.5">
              <input
                type="number"
                min={0}
                step="any"
                inputMode="decimal"
                value={String(regularAmount)}
                onChange={(event) => setRegularAmount(event.target.value)}
                placeholder="–"
                aria-label={`Normalpreis: Menge in ${
                  weighed && regularInPieces ? "Stück" : UNIT_LABEL[unit]
                }`}
                className="field w-20 py-1 text-right"
              />
              {weighed ? (
                <Segmented
                  size="xs"
                  label="Normalpreis: Menge in"
                  value={regularInPieces ? "piece" : "unit"}
                  options={[
                    { value: "unit", label: UNIT_LABEL[unit] },
                    { value: "piece", label: "Stück" },
                  ]}
                  onChange={(choice) => setRegularInPieces(choice === "piece")}
                />
              ) : (
                <span className="text-sm text-ink-muted">{UNIT_LABEL[unit]}</span>
              )}
              <span className="text-sm text-ink-muted">für</span>
              <input
                type="number"
                min={0}
                step="0.01"
                inputMode="decimal"
                value={String(regularPrice)}
                onChange={(event) => setRegularPrice(event.target.value)}
                placeholder="–"
                aria-label="Normalpreis: Preis in €"
                className="field w-20 py-1 text-right"
              />
              <span className="text-sm text-ink-muted">€</span>
              {regularPreview && (
                <span className="text-xs text-ink-faint">= {regularPreview}</span>
              )}
              {weighed && regularInPieces && !regularPreview && regularAmount !== "" && (
                <span className="text-xs text-warn">braucht ein Stückgewicht</span>
              )}
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs text-ink-muted">
              Richtpreis – Angebote darüber zählen nicht (leer: jedes zählt)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-sm text-ink-muted">bis</span>
              <input
                id="article-target-price"
                aria-label={`Richtpreis in €/${PRICE_UNIT[unit]}`}
                type="number"
                min={0}
                step="0.01"
                inputMode="decimal"
                value={String(target)}
                onChange={(event) => setTarget(event.target.value)}
                placeholder="–"
                className="field w-24 py-1 text-right"
              />
              <span className="text-sm text-ink-muted">€/{PRICE_UNIT[unit]}</span>
            </span>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-xs text-ink-muted">
              Mindestpackung – kleinere Angebote zählen nicht (leer: jede)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-sm text-ink-muted">ab</span>
              <input
                aria-label={`Mindestpackung in ${UNIT_LABEL[unit]}`}
                type="number"
                min={0}
                step="any"
                inputMode="decimal"
                value={String(minAmount)}
                onChange={(event) => setMinAmount(event.target.value)}
                placeholder="–"
                className="field w-20 py-1 text-right"
              />
              <span className="text-sm text-ink-muted">{UNIT_LABEL[unit]}</span>
            </span>
          </div>
        </div>
      </fieldset>

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

      {article && (
        <BlsReference article={article}>
          <MicroProfile article={article} basis={BASIS_LABEL[unit]} />
        </BlsReference>
      )}

      <LabelMicros values={labelMicros} onChange={setLabelMicros} basis={BASIS_LABEL[unit]} />

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
