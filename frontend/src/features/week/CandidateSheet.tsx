/**
 * Kandidatenliste für einen Slot (general_plan.md §4 "Assistierte Planung").
 *
 * Der Score *ist* die Begründung (ARCHITECTURE.md §4 Nr. 1): jede Zeile zeigt ihre
 * Beiträge, keine zweite Erklärungslogik im Frontend. Nicht zulässige Gerichte stehen
 * unten mit dem Grund - damit "warum ist mein Gericht nicht dabei?" beantwortet ist.
 */
import { useMemo, useState } from "react";
import type { Candidate, Meal, Slot } from "../../api/client";
import { IconCheck, IconLeftover, IconWarn } from "../../components/Icons";
import { Spinner } from "../../components/Primitives";
import { Sheet } from "../../components/Sheet";
import { ScoreLines } from "../../components/Warnings";
import { DAY_NAMES, hasArrived } from "../../lib/dates";
import { MEAL_LABEL, TIME_LABEL, formatScore, pluralPortions } from "../../lib/format";

export function CandidateSheet({
  open,
  slot,
  candidates,
  loading,
  onClose,
  onChoose,
  onClear,
  onCancel,
  busy,
}: {
  open: boolean;
  slot: Slot | null;
  candidates: Candidate[];
  loading: boolean;
  onClose: () => void;
  onChoose: (candidate: Candidate) => void;
  onClear: () => void;
  /** Gericht ausgefallen (true) oder doch gekocht (false). */
  onCancel: (cancelled: boolean) => void;
  busy: boolean;
}) {
  const [showBlocked, setShowBlocked] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  const { allowed, blocked } = useMemo(() => {
    return {
      allowed: candidates.filter((candidate) => candidate.eligible),
      blocked: candidates.filter((candidate) => !candidate.eligible),
    };
  }, [candidates]);

  if (!slot) return null;

  // Ausfallen kann nur ein Gericht, dessen Tag schon da ist. Davor plant man einfach um.
  const current = slot.assignment;
  const mayCancel = current?.kind === "DISH" && hasArrived(slot.date);

  const subtitle = [
    `${pluralPortions(slot.demand)} gebraucht`,
    slot.packed_portions > 0
      ? `${slot.packed_portions} ${slot.packed_fresh ? "frisch " : ""}zum Mitnehmen`
      : null,
    slot.time_budget !== "NORMAL" ? TIME_LABEL[slot.time_budget] : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Sheet
      open={open}
      title={`${DAY_NAMES[slot.day]} ${MEAL_LABEL[slot.meal]}`}
      subtitle={subtitle}
      onClose={onClose}
      footer={
        current ? (
          <div className="flex items-center justify-between gap-3">
            <span className="truncate text-sm text-ink-muted">
              aktuell: {current.dish_name}
              {current.cancelled && " · ausgefallen"}
            </span>
            <div className="flex shrink-0 gap-2">
              {mayCancel && (
                <button
                  type="button"
                  onClick={() => onCancel(!current.cancelled)}
                  disabled={busy}
                  aria-pressed={current.cancelled}
                  title={
                    current.cancelled
                      ? "Doch gekocht - zählt wieder für die Abwechslung"
                      : "Nicht gekocht - zählt nicht für die Abwechslung"
                  }
                  className="btn-secondary btn-sm"
                >
                  {current.cancelled ? "doch gekocht" : "ausgefallen"}
                </button>
              )}
              <button type="button" onClick={onClear} disabled={busy} className="btn-secondary btn-sm">
                Slot leeren
              </button>
            </div>
          </div>
        ) : null
      }
    >
      {loading ? (
        <div className="p-4">
          <Spinner label="Kandidaten werden bewertet …" />
        </div>
      ) : (
        <>
          {allowed.length === 0 && (
            <p className="px-4 py-6 text-sm text-ink-muted">
              Kein Gericht passt in diesen Slot. Mehr Gerichte erfassen oder im Raster
              anpassen, wer hier isst und mitnimmt.
            </p>
          )}

          <ul className="divide-y divide-line">
            {allowed.map((candidate) => {
              const key = candidateKey(candidate);
              const chosen = isChosen(candidate, slot);
              const isLeftover = candidate.assignment.kind === "LEFTOVER";
              return (
                <li key={key}>
                  <div
                    className={[
                      "px-4 py-3 transition-colors duration-fast",
                      chosen ? "bg-accent-soft/60" : "hover:bg-sunken/60",
                    ].join(" ")}
                  >
                    <div className="flex items-start gap-2">
                      <button
                        type="button"
                        onClick={() => onChoose(candidate)}
                        disabled={busy}
                        className="min-w-0 flex-1 text-left"
                      >
                        <span className="flex items-center gap-1.5">
                          {isLeftover && <IconLeftover className="h-3.5 w-3.5 text-accent" />}
                          <span className="truncate text-sm font-medium">{candidate.label}</span>
                          {chosen && <IconCheck className="h-3.5 w-3.5 text-accent" />}
                        </span>
                        {candidate.warnings.length > 0 && (
                          <span className="mt-1 flex items-start gap-1 text-xs text-warn">
                            <IconWarn className="mt-[2px] h-3 w-3" />
                            {candidate.warnings.join(" · ")}
                          </span>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => setExpanded(expanded === key ? null : key)}
                        aria-expanded={expanded === key}
                        className="shrink-0 rounded px-1.5 py-0.5 font-mono text-xs tabular-nums
                                   text-ink-muted hover:bg-sunken hover:text-ink"
                        title="Begründung anzeigen"
                      >
                        {formatScore(candidate.score.total)}
                      </button>
                    </div>

                    {/* Begründung: erst die Kurzform, auf Klick die Score-Beiträge. */}
                    {expanded === key ? (
                      <div className="mt-2 rounded border border-line bg-surface px-2.5 py-2">
                        <ScoreLines contributions={candidate.score.contributions} />
                      </div>
                    ) : (
                      candidate.score.reasons.length > 0 && (
                        <p className="mt-1 line-clamp-2 text-xs text-ink-muted">
                          {candidate.score.reasons.slice(0, 3).join(" · ")}
                        </p>
                      )
                    )}
                  </div>
                </li>
              );
            })}
          </ul>

          {blocked.length > 0 && (
            <div className="rule mt-2">
              <button
                type="button"
                onClick={() => setShowBlocked(!showBlocked)}
                aria-expanded={showBlocked}
                className="flex w-full items-center justify-between px-4 py-2.5 text-left"
              >
                <span className="label">
                  {blocked.length} Gerichte passen nicht
                </span>
                <span className="text-xs text-ink-faint">{showBlocked ? "verbergen" : "zeigen"}</span>
              </button>
              {showBlocked && (
                <ul className="divide-y divide-line border-t border-line">
                  {blocked.map((candidate) => (
                    <li key={candidateKey(candidate)} className="px-4 py-2">
                      <p className="text-sm text-ink-muted">{candidate.label}</p>
                      <p className="text-xs text-ink-faint">{candidate.warnings.join(" · ")}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </Sheet>
  );
}

function candidateKey(candidate: Candidate): string {
  const assignment = candidate.assignment;
  return [
    assignment.kind,
    assignment.dish_id,
    assignment.factor,
    assignment.leftover_source_day,
    assignment.leftover_source_meal,
  ].join(":");
}

function isChosen(candidate: Candidate, slot: Slot): boolean {
  const current = slot.assignment;
  if (!current) return false;
  const next = candidate.assignment;
  return (
    current.kind === next.kind &&
    current.dish_id === next.dish_id &&
    current.factor === next.factor &&
    current.leftover_source_day === next.leftover_source_day
  );
}

export type SlotRef = { day: number; meal: Meal };
