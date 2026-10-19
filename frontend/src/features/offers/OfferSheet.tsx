/**
 * Ein Angebot nachprüfen: was im Prospekt steht, woher es kommt, und warum es für einen
 * Artikel zählt oder nicht.
 */
import type { ReactNode } from "react";
import type { Offer } from "../../api/client";
import { Sheet } from "../../components/Sheet";
import { formatIsoDay } from "../../lib/dates";
import {
  formatEuro,
  formatNormalDiff,
  formatNumber,
  formatPackAmount,
  formatUnitPrice,
} from "../../lib/format";
import { ProductImage } from "./OfferImage";

export function OfferSheet({ offer, onClose }: { offer: Offer | null; onClose: () => void }) {
  if (!offer) return null;
  return (
    <Sheet
      open
      title={offer.raw_name}
      subtitle={[offer.brand, offer.store_name].filter(Boolean).join(" · ")}
      onClose={onClose}
    >
      <div className="flex flex-col gap-5 px-4 py-4">
        {offer.image_url && <ProductImage key={offer.offer_id} url={offer.image_url} />}

        <section>
          <h3 className="label mb-1.5">Im Prospekt</h3>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <Row label="Preis">
              <span className="font-medium">{formatEuro(offer.price)}</span>
              {offer.old_price && (
                <span className="ml-2 text-ink-faint line-through">
                  {formatEuro(offer.old_price)}
                </span>
              )}
            </Row>
            <Row label="Grundpreis">
              {offer.unit_price
                ? formatUnitPrice(offer.unit_price, offer.unit_price_unit)
                : <span className="text-ink-faint">nicht bestimmbar</span>}
              {offer.base_price && !offer.unit_price && (
                <span className="ml-2 text-ink-faint">({offer.base_price})</span>
              )}
            </Row>
            {offer.pack && <Row label="Packung">{offer.pack}</Row>}
            <Row label="gültig">{validity(offer)}</Row>
            {offer.description && <Row label="Text">„{offer.description}“</Row>}
            {offer.category && <Row label="Warengruppe">{offer.category}</Row>}
          </dl>
        </section>

        <section>
          <h3 className="label mb-1.5">Für deine Artikel</h3>
          <Verdict offer={offer} />
        </section>

        <section>
          <h3 className="label mb-1.5">Quelle</h3>
          <p className="text-sm">{sourceText(offer.source_detail)}</p>
          {offer.market_label && <p className="text-sm text-ink-muted">{offer.market_label}</p>}
          {offer.fetched_at && (
            <p className="text-xs text-ink-faint">
              abgerufen{" "}
              {new Date(offer.fetched_at).toLocaleString("de-DE", {
                weekday: "short",
                day: "numeric",
                month: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {sourceLinks(offer).map((link) => (
              <ExternalLink key={link.href} href={link.href}>
                {link.label}
              </ExternalLink>
            ))}
          </div>
        </section>
      </div>
    </Sheet>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-ink-muted">{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

function Verdict({ offer }: { offer: Offer }) {
  if (!offer.article_name) {
    return <p className="text-sm text-ink-muted">keinem Artikel zugeordnet</p>;
  }
  const target = formatUnitPrice(offer.target_price, offer.article_price_unit);
  // Der Angebotspreis in der Einheit des Artikels - bei Stück-Angeboten umgerechnet
  const compared = formatUnitPrice(offer.compared_price, offer.article_price_unit);
  return (
    <div className="flex flex-col gap-0.5 text-sm">
      <p>
        <span className="font-medium">{offer.article_name}</span>{" "}
        <span className="text-ink-muted">
          {offer.match_confirmed ? "– bestätigt" : "– automatisch zugeordnet, noch nicht bestätigt"}
        </span>
      </p>
      {offer.price_verdict === null && (
        <p className="text-ink-muted">
          kein Richtpreis{offer.counts ? " – das Angebot zählt" : ""}
        </p>
      )}
      {offer.compared_via_piece && (
        <p className="text-ink-muted">
          {formatUnitPrice(offer.unit_price, offer.unit_price_unit)} ≈ {compared} (umgerechnet,
          1 Stück ≈ {formatNumber(offer.piece_size)} {offer.article_price_unit === "l" ? "ml" : "g"})
        </p>
      )}
      {offer.price_verdict === "ok" && (
        <p className="text-accent">
          {compared} hält den Richtpreis{target ? ` von ${target}` : ""}
          {offer.counts ? " – zählt" : ""}
        </p>
      )}
      {offer.price_verdict === "too_expensive" && (
        <p className="text-warn">
          {compared} liegt über dem Richtpreis{target ? ` von ${target}` : ""} – zählt nicht
        </p>
      )}
      {offer.price_verdict === "unknown" && (
        <p className="text-warn">
          Grundpreis nicht mit dem Richtpreis vergleichbar – zählt nicht
          {offer.unit_price_unit === "Stück" && !offer.piece_size
            ? " (am Artikel fehlt das Stückgewicht)"
            : ""}
        </p>
      )}
      <PackSize offer={offer} />
      <NormalPrice offer={offer} />
    </div>
  );
}

/** Mindestpackung des Artikels: "300 g – zählt erst ab 400 g". */
function PackSize({ offer }: { offer: Offer }) {
  const minimum = formatPackAmount(offer.min_offer_amount, offer.article_price_unit);
  const amount = formatPackAmount(offer.offer_amount, offer.article_price_unit);
  if (offer.pack_verdict === "too_small") {
    return <p className="text-warn">Packung {amount} – zählt erst ab {minimum}</p>;
  }
  if (offer.pack_verdict === "unknown") {
    return <p className="text-warn">Packungsgröße unbekannt – zählt erst ab {minimum}</p>;
  }
  if (offer.pack_verdict === "ok") {
    return (
      <p className="text-ink-muted">
        Packung {amount} – ab {minimum} gewünscht
      </p>
    );
  }
  return null;
}

/** Was das Angebot gegenüber dem normalen Einkauf bringt - unabhängig vom Richtpreis. */
function NormalPrice({ offer }: { offer: Offer }) {
  if (!offer.regular_unit_price) {
    return <p className="text-ink-faint">kein Normalpreis hinterlegt</p>;
  }
  const regular = formatUnitPrice(offer.regular_unit_price, offer.article_price_unit);
  if (offer.normal_diff === null || offer.normal_diff === undefined) {
    return (
      <p className="text-ink-muted">Normalpreis {regular} – mit diesem Angebot nicht vergleichbar</p>
    );
  }
  const cheaper = Number(offer.normal_diff) < 0;
  return (
    <p className={cheaper ? "text-accent" : "text-ink-muted"}>
      {formatNormalDiff(offer.normal_diff, offer.normal_diff_percent, offer.article_price_unit)}{" "}
      (Normalpreis {regular})
    </p>
  );
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="btn-secondary btn-sm">
      {children} ↗
    </a>
  );
}

function validity(offer: Offer): string {
  const from = offer.valid_from ? formatIsoDay(offer.valid_from) : null;
  const to = offer.valid_to ? formatIsoDay(offer.valid_to) : null;
  if (from && to) return `${from} – ${to}`;
  if (to) return `bis ${to}`;
  return "unbekannt";
}

/**
 * Die Quellen verlinken kein einzelnes Angebot, sondern den Prospekt (marktguru) bzw. die
 * Angebotsseite des Markts (Rewe) - so heißen die Knöpfe auch. Bei marktguru-Läden ist
 * die Filialseite keine Quelle der Angebote und bleibt weg; doppelte Adressen auch.
 */
function sourceLinks(offer: Offer): { href: string; label: string }[] {
  const urls = [offer.source_url, offer.source_detail === "offiziell" ? offer.market_url : null];
  const unique = [...new Set(urls.filter((url): url is string => Boolean(url)))];
  return unique.map((href) => ({
    href,
    label: href.includes("marktguru.") ? "Prospekt bei marktguru" : "Angebotsseite des Markts",
  }));
}

function sourceText(detail: string | null | undefined): string {
  if (detail === "offiziell") return "direkt von der Angebotsseite des Händlers";
  if (detail === "Marktguru") return "aus dem regionalen Prospekt bei marktguru";
  return detail ? `über Korbunio (${detail})` : "über Korbunio";
}
