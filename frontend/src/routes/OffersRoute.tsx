/**
 * Angebote (Phase 2). Ohne konfigurierte Quelle steht hier bewusst eine Erklärung
 * statt einer leeren Tabelle: die Tabellen existieren, die Quelle kommt später
 * (ARCHITECTURE.md §3, general_plan.md §7).
 */
import { useOffers } from "../api/hooks";
import { EmptyState, Spinner } from "../components/Primitives";
import { formatEuro } from "../lib/format";

export function OffersRoute() {
  const offers = useOffers();

  if (offers.isLoading) {
    return (
      <div className="p-6">
        <Spinner />
      </div>
    );
  }

  const rows = offers.data ?? [];

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 sm:p-6">
      <header>
        <h1 className="text-xl font-semibold">Angebote</h1>
        <p className="text-sm text-ink-muted">
          Edeka, Aldi Nord, Netto MD und Rewe – Abruf montags und donnerstags früh.
        </p>
      </header>

      {rows.length === 0 ? (
        <EmptyState
          title="Keine Angebotsdaten"
          hint="Phase 2 ist vorbereitet, aber noch nicht angeschlossen: sobald ein
                Korbunio-Container erreichbar ist und Läden hinterlegt sind, erscheinen
                hier die Angebote – und ihre Ersparnis fließt als Bonus in die
                Gerichte-Vorschläge ein."
        />
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line bg-sunken/60 text-left">
                <th className="px-3 py-2 font-medium text-ink-muted">Angebot</th>
                <th className="px-3 py-2 font-medium text-ink-muted">Laden</th>
                <th className="px-3 py-2 font-medium text-ink-muted">Artikel</th>
                <th className="px-3 py-2 text-right font-medium text-ink-muted">Preis</th>
                <th className="px-3 py-2 text-right font-medium text-ink-muted">spart</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((offer) => (
                <tr key={offer.offer_id} className="hover:bg-sunken/40">
                  <td className="px-3 py-2">
                    <span className="font-medium">{offer.raw_name}</span>
                    {offer.valid_to && (
                      <span className="ml-2 text-2xs text-ink-faint">bis {offer.valid_to}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-ink-muted">{offer.store_name}</td>
                  <td className="px-3 py-2">
                    {offer.article_name ?? (
                      <span className="chip py-0 text-2xs">unzugeordnet</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatEuro(offer.price)}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-accent">
                    {offer.savings ? formatEuro(offer.savings) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
