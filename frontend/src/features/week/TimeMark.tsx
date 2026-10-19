/**
 * Die Zeit einer Mahlzeit, platzsparend: eine Uhr bei wenig Zeit, die Reste-Schale bei
 * keiner - dort wird nicht gekocht. Normale Zeit braucht kein Zeichen.
 */
import type { TimeBudget } from "../../api/client";
import { IconClock, IconLeftover } from "../../components/Icons";
import { TIME_HINT, TIME_LABEL } from "../../lib/format";

export function TimeMark({ budget, className = "" }: { budget: TimeBudget; className?: string }) {
  if (budget === "NORMAL") return null;
  const Icon = budget === "NONE" ? IconLeftover : IconClock;
  return (
    <span
      role="img"
      aria-label={TIME_LABEL[budget]}
      title={`${TIME_LABEL[budget]} - ${TIME_HINT[budget]}`}
      className={className}
    >
      <Icon className="h-3 w-3 text-ink-muted" />
    </span>
  );
}
