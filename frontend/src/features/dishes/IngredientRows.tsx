/**
 * Zutaten eines Gerichts: Zeilenliste + Suche zum Auswählen oder Anlegen.
 *
 * Der Hauptweg ist die Suche (`ArticleCombobox`): tippen, vorhandene Zutat auswählen,
 * sonst mit genau diesem Namen anlegen. Eine Zutat *ist* ein Artikel und hat genau
 * einen Namen - keine Zweitnamen, keine Synonym-Pflege.
 *
 * Darunter liegt der Massenweg für Phase 0 (general_plan.md §5): ein Textblock, eine
 * Zeile pro Zutat. Der Parser (deterministisch, kein LLM) trennt Menge, Einheit und
 * Namen; was er sicher zuordnen kann, landet direkt in der Liste, der Rest wird
 * gefragt. Standardmäßig eingeklappt, damit die Suche der offensichtliche Weg bleibt.
 */
import { useEffect, useRef, useState } from "react";
import type { Article, ParsedLine, Unit } from "../../api/client";
import { parseIngredients, useSaveArticle } from "../../api/hooks";
import { IconCheck, IconClose, IconPlus, IconWarn } from "../../components/Icons";
import { errorText, useToast } from "../../components/Toast";
import { UNIT_LABEL } from "../../lib/format";
import { ArticleCombobox } from "./ArticleCombobox";

export type IngredientRow = {
  article_id: number;
  article_name: string;
  quantity: string | null;
  unit: Unit;
};

const UNIT_OPTIONS: Unit[] = ["G", "ML", "STUECK"];

