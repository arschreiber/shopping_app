/**
 * Am Handy: "Artikel | Nährwerte" oben auf beiden Seiten. Die untere Leiste hat schon
 * fünf Ziele - ein sechstes würde alle Beschriftungen zusammendrücken. Am Laptop steht
 * "Nährwerte" als eigener Tab in der Kopfzeile, dort ist diese Leiste ausgeblendet.
 */
import { NavLink } from "react-router-dom";

const tabClass = ({ isActive }: { isActive: boolean }) =>
  [
    "flex-1 px-3 py-1.5 text-center text-sm transition-colors duration-fast",
    isActive ? "bg-accent-soft font-medium text-accent" : "text-ink-muted",
  ].join(" ");

export function ArticleTabs() {
  return (
    <nav
      aria-label="Artikel oder Nährwerte"
      className="flex overflow-hidden rounded border border-line bg-surface sm:hidden"
    >
      <NavLink to="/articles" className={tabClass}>
        Artikel
      </NavLink>
      <NavLink to="/nutrients" className={(state) => `${tabClass(state)} border-l border-line`}>
        Nährwerte
      </NavLink>
    </nav>
  );
}
