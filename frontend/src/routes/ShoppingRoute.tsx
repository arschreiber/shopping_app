/**
 * Einkaufsliste prüfen und nach Bring! pushen (general_plan.md §5 Phase 1).
 *
 * Der Ablauf im Laden ist: Vorhandenes abhaken → pushen → in Bring! abhaken. Deshalb ist
 * das Abhaken hier groß und mit Daumen erreichbar, und der Text-Export ist immer da -
 * er ist der Fallback, wenn Bring! bricht (ARCHITECTURE.md §5).
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import type { PushResult, ShoppingItem } from "../api/client";
import {
  useAddItem,
  useArticles,
  usePush,
  useRemoveItem,
  useShoppingList,
  useToggleHave,
} from "../api/hooks";
import { IconCart, IconCheck, IconClose, IconPlus, IconTag } from "../components/Icons";
import { EmptyState, Spinner } from "../components/Primitives";
import { errorText, useToast } from "../components/Toast";
import { currentIsoWeek, formatRange, parseIso } from "../lib/dates";

export function ShoppingRoute() {
  const params = useParams<{ iso?: string }>();
  const iso = params.iso ?? currentIsoWeek();
  const toast = useToast();

  const list = useShoppingList(iso);
  const toggle = useToggleHave(iso);
  const addItem = useAddItem(iso);
  const removeItem = useRemoveItem(iso);
  const push = usePush(iso);

  const [pushResult, setPushResult] = useState<PushResult | null>(null);
  const [adding, setAdding] = useState(false);

  if (list.isLoading) {
    return (
      <div className="p-6">
        <Spinner label="Liste wird aus dem Plan gebaut …" />
      </div>
    );
  }
  if (list.isError || !list.data) {
    return (
      <div className="p-6">
        <EmptyState title="Liste konnte nicht geladen werden" hint={errorText(list.error)} />
      </div>
    );
  }

  const data = list.data;
  const open = data.items.filter((item) => !item.have_already);
  const done = data.items.filter((item) => item.have_already);
  const { week } = parseIso(iso);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-xl font-semibold">Einkaufsliste</h1>
          <p className="text-sm text-ink-muted">
            Woche {week} · {formatRange(iso)}
          </p>
        </div>
        <span className={data.status === "SENT" ? "chip chip-accent" : "chip"}>
          {data.status === "SENT" ? "an Bring! gesendet" : "in Prüfung"}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setAdding(!adding)}
            className="btn-secondary btn-sm"
          >
            <IconPlus className="h-3.5 w-3.5" />
            Artikel
          </button>
          <button
            type="button"
            disabled={push.isPending || open.length === 0}
            onClick={() =>
              push.mutate(undefined, {
                onError: (error) => toast.show(errorText(error), "error"),
                onSuccess: (result) => {
                  setPushResult(result);
                  if (result.ok) {
                    toast.show(
                      result.adapter === "text"
                        ? "Liste erzeugt – Bring! ist nicht konfiguriert"
                        : `${result.items_sent} Artikel an Bring! gesendet`,
                      "ok",
                    );
                  } else {
                    toast.show(`Bring!-Push fehlgeschlagen: ${result.error}`, "error");
                  }
                },
              })
            }
            className="btn-primary btn-sm"
          >
            <IconCart className="h-3.5 w-3.5" />
            {push.isPending ? "sendet …" : `${open.length} an Bring!`}
          </button>
        </div>
      </header>

      {adding && <ArticlePicker onPick={(id) => addItem.mutate({ article_id: id })} />}

      {pushResult && !pushResult.ok && (
        <section className="rounded-md border border-danger-line bg-danger-soft p-3">
          <h2 className="text-sm font-medium text-danger">
            Bring! nicht erreichbar – Liste zum Kopieren
          </h2>
          <p className="mt-0.5 text-xs text-danger/80">{pushResult.error}</p>
          <textarea
            readOnly
            rows={Math.min(open.length + 2, 14)}
            value={pushResult.text_fallback ?? data.text_export}
            className="field mt-2 bg-surface font-mono text-xs"
          />
        </section>
      )}

      {data.items.length === 0 ? (
        <EmptyState
          title="Nichts einzukaufen"
          hint="Die Liste entsteht aus dem Wochenplan. Sobald Gerichte eingeplant sind,
                stehen ihre Zutaten hier – aggregiert und in einer Einheit."
        />
      ) : (
        <>
          <div className="card overflow-hidden">
            <ul className="divide-y divide-line">
              {open.map((item) => (
                <ItemRow
                  key={item.article_id}
                  item={item}
                  onToggle={() =>
                    toggle.mutate({ article_id: item.article_id, have_already: true })
                  }
                  onRemove={() => removeItem.mutate({ article_id: item.article_id })}
                />
              ))}
            </ul>
          </div>

          {done.length > 0 && (
            <section>
              <h2 className="label mb-2">Haben wir schon ({done.length})</h2>
              <div className="card overflow-hidden opacity-60">
                <ul className="divide-y divide-line">
                  {done.map((item) => (
                    <ItemRow
                      key={item.article_id}
                      item={item}
                      onToggle={() =>
                        toggle.mutate({ article_id: item.article_id, have_already: false })
                      }
                      onRemove={() => removeItem.mutate({ article_id: item.article_id })}
                    />
                  ))}
                </ul>
              </div>
            </section>
          )}

          <details className="text-sm">
            <summary className="cursor-pointer text-ink-muted hover:text-ink">
              Als Text kopieren
            </summary>
            <textarea
              readOnly
              rows={Math.min(open.length + 2, 16)}
              value={data.text_export}
              onFocus={(event) => event.currentTarget.select()}
              className="field mt-2 font-mono text-xs"
            />
          </details>
        </>
      )}
    </div>
  );
}

function ItemRow({
  item,
  onToggle,
  onRemove,
}: {
  item: ShoppingItem;
  onToggle: () => void;
  onRemove: () => void;
}) {
  return (
    <li className="flex items-center gap-3 px-3 py-2.5">
      <button
        type="button"
        role="checkbox"
        aria-checked={item.have_already}
        aria-label={`${item.article_name} ${item.have_already ? "wieder einkaufen" : "haben wir schon"}`}
        onClick={onToggle}
        className={[
          "flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors",
          "duration-fast",
          item.have_already
            ? "border-accent bg-accent text-white"
            : "border-line-strong bg-surface hover:border-accent",
        ].join(" ")}
      >
        {item.have_already && <IconCheck className="h-3 w-3" />}
      </button>

      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span
            className={[
              "truncate text-sm font-medium",
              item.have_already ? "line-through opacity-60" : "",
            ].join(" ")}
          >
            {item.article_name}
          </span>
          {item.source !== "RECIPE" && (
            <span className="chip shrink-0 py-0 text-2xs">
              {item.source === "WATCHLIST" ? "Angebot" : "manuell"}
            </span>
          )}
        </div>
        {item.offer_hint && (
          <p className="mt-0.5 flex items-center gap-1 text-2xs text-accent">
            <IconTag className="h-3 w-3" />
            {item.offer_hint}
          </p>
        )}
      </div>

      <span className="shrink-0 font-mono text-sm tabular-nums text-ink-muted">
        {item.spec_text}
      </span>

      <button
        type="button"
        aria-label={`${item.article_name} von der Liste nehmen`}
        onClick={onRemove}
        className="btn-ghost btn-sm shrink-0"
      >
        <IconClose className="h-3.5 w-3.5" />
      </button>
    </li>
  );
}

function ArticlePicker({ onPick }: { onPick: (articleId: number) => void }) {
  const [query, setQuery] = useState("");
  const articles = useArticles(query || undefined);

  return (
    <div className="card p-3">
      <label className="label mb-1 block" htmlFor="article-search">
        Artikel ergänzen
      </label>
      <input
        id="article-search"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Kaffee, Klopapier …"
        className="field"
        autoFocus
      />
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {(articles.data ?? []).slice(0, 24).map((article) => (
          <li key={article.id}>
            <button
              type="button"
              onClick={() => onPick(article.id)}
              className="chip hover:border-accent-line hover:bg-accent-soft hover:text-accent"
            >
              <IconPlus className="h-3 w-3" />
              {article.canonical_name}
              {article.is_watchlist && <span className="text-2xs opacity-60">★</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
