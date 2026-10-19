/**
 * Läden (Phase 2): wo eingekauft wird, und ob dort Angebote abgerufen werden.
 *
 * Jede Zeile speichert für sich - anders als die Gewichte darunter, die gemeinsam über
 * die Leiste am Seitenende gespeichert werden. Ein Laden ist ein eigenes Ding, kein
 * Regler. Die Markt-ID gibt es nur, wo sie etwas bewirkt (Rewe, Netto).
 */
import { useState } from "react";
import type { Chain, Store } from "../../api/client";
import { useCreateStore, useDeleteStore, useStores, useUpdateStore } from "../../api/hooks";
import { IconClose } from "../../components/Icons";
import { SectionTitle, Spinner, Toggle } from "../../components/Primitives";
import { errorText, useToast } from "../../components/Toast";

const CHAINS: { value: Chain; label: string }[] = [
  { value: "EDEKA", label: "Edeka" },
  { value: "REWE", label: "Rewe" },
  { value: "NETTO_MD", label: "Netto" },
  { value: "COMBI", label: "Combi" },
  { value: "ALDI_NORD", label: "Aldi Nord" },
];

const CHAIN_HINT: Record<Chain, string> = {
  EDEKA:
    "Edeka: der Abruf nimmt den ersten Markt zur PLZ – einen bestimmten Markt kann man " +
    "nicht wählen.",
  REWE:
    "Rewe: PLZ des Markts. Die Markt-ID steht in seiner Angebots-Adresse " +
    "(rewe.de/angebote/…/241090/…).",
  NETTO_MD: "Netto: regionaler Prospekt – eine Markt-ID ist nicht nötig.",
  COMBI: "Combi: regionaler Prospekt (über marktguru).",
  ALDI_NORD: "Aldi Nord: bundesweiter Prospekt.",
};

const MARKET_ID_CHAINS: Chain[] = ["REWE", "NETTO_MD"];

type Draft = {
  name: string;
  chain: Chain;
  postal_code: string;
  market_id: string;
  offers_enabled: boolean;
  is_primary: boolean;
};

const EMPTY: Draft = {
  name: "",
  chain: "REWE",
  postal_code: "",
  market_id: "",
  offers_enabled: true,
  is_primary: false,
};

function toDraft(store: Store): Draft {
  return {
    name: store.name,
    chain: store.chain,
    postal_code: store.postal_code ?? "",
    market_id: store.market_id ?? "",
    offers_enabled: store.offers_enabled,
    is_primary: store.is_primary,
  };
}

export function StoresSection() {
  const stores = useStores();
  const [adding, setAdding] = useState(false);

  return (
    <section className="card p-4">
      <SectionTitle
        action={
          !adding && (
            <button type="button" onClick={() => setAdding(true)} className="btn-secondary btn-sm">
              Laden hinzufügen
            </button>
          )
        }
      >
        Läden
      </SectionTitle>
      <p className="mb-3 text-xs text-ink-muted">
        Wo ihr einkauft. Für Läden mit „Angebote“ holt die App montags und donnerstags früh
        den aktuellen Prospekt. Der Hauptladen ist der, in dem das meiste gekauft wird.
      </p>

      {stores.isLoading ? (
        <Spinner />
      ) : (
        <ul className="divide-y divide-line rounded-md border border-line">
          {(stores.data ?? []).map((store) => (
            // Neu aufbauen, sobald sich der gespeicherte Stand ändert - etwa wenn ein
            // anderer Laden Hauptladen wird und dieser es dadurch nicht mehr ist.
            <StoreRow key={JSON.stringify(store)} store={store} />
          ))}
          {adding && <StoreRow onDone={() => setAdding(false)} />}
          {!adding && (stores.data ?? []).length === 0 && (
            <li className="px-3 py-4 text-sm text-ink-muted">Noch kein Laden angelegt.</li>
          )}
        </ul>
      )}
    </section>
  );
}

