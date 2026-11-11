/**
 * Vitamine und Mineralstoffe in drei Spalten (Allgemein, Mineralstoffe, Vitamine), je eine
 * Zeile mit Balken. Dieselbe Darstellung wie im Gericht - nur ohne Aufschlüsselung nach
 * Zutaten, für Summen über mehrere Gerichte (Tag, Woche). Ein Klick führt zur
 * Artikel-Rangliste dieses Nährstoffs.
 */
import { useNavigate } from "react-router-dom";
import type { MicroValue } from "../../api/client";
import { MicroBar } from "./MicroBar";

const GROUPS = ["Allgemein", "Mineralstoffe", "Vitamine"];

export function MicroGrid({ values }: { values: MicroValue[] }) {
  // Klick auf einen Nährstoff: welche Artikel tragen am meisten davon?
  const navigate = useNavigate();
  return (
    <div className="grid gap-x-6 gap-y-3 sm:grid-cols-3">
      {GROUPS.map((group) => (
        <dl key={group} className="flex flex-col gap-1">
          <dt className="text-2xs font-medium uppercase tracking-wide text-ink-faint">{group}</dt>
          {values
            .filter((value) => value.group === group)
            .map((value) => (
              <MicroBar
                key={value.code}
                label={value.label}
                unit={value.unit}
                amount={value.amount}
                share={value.share}
                kind={value.kind}
                partial={value.partial}
                onClick={() => navigate(`/nutrients?code=${encodeURIComponent(value.code)}`)}
                clickTitle="Alle Artikel nach diesem Nährstoff sortiert"
              />
            ))}
        </dl>
      ))}
    </div>
  );
}
