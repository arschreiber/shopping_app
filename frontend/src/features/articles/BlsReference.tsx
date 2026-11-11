/**
 * Die BLS-Referenz eines Artikels: aus ihr kommen Vitamine und Mineralstoffe (und die
 * Makros, solange oben nichts vom Etikett steht).
 *
 * Gespeichert wird sofort beim Klick, unabhängig vom Formular darüber - die Wahl ist
 * eine eigene Entscheidung ("Kichererbsen: getrocknet oder aus der Dose?") und soll
 * nicht an „Speichern“ hängen. Vorschläge werden nie still übernommen.
 */
import { type ReactNode, useEffect, useState } from "react";
import type { Article, BlsFood } from "../../api/client";
import { searchBls, useBlsSuggestions, useSetBls } from "../../api/hooks";
import { errorText, useToast } from "../../components/Toast";

export function BlsReference({ article, children }: { article: Article; children?: ReactNode }) {
  const setBls = useSetBls();
  const toast = useToast();
  const open = !article.bls_code && !article.bls_skip;
  const [choosing, setChoosing] = useState(open);
  const suggestions = useBlsSuggestions(article.id, choosing);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<BlsFood[] | null>(null);
  const [grams, setGrams] = useState(article.bls_grams_per_unit ?? "");
  const needsGrams = article.unit !== "G";

  useEffect(() => {
    if (query.trim().length < 2) {
      setHits(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const result = await searchBls(query);
        if (!cancelled) setHits(result);
      } catch {
        if (!cancelled) setHits([]);
      }
    }, 200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  function save(vars: { code?: string | null; skip?: boolean; grams_per_unit?: string | null }) {
    setBls.mutate(
      { id: article.id, grams_per_unit: decimalOrNull(grams), ...vars },
      {
        onError: (error) => toast.show(errorText(error), "error"),
        onSuccess: () => {
          setChoosing(false);
          setQuery("");
        },
      },
    );
  }

  const list = hits ?? suggestions.data ?? [];

  return (
    <fieldset className="rounded border border-line bg-sunken/40 px-2.5 py-2">
      <legend className="label px-1">
        Vitamine &amp; Mineralstoffe{" "}
        <span className="font-normal normal-case tracking-normal text-ink-faint">
          (Referenz im Bundeslebensmittelschlüssel)
        </span>
      </legend>

      <div className="flex flex-wrap items-center gap-2">
        {article.bls_code ? (
          <span className="text-sm">
            {article.bls_name ?? article.bls_code}
            <span className="ml-1.5 font-mono text-2xs text-ink-faint">{article.bls_code}</span>
          </span>
        ) : article.bls_skip ? (
          <span className="text-sm text-ink-muted">bewusst ohne Referenz</span>
        ) : (
          <span className="text-sm text-warn">noch keine Referenz</span>
        )}
        <span className="ml-auto flex gap-1.5">
          {!choosing && (
            <button type="button" className="btn-ghost btn-sm" onClick={() => setChoosing(true)}>
              {article.bls_code ? "Ändern" : "Wählen"}
            </button>
          )}
          {article.bls_code && (
            <button type="button" className="btn-ghost btn-sm" onClick={() => save({})}>
              Lösen
            </button>
          )}
          {!article.bls_skip && (
            <button
              type="button"
              className="btn-ghost btn-sm"
              title="Kein passender Eintrag (z. B. Proteinpulver) – zählt im Gericht als Lücke"
              onClick={() => save({ skip: true })}
            >
              Keine passende
            </button>
          )}
        </span>
      </div>

      {needsGrams && (
        <label className="mt-2 flex items-center gap-1.5">
          <span className="text-xs text-ink-muted">
            {article.unit === "STUECK" ? "1 Stück wiegt" : "Dichte"}
          </span>
          <input
            type="number"
            min={0}
            step="any"
            inputMode="decimal"
            value={String(grams)}
            onChange={(event) => setGrams(event.target.value)}
            onBlur={() => {
              if (article.bls_code && decimalOrNull(grams) !== (article.bls_grams_per_unit ?? null)) {
                save({ code: article.bls_code });
              }
            }}
            placeholder={article.unit === "STUECK" ? "nötig" : "1"}
            className="field w-20 py-1 text-right"
            aria-label={article.unit === "STUECK" ? "Gramm je Stück" : "Gramm je Milliliter"}
          />
          <span className="text-2xs text-ink-faint">
            {article.unit === "STUECK" ? "g" : "g/ml (Öl ≈ 0,92)"}
          </span>
        </label>
      )}

      {choosing && (
        <div className="mt-2 flex flex-col gap-1.5">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Im BLS suchen, z. B. „linse rot“"
            className="field py-1"
            aria-label="Im Bundeslebensmittelschlüssel suchen"
          />
          <ul className="flex max-h-56 flex-col overflow-y-auto">
            {list.map((food) => (
              <li key={food.code}>
                <button
                  type="button"
                  onClick={() => save({ code: food.code })}
                  disabled={setBls.isPending}
                  className="flex w-full items-baseline gap-2 rounded px-1.5 py-1 text-left
                             text-sm hover:bg-accent-soft"
                >
                  <span className="min-w-0 flex-1">{food.name}</span>
                  <span className="font-mono text-2xs text-ink-faint">{food.code}</span>
                </button>
              </li>
            ))}
            {list.length === 0 && (
              <li className="px-1.5 py-1 text-xs text-ink-faint">
                {suggestions.isLoading ? "lädt …" : "Nichts gefunden – anders suchen"}
              </li>
            )}
          </ul>
          {!open && (
            <button
              type="button"
              className="btn-ghost btn-sm self-start"
              onClick={() => setChoosing(false)}
            >
              Abbrechen
            </button>
          )}
        </div>
      )}

      {children}
    </fieldset>
  );
}

function decimalOrNull(value: string | number): string | null {
  const text = String(value).trim().replace(",", ".");
  return text === "" ? null : text;
}