/** Ohne `store` ist es die Zeile für einen neuen Laden. */
function StoreRow({ store, onDone }: { store?: Store; onDone?: () => void }) {
  const toast = useToast();
  const create = useCreateStore();
  const update = useUpdateStore();
  const remove = useDeleteStore();
  const saved = store ? toDraft(store) : EMPTY;
  const [draft, setDraft] = useState<Draft>(saved);
  const dirty = !store || JSON.stringify(draft) !== JSON.stringify(saved);
  const busy = create.isPending || update.isPending || remove.isPending;
  const withMarket = MARKET_ID_CHAINS.includes(draft.chain);
  const label = store?.name ?? "neuer Laden";

  function patch(changes: Partial<Draft>) {
    setDraft((current) => ({ ...current, ...changes }));
  }

  function fail(error: unknown) {
    toast.show(errorText(error), "error");
  }

  function save() {
    const market_id = withMarket ? draft.market_id.trim() : "";
    if (store) {
      update.mutate(
        { id: store.id, ...draft, market_id },
        { onError: fail, onSuccess: () => toast.show(`${draft.name} gespeichert`, "ok") },
      );
    } else {
      create.mutate(
        {
          ...draft,
          postal_code: draft.postal_code.trim() || null,
          market_id: market_id || null,
        },
        {
          onError: fail,
          onSuccess: () => {
            toast.show(`${draft.name} angelegt`, "ok");
            onDone?.();
          },
        },
      );
    }
  }

  function drop() {
    if (!store) return onDone?.();
    if (!window.confirm(`${store.name} löschen? Seine Angebote und Zuordnungen gehen mit.`)) {
      return;
    }
    remove.mutate(store.id, { onError: fail });
  }

  return (
    <li className="flex flex-col gap-2 px-3 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={draft.name}
          onChange={(event) => patch({ name: event.target.value })}
          placeholder="Name, z. B. Rewe Heinrichstraße"
          aria-label={`Name ${label}`}
          className="field min-w-0 flex-1 basis-48"
        />
        <select
          value={draft.chain}
          onChange={(event) => patch({ chain: event.target.value as Chain })}
          aria-label={`Kette ${label}`}
          className="field w-auto"
        >
          {CHAINS.map((chain) => (
            <option key={chain.value} value={chain.value}>
              {chain.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={drop}
          disabled={busy}
          title={store ? "Laden löschen" : "abbrechen"}
          aria-label={store ? `${store.name} löschen` : "neuen Laden verwerfen"}
          className="rounded p-1.5 text-ink-faint hover:bg-danger-soft hover:text-danger"
        >
          <IconClose className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <input
          value={draft.postal_code}
          onChange={(event) => patch({ postal_code: event.target.value.replace(/\D/g, "") })}
          placeholder="PLZ"
          inputMode="numeric"
          maxLength={5}
          aria-label={`PLZ ${label}`}
          className="field w-20"
        />
        {withMarket && (
          <input
            value={draft.market_id}
            onChange={(event) => patch({ market_id: event.target.value.replace(/\D/g, "") })}
            placeholder="Markt-ID"
            inputMode="numeric"
            aria-label={`Markt-ID ${label}`}
            className="field w-28"
          />
        )}
        <Toggle
          checked={draft.offers_enabled}
          onChange={(offers_enabled) => patch({ offers_enabled })}
          label="Angebote"
        />
        <Toggle
          checked={draft.is_primary}
          onChange={(is_primary) => patch({ is_primary })}
          label="Hauptladen"
        />
        {dirty && (
          <div className="ml-auto flex gap-2">
            {store && (
              <button
                type="button"
                onClick={() => setDraft(saved)}
                disabled={busy}
                className="btn-ghost btn-sm"
              >
                verwerfen
              </button>
            )}
            <button
              type="button"
              onClick={save}
              disabled={busy || !draft.name.trim()}
              className="btn-primary btn-sm"
            >
              {store ? "Speichern" : "Anlegen"}
            </button>
          </div>
        )}
      </div>

      {draft.offers_enabled && (
        <p className="text-2xs text-ink-faint">{CHAIN_HINT[draft.chain]}</p>
      )}
    </li>
  );
}
