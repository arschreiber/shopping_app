/**
 * Zutaten-Suche mit Anlegen (der Weg, den man beim Erfassen tatsächlich geht).
 *
 * Tippen zeigt vorhandene Zutaten darunter an - wer "Reis" eingibt und "Reis" schon
 * hat, sieht es und wählt es aus. Erst wenn nichts passt, entsteht eine neue Zutat mit
 * genau diesem Namen. Es gibt *keine* Zweitnamen: eine Zutat wird über ihren einen
 * Namen identifiziert, sonst weiß nach ein paar Wochen niemand mehr, was wo hängt.
 *
 * Tastatur: ↑/↓ wählt, Enter übernimmt, Esc schließt - beim Eintippen von 30-50
 * Gerichten zählt jeder Handgriff (general_plan.md §5 Phase 0).
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { Article, Unit } from "../../api/client";
import { suggestArticles, useSaveArticle } from "../../api/hooks";
import { IconPlus } from "../../components/Icons";
import { errorText, useToast } from "../../components/Toast";
import { UNIT_LABEL } from "../../lib/format";

const UNITS: Unit[] = ["G", "ML", "STUECK"];

type Hit = { article: Article; score: number };

export function ArticleCombobox({
  onPick,
  taken,
}: {
  onPick: (article: Article) => void;
  /** Schon in diesem Gericht verwendete Zutaten - werden als solche markiert. */
  taken: number[];
}) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [newUnit, setNewUnit] = useState<Unit>("G");
  const [loading, setLoading] = useState(false);
  const saveArticle = useSaveArticle();
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const trimmed = query.trim();

  // Debounce: 150 ms reichen, damit Tippen nicht bei jedem Zeichen eine Anfrage auslöst.
  useEffect(() => {
    if (!trimmed) {
      setHits([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(async () => {
      try {
        const result = await suggestArticles(trimmed);
        if (!cancelled) setHits(result as Hit[]);
      } catch {
        if (!cancelled) setHits([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 150);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [trimmed]);

  const exact = useMemo(
    () =>
      hits.some(
        (hit) => hit.article.canonical_name.toLowerCase() === trimmed.toLowerCase(),
      ),
    [hits, trimmed],
  );

  // Die Option "neu anlegen" ist die letzte Zeile der Liste - so ist sie mit derselben
  // Tastenfolge erreichbar wie die Treffer.
  const options = useMemo(
    () => [
      ...hits.map((hit) => ({ kind: "article" as const, hit })),
      ...(trimmed && !exact ? [{ kind: "create" as const, hit: null }] : []),
    ],
    [hits, trimmed, exact],
  );

  useEffect(() => setActive(0), [options.length]);

  function reset() {
    setQuery("");
    setHits([]);
    setOpen(false);
    inputRef.current?.focus();
  }

  function choose(index: number) {
    const option = options[index];
    if (!option) return;
    if (option.kind === "article") {
      onPick(option.hit.article);
      reset();
      return;
    }
    createNew();
  }

  async function createNew() {
    if (!trimmed) return;
    try {
      const article = await saveArticle.mutateAsync({
        body: { canonical_name: trimmed, unit: newUnit },
      });
      onPick(article);
      toast.show(`„${article.canonical_name}“ angelegt`, "ok");
      reset();
    } catch (error) {
      toast.show(errorText(error), "error");
    }
  }

  return (
    <div className="relative">
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          value={query}
          role="combobox"
          aria-expanded={open && options.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          placeholder="Zutat suchen oder anlegen …"
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setOpen(true);
              setActive((current) => Math.min(current + 1, options.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((current) => Math.max(current - 1, 0));
            } else if (event.key === "Enter") {
              event.preventDefault();
              choose(active);
            } else if (event.key === "Escape") {
              setOpen(false);
            }
          }}
          className="field"
        />
        {trimmed && !exact && (
          <select
            value={newUnit}
            onChange={(event) => setNewUnit(event.target.value as Unit)}
            aria-label="Einheit für eine neue Zutat"
            title="Einheit, falls die Zutat neu angelegt wird"
            className="field w-20 py-1.5"
          >
            {UNITS.map((unit) => (
              <option key={unit} value={unit}>
                {UNIT_LABEL[unit]}
              </option>
            ))}
          </select>
        )}
      </div>

      {open && (trimmed.length > 0 || hits.length > 0) && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-md border
                     border-line bg-surface py-1 shadow-pop"
        >
          {loading && options.length === 0 && (
            <li className="px-3 py-2 text-sm text-ink-faint">sucht …</li>
          )}
          {options.map((option, index) => {
            const highlighted = index === active;
            if (option.kind === "create") {
              return (
                <li key="create" role="option" aria-selected={highlighted}>
                  <button
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => choose(index)}
                    onMouseEnter={() => setActive(index)}
                    disabled={saveArticle.isPending}
                    className={[
                      "flex w-full items-center gap-2 px-3 py-2 text-left text-sm",
                      highlighted ? "bg-accent-soft text-accent" : "text-ink-muted",
                    ].join(" ")}
                  >
                    <IconPlus className="h-3.5 w-3.5" />
                    <span className="flex-1 truncate">
                      „{trimmed}“ als neue Zutat anlegen
                    </span>
                    <span className="text-2xs opacity-70">{UNIT_LABEL[newUnit]}</span>
                  </button>
                </li>
              );
            }
            const article = option.hit.article;
            const already = taken.includes(article.id);
            return (
              <li key={article.id} role="option" aria-selected={highlighted}>
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(index)}
                  onMouseEnter={() => setActive(index)}
                  disabled={already}
                  className={[
                    "flex w-full items-center gap-2 px-3 py-2 text-left text-sm",
                    highlighted ? "bg-accent-soft" : "",
                    already ? "opacity-45" : "",
                  ].join(" ")}
                >
                  <span className="flex-1 truncate font-medium">
                    {article.canonical_name}
                  </span>
                  {article.is_staple && (
                    <span className="text-2xs text-ink-faint">Vorrat</span>
                  )}
                  <span className="text-2xs text-ink-faint">
                    {UNIT_LABEL[article.unit]}
                  </span>
                  {already && <span className="text-2xs text-ink-faint">schon drin</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
