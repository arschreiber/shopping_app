/**
 * Produktbilder der Angebote - direkt von der Quelle (Rewe, Aldi, marktguru), ohne
 * Referrer. Gespiegelt werden sie noch nicht (ARCHITECTURE.md §5).
 */
import { useState } from "react";

/** Groß im Detailfenster - geladen, sobald jemand das Fenster öffnet. */
export function ProductImage({ url }: { url: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <img
      src={url}
      alt=""
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="mx-auto max-h-48 rounded border border-line bg-surface object-contain"
    />
  );
}

/**
 * Klein neben dem Angebot in der Liste. Erst geladen, wenn die Zeile in Sicht kommt - bei
 * "alle" sind es 800 Angebote. Ohne Bild bleibt das Feld leer, damit die Zeilen bündig
 * stehen. Öffnet dasselbe wie der Name, darum kein eigener Tab-Halt.
 */
export function OfferThumb({ url, onOpen }: { url: string | null | undefined; onOpen: () => void }) {
  const [failed, setFailed] = useState(false);
  return (
    <button
      type="button"
      tabIndex={-1}
      aria-hidden
      onClick={onOpen}
      className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded
                 border border-line bg-surface sm:h-16 sm:w-16 lg:h-28 lg:w-28"
    >
      {url && !failed && (
        <img
          src={url}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
          className="h-full w-full object-contain"
        />
      )}
    </button>
  );
}