export function IngredientRows({
  rows,
  onChange,
}: {
  rows: IngredientRow[];
  onChange: (rows: IngredientRow[]) => void;
}) {
  const [bulkOpen, setBulkOpen] = useState(false);
  const [text, setText] = useState("");
  const [parsed, setParsed] = useState<ParsedLine[] | null>(null);
  const [parsing, setParsing] = useState(false);
  const [accepted, setAccepted] = useState(0);
  const saveArticle = useSaveArticle();
  const toast = useToast();

  // Spiegel der aktuellen Zeilen: die Anlage-Aufrufe sind async, und zwei schnell
  // hintereinander ausgelöste würden sonst beide dieselbe alte Liste erweitern.
  const rowsRef = useRef(rows);
  useEffect(() => {
    rowsRef.current = rows;
  }, [rows]);

  function addArticle(article: Article, quantity: string | null = null) {
    if (rowsRef.current.some((row) => row.article_id === article.id)) return;
    const next = [
      ...rowsRef.current,
      {
        article_id: article.id,
        article_name: article.canonical_name,
        quantity,
        unit: article.unit,
      },
    ];
    rowsRef.current = next;
    onChange(next);
  }

  /** Erledigte Zeile aus Vorschlagsliste und Textblock entfernen. */
  function resolve(line: ParsedLine) {
    setParsed((current) => {
      const remaining = (current ?? []).filter((entry) => entry.raw !== line.raw);
      setText(remaining.map((entry) => entry.raw).join("\n"));
      return remaining.length > 0 ? remaining : null;
    });
  }

  async function runParse(value: string) {
    if (!value.trim()) {
      setParsed(null);
      return;
    }
    setParsing(true);
    try {
      const lines = await parseIngredients(value);
      const matched = lines.filter((line) => line.article_id !== null && !line.unit_conflict);
      const open = lines.filter((line) => line.article_id === null || line.unit_conflict);

      // Sichere Treffer landen sofort in der Liste - wer danach speichert, soll seine
      // Zeilen nicht verlieren.
      if (matched.length > 0) {
        const next = [...rowsRef.current];
        for (const line of matched) {
          if (next.some((row) => row.article_id === line.article_id)) continue;
          next.push({
            article_id: line.article_id!,
            article_name: line.article_name ?? line.name,
            quantity: line.quantity,
            unit: line.unit,
          });
        }
        rowsRef.current = next;
        onChange(next);
      }
      setParsed(open.length > 0 ? open : null);
      setText(open.map((line) => line.raw).join("\n"));
      setAccepted(matched.length);
    } catch (error) {
      toast.show(errorText(error), "error");
    } finally {
      setParsing(false);
    }
  }

  async function createFromLine(line: ParsedLine) {
    try {
      const article = await saveArticle.mutateAsync({
        body: { canonical_name: line.name, unit: line.suggested_unit },
      });
      addArticle(article, line.quantity);
      resolve(line);
    } catch (error) {
      toast.show(errorText(error), "error");
    }
  }

  const pendingNew = (parsed ?? [])
    .filter((line) => line.article_id === null)
    .map((line) => ({ ...line, suggestions: line.suggestions ?? [] }));
  const conflicts = (parsed ?? []).filter((line) => line.unit_conflict);

  return (
    <div className="flex flex-col gap-3">
      {rows.length > 0 && (
        <ul className="divide-y divide-line rounded-md border border-line">
          {rows.map((row, index) => (
            <li key={row.article_id} className="flex items-center gap-2 px-2.5 py-1.5">
              <input
                value={row.quantity ?? ""}
                placeholder="nach Bedarf"
                inputMode="decimal"
                onChange={(event) =>
                  onChange(
                    rows.map((entry, position) =>
                      position === index
                        ? { ...entry, quantity: event.target.value || null }
                        : entry,
                    ),
                  )
                }
                className="field w-24 py-1 text-right"
                aria-label={`Menge ${row.article_name}`}
              />
              <select
                value={row.unit}
                onChange={(event) =>
                  onChange(
                    rows.map((entry, position) =>
                      position === index
                        ? { ...entry, unit: event.target.value as Unit }
                        : entry,
                    ),
                  )
                }
                className="field w-20 py-1"
                aria-label={`Einheit ${row.article_name}`}
              >
                {UNIT_OPTIONS.map((unit) => (
                  <option key={unit} value={unit}>
                    {UNIT_LABEL[unit]}
                  </option>
                ))}
              </select>
              <span className="flex-1 truncate text-sm">{row.article_name}</span>
              <button
                type="button"
                aria-label={`${row.article_name} entfernen`}
                onClick={() => onChange(rows.filter((_, position) => position !== index))}
                className="btn-ghost btn-sm"
              >
                <IconClose className="h-3.5 w-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <ArticleCombobox
        onPick={(article) => addArticle(article)}
        taken={rows.map((row) => row.article_id)}
      />

      <div>
        <button
          type="button"
          onClick={() => setBulkOpen(!bulkOpen)}
          aria-expanded={bulkOpen}
          className="text-xs text-ink-muted underline-offset-2 hover:text-ink hover:underline"
        >
          {bulkOpen ? "Textblock schließen" : "Mehrere Zeilen auf einmal einfügen"}
        </button>
      </div>

      {bulkOpen && (
        <div className="rounded-md border border-line bg-sunken/40 p-2.5">
          <label className="label mb-1 block" htmlFor="ingredient-paste">
            Eine Zeile pro Zutat
          </label>
          <textarea
            id="ingredient-paste"
            value={text}
            rows={4}
            spellCheck={false}
            placeholder={"250 g Basmatireis\n200 g Hirtenkäse\n1 Zucchini\nSalz"}
            onChange={(event) => setText(event.target.value)}
            onBlur={(event) => runParse(event.target.value)}
            className="field bg-surface font-mono text-sm"
          />
          <div className="mt-1.5 flex items-center gap-2">
            <button
              type="button"
              onClick={() => runParse(text)}
              disabled={!text.trim() || parsing}
              className="btn-secondary btn-sm"
            >
              {parsing ? "erkennt …" : "Zeilen erkennen"}
            </button>
            {accepted > 0 && (
              <span className="flex items-center gap-1 text-xs text-accent">
                <IconCheck className="h-3.5 w-3.5" />
                {accepted} {accepted === 1 ? "Zeile" : "Zeilen"} übernommen
              </span>
            )}
          </div>

          {pendingNew.length > 0 && (
            <ul className="mt-2.5 flex flex-col gap-2.5 border-t border-line pt-2.5">
              {pendingNew.map((line) => (
                <li key={line.raw} className="flex flex-col gap-1">
                  <span className="text-sm font-medium">{line.name}</span>
                  {line.suggestions.length > 0 ? (
                    <>
                      <span className="text-2xs text-ink-muted">
                        Gibt es schon – meinst du das?
                      </span>
                      <span className="flex flex-wrap items-center gap-1.5">
                        {line.suggestions.map((suggestion) => (
                          <button
                            key={suggestion.article.id}
                            type="button"
                            onClick={() => {
                              addArticle(suggestion.article, line.quantity);
                              resolve(line);
                            }}
                            className="chip border-accent-line bg-accent-soft/60 text-accent
                                       hover:bg-accent-soft"
                          >
                            <IconCheck className="h-3 w-3" />
                            {suggestion.article.canonical_name}
                            <span className="text-2xs opacity-60">
                              {UNIT_LABEL[suggestion.article.unit]}
                            </span>
                          </button>
                        ))}
                        <span className="text-2xs text-ink-faint">oder</span>
                        <button
                          type="button"
                          onClick={() => createFromLine(line)}
                          disabled={saveArticle.isPending}
                          className="chip hover:border-line-strong"
                        >
                          <IconPlus className="h-3 w-3" />
                          „{line.name}“ neu anlegen
                        </button>
                      </span>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => createFromLine(line)}
                      disabled={saveArticle.isPending}
                      className="chip self-start hover:border-accent-line hover:bg-accent-soft
                                 hover:text-accent"
                    >
                      <IconPlus className="h-3 w-3" />
                      als neue Zutat anlegen
                      <span className="text-2xs opacity-70">
                        {UNIT_LABEL[line.suggested_unit]}
                      </span>
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          {conflicts.length > 0 && (
            <div className="mt-2.5 rounded border border-warn-line bg-warn-soft p-2 text-sm
                            text-warn">
              <p className="flex items-center gap-1.5 font-medium">
                <IconWarn className="h-3.5 w-3.5" />
                Einheit passt nicht zur Zutat
              </p>
              <ul className="mt-1 flex flex-col gap-0.5 text-xs">
                {conflicts.map((line) => (
                  <li key={line.raw}>
                    „{line.raw}“ – {line.article_name} wird in{" "}
                    {UNIT_LABEL[line.suggested_unit]} geführt. Zeile anpassen oder die
                    Zutat umstellen.
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
