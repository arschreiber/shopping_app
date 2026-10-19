/**
 * Angebote (Phase 2): die aktuellen Prospekte eurer Läden.
 *
 * Oben der Stand pro Laden - wann zuletzt abgerufen, welcher Markt, ob es geklappt hat -,
 * darunter die Angebote selbst. Zugeordnet wird automatisch; was davon noch nicht
 * bestätigt ist, steht als "automatisch" daneben und wirkt weder auf die Einkaufsliste
 * noch auf den Planer. Bestätigen und korrigieren kommt mit Stufe 2.
 *
 * "meine Artikel" zeigt nur, was für einen Artikel zählt - über dem Richtpreis nicht.
 * Ein Klick auf ein Angebot öffnet, was im Prospekt steht und woher es kommt. "Bilder"
 * zeigt das Produktbild neben jedem Angebot; gemerkt wird das pro Gerät.
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { Offer, StoreStatus } from "../api/client";
import { useFetchOffers, useOfferStatus, useOffers } from "../api/hooks";
import { EmptyState, Segmented, Spinner, Toggle } from "../components/Primitives";
import { errorText, useToast } from "../components/Toast";
import { OfferThumb } from "../features/offers/OfferImage";
import { OfferSheet } from "../features/offers/OfferSheet";
import { formatIsoDay } from "../lib/dates";
import { formatEuro, formatNormalDiff, formatPackAmount, formatUnitPrice } from "../lib/format";
import { useStoredFlag } from "../lib/storage";

type Scope = "matched" | "all";

const SCOPES: { value: Scope; label: string }[] = [
  { value: "matched", label: "meine Artikel" },
  { value: "all", label: "alle" },
];

export function OffersRoute() {
  const offers = useOffers();
  const status = useOfferStatus();
  const fetchOffers = useFetchOffers();
  const toast = useToast();
  const [scope, setScope] = useState<Scope>("matched");
  const [storeId, setStoreId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Offer | null>(null);
  const [images, setImages] = useStoredFlag("offers.images");

  const rows = offers.data ?? [];
  const stores = status.data ?? [];
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter(
      (offer) =>
        (scope === "all" || offer.counts) &&
        (storeId === null || offer.store_id === storeId) &&
        (!needle ||
          `${offer.raw_name} ${offer.brand ?? ""} ${offer.article_name ?? ""}`
            .toLowerCase()
            .includes(needle)),
    );
  }, [rows, scope, storeId, query]);

  if (offers.isLoading || status.isLoading) {
    return (
      <div className="p-6">
        <Spinner />
      </div>
    );
  }

  function runFetch() {
    fetchOffers.mutate(undefined, {
      onError: (error) => toast.show(errorText(error), "error"),
      onSuccess: (result) => {
        const failed = result.filter((store) => store.last_status !== "OK");
        toast.show(
          failed.length
            ? `Nicht geklappt: ${failed.map((store) => store.store_name).join(", ")}`
            : `${result.reduce((sum, store) => sum + store.current_count, 0)} Angebote geladen`,
          failed.length ? "error" : "ok",
        );
      },
    });
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4 p-4 sm:p-6">
      <header className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">Angebote</h1>
          <p className="text-sm text-ink-muted">
            Die aktuellen Prospekte eurer Läden – abgerufen montags und donnerstags früh.
          </p>
        </div>
        {stores.length > 0 && (
          <button
            type="button"
            onClick={runFetch}
            disabled={fetchOffers.isPending}
            className="btn-primary btn-sm"
          >
            {fetchOffers.isPending ? "ruft ab …" : "Angebote abrufen"}
          </button>
        )}
      </header>

      {stores.length === 0 ? (
        <EmptyState
          title="Noch kein Laden mit Angeboten"
          hint="Unter Einstellungen → Läden eintragen, wo ihr einkauft, und bei den Läden mit
                Prospekt „Angebote“ einschalten."
          action={
            <Link to="/settings" className="btn-secondary btn-sm">
              zu den Einstellungen
            </Link>
          }
        />
      ) : (
        <>
          {fetchOffers.isPending && (
            <Spinner label="Prospekte werden geholt – beim ersten Mal bis zu einer Minute …" />
          )}
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {stores.map((store) => (
              <StoreCard key={store.store_id} store={store} />
            ))}
          </ul>

          <div className="flex flex-wrap items-center gap-2">
            <Segmented label="Angebote" value={scope} options={SCOPES} onChange={setScope} />
            <select
              value={storeId ?? ""}
              onChange={(event) =>
                setStoreId(event.target.value ? Number(event.target.value) : null)
              }
              aria-label="Laden"
              className="field w-auto"
            >
              <option value="">alle Läden</option>
              {stores.map((store) => (
                <option key={store.store_id} value={store.store_id}>
                  {store.store_name}
                </option>
              ))}
            </select>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="suchen …"
              aria-label="Angebote durchsuchen"
              className="field min-w-0 flex-1 basis-40"
            />
            <Toggle checked={images} onChange={setImages} label="Bilder" />
          </div>

          {visible.length === 0 ? (
            <EmptyState
              title={rows.length === 0 ? "Noch keine Angebote" : "Nichts gefunden"}
              hint={
                rows.length === 0
                  ? "„Angebote abrufen“ holt die aktuellen Prospekte."
                  : scope === "matched"
                    ? "Zu deinen Artikeln passt hier nichts – unter „alle“ steht der ganze Prospekt."
                    : undefined
              }
            />
          ) : (
            <OfferTable offers={visible} images={images} onOpen={setSelected} />
          )}
        </>
      )}

      <OfferSheet offer={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function StoreCard({ store }: { store: StoreStatus }) {
  const failed = store.last_status !== null && store.last_status !== "OK";
  return (
    <li
      className={[
        "card flex flex-col gap-0.5 px-3 py-2",
        failed ? "border-danger-line" : "",
      ].join(" ")}
    >
      <span className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium">{store.store_name}</span>
        <span className="shrink-0 text-xs tabular-nums text-ink-muted">
          {store.current_count} Angebote
        </span>
      </span>
      <span className="text-2xs text-ink-faint">
        {store.last_fetched_at
          ? `abgerufen ${new Date(store.last_fetched_at).toLocaleString("de-DE", {
              weekday: "short",
              day: "numeric",
              month: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}`
          : "noch nie abgerufen"}
        {store.market_label && ` · ${store.market_label}`}
      </span>
      {failed && store.last_error && (
        <span className="text-2xs text-danger">{store.last_error}</span>
      )}
    </li>
  );
}

function OfferTable({
  offers,
  images,
  onOpen,
}: {
  offers: Offer[];
  images: boolean;
  onOpen: (offer: Offer) => void;
}) {
  return (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line bg-sunken/60 text-left">
            <th className="px-3 py-2 font-medium text-ink-muted">Angebot</th>
            <th className="hidden px-3 py-2 font-medium text-ink-muted sm:table-cell">Laden</th>
            <th className="hidden px-3 py-2 font-medium text-ink-muted md:table-cell">Artikel</th>
            <th className="px-3 py-2 text-right font-medium text-ink-muted">Preis</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {offers.map((offer) => (
            <tr key={offer.offer_id} className="align-top hover:bg-sunken/40">
              <td className="px-3 py-2">
                <div className="flex items-start gap-2 sm:gap-3">
                  {images && <OfferThumb url={offer.image_url} onOpen={() => onOpen(offer)} />}
                  <div className="min-w-0">
                    <button
                      type="button"
                      onClick={() => onOpen(offer)}
                      className="text-left font-medium hover:text-accent hover:underline"
                    >
                      {offer.raw_name}
                    </button>
                    <span className="block text-2xs text-ink-faint">
                      {[
                        offer.pack,
                        offer.valid_to ? `bis ${formatIsoDay(offer.valid_to)}` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                      <span className="sm:hidden"> · {offer.store_name}</span>
                    </span>
                    {offer.article_name && (
                      <span className="mt-0.5 block md:hidden">
                        <ArticleMatch offer={offer} />
                      </span>
                    )}
                  </div>
                </div>
              </td>
              <td className="hidden px-3 py-2 text-ink-muted sm:table-cell">{offer.store_name}</td>
              <td className="hidden px-3 py-2 md:table-cell">
                {offer.article_name ? <ArticleMatch offer={offer} /> : null}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                <span className="font-medium">{formatEuro(offer.price)}</span>
                {offer.old_price && (
                  <span className="block text-2xs text-ink-faint line-through">
                    {formatEuro(offer.old_price)}
                  </span>
                )}
                {(offer.unit_price || offer.base_price) && (
                  <span className="block text-2xs text-ink-faint">
                    {offer.unit_price
                      ? formatUnitPrice(offer.unit_price, offer.unit_price_unit)
                      : offer.base_price}
                  </span>
                )}
                {offer.compared_via_piece && (
                  <span
                    className="block text-2xs text-ink-faint"
                    title="über das Stückgewicht des Artikels umgerechnet"
                  >
                    ≈ {formatUnitPrice(offer.compared_price, offer.article_price_unit)}
                  </span>
                )}
                {offer.normal_diff !== null && offer.normal_diff !== undefined && (
                  <span
                    className={[
                      // Auf dem Handy darf es umbrechen - sonst ragt die Tabelle mit Bildern
                      // über den Rand.
                      "block text-2xs sm:whitespace-nowrap",
                      Number(offer.normal_diff) < 0 ? "text-accent" : "text-warn",
                    ].join(" ")}
                  >
                    {formatNormalDiff(
                      offer.normal_diff,
                      offer.normal_diff_percent,
                      offer.article_price_unit,
                    )}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ArticleMatch({ offer }: { offer: Offer }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-sm">
      <span className={offer.counts ? "" : "text-ink-faint line-through"}>
        {offer.article_name}
      </span>
      {offer.price_verdict === "too_expensive" && (
        <span
          className="chip border-warn-line bg-warn-soft py-0 text-2xs text-warn"
          title="Grundpreis über dem Richtpreis des Artikels – zählt nicht"
        >
          über Richtpreis
        </span>
      )}
      {offer.price_verdict === "unknown" && (
        <span
          className="chip border-warn-line bg-warn-soft py-0 text-2xs text-warn"
          title="Grundpreis nicht mit dem Richtpreis vergleichbar – zählt nicht"
        >
          Grundpreis?
        </span>
      )}
      {offer.pack_verdict === "too_small" && (
        <span
          className="chip border-warn-line bg-warn-soft py-0 text-2xs text-warn"
          title={`${formatPackAmount(offer.offer_amount, offer.article_price_unit)} – zählt erst ab ${formatPackAmount(offer.min_offer_amount, offer.article_price_unit)}`}
        >
          Packung zu klein
        </span>
      )}
      {offer.pack_verdict === "unknown" && (
        <span
          className="chip border-warn-line bg-warn-soft py-0 text-2xs text-warn"
          title={`Packungsgröße unbekannt – zählt erst ab ${formatPackAmount(offer.min_offer_amount, offer.article_price_unit)}`}
        >
          Packung?
        </span>
      )}
      {!offer.match_confirmed && (
        <span
          className="chip py-0 text-2xs"
          title="automatisch zugeordnet, noch nicht bestätigt – wirkt noch nicht auf Liste und Planer"
        >
          automatisch
        </span>
      )}
    </span>
  );
}
