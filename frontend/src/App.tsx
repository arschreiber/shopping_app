/** App-Shell: Navigation, Routen, Fehlerhinweise. */
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useHealth } from "./api/hooks";
import { IconBook, IconBox, IconCart, IconGear, IconTag } from "./components/Icons";
import { ArticlesRoute } from "./routes/ArticlesRoute";
import { DishEditRoute } from "./routes/DishEditRoute";
import { DishesRoute } from "./routes/DishesRoute";
import { OffersRoute } from "./routes/OffersRoute";
import { SettingsRoute } from "./routes/SettingsRoute";
import { ShoppingRoute } from "./routes/ShoppingRoute";
import { WeekRoute } from "./routes/WeekRoute";
import { currentIsoWeek } from "./lib/dates";

export function App() {
  const iso = currentIsoWeek();
  return (
    <div className="flex min-h-dvh flex-col">
      <TopBar />
      <main className="flex-1 pb-16 sm:pb-0">
        <Routes>
          <Route path="/" element={<Navigate to={`/week/${iso}`} replace />} />
          <Route path="/week" element={<Navigate to={`/week/${iso}`} replace />} />
          <Route path="/week/:iso" element={<WeekRoute />} />
          <Route path="/week/:iso/list" element={<ShoppingRoute />} />
          <Route path="/list" element={<Navigate to={`/week/${iso}/list`} replace />} />
          <Route path="/dishes" element={<DishesRoute />} />
          <Route path="/dishes/:id" element={<DishEditRoute />} />
          <Route path="/articles" element={<ArticlesRoute />} />
          <Route path="/offers" element={<OffersRoute />} />
          <Route path="/settings" element={<SettingsRoute />} />
          <Route path="*" element={<Navigate to={`/week/${iso}`} replace />} />
        </Routes>
      </main>
      <BottomNav />
    </div>
  );
}

/** Die Wochen-ISO aus der URL behalten, damit „Liste“ zur richtigen Woche führt. */
function useCurrentIso(): string {
  const location = useLocation();
  const match = location.pathname.match(/\/week\/(\d{4}-W\d{2})/i);
  return match?.[1] ?? currentIsoWeek();
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "flex items-center gap-1.5 rounded px-2.5 py-1.5 text-sm transition-colors duration-fast",
    isActive
      ? "bg-accent-soft font-medium text-accent"
      : "text-ink-muted hover:bg-sunken hover:text-ink",
  ].join(" ");

function TopBar() {
  const iso = useCurrentIso();
  const health = useHealth();
  const textOnly = health.data?.sync_adapter === "text";

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-ground/90 backdrop-blur">
      <div className="flex items-center gap-1 px-3 py-2 sm:px-4">
        <NavLink to={`/week/${iso}`} className="mr-2 flex items-baseline gap-1.5">
          <span className="text-sm font-semibold tracking-tight">Wochenplan</span>
          <span className="hidden text-2xs text-ink-faint sm:inline">&amp; Einkauf</span>
        </NavLink>

        <nav className="hidden items-center gap-0.5 sm:flex">
          <NavLink to={`/week/${iso}`} className={linkClass} end>
            Woche
          </NavLink>
          <NavLink to={`/week/${iso}/list`} className={linkClass}>
            <IconCart className="h-3.5 w-3.5" />
            Liste
          </NavLink>
          <NavLink to="/dishes" className={linkClass}>
            <IconBook className="h-3.5 w-3.5" />
            Gerichte
          </NavLink>
          <NavLink to="/articles" className={linkClass}>
            Artikel
          </NavLink>
          <NavLink to="/offers" className={linkClass}>
            <IconTag className="h-3.5 w-3.5" />
            Angebote
          </NavLink>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          {textOnly && (
            <span
              className="chip hidden py-0 text-2xs sm:inline-flex"
              title="Ohne Bring!-Zugangsdaten erzeugt die App nur den Text-Export. Siehe README."
            >
              Bring! nicht verbunden
            </span>
          )}
          <NavLink to="/settings" className={linkClass} aria-label="Einstellungen">
            <IconGear className="h-4 w-4" />
          </NavLink>
        </div>
      </div>
    </header>
  );
}

/**
 * Am Handy unten: dieselben Ziele wie die Kopfzeile am Desktop. Die Einstellungen
 * erreicht man über das Zahnrad oben, das auch am Handy sichtbar bleibt.
 */
function BottomNav() {
  const iso = useCurrentIso();
  const itemClass = ({ isActive }: { isActive: boolean }) =>
    [
      "flex flex-1 flex-col items-center gap-0.5 py-2 text-2xs transition-colors duration-fast",
      isActive ? "text-accent" : "text-ink-muted",
    ].join(" ");

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-30 flex border-t border-line bg-surface/95
                 pb-[env(safe-area-inset-bottom)] backdrop-blur sm:hidden"
    >
      <NavLink to={`/week/${iso}`} className={itemClass} end>
        <span className="h-4 w-4 rounded-sm border border-current" aria-hidden="true" />
        Woche
      </NavLink>
      <NavLink to={`/week/${iso}/list`} className={itemClass}>
        <IconCart />
        Liste
      </NavLink>
      <NavLink to="/dishes" className={itemClass}>
        <IconBook />
        Gerichte
      </NavLink>
      <NavLink to="/articles" className={itemClass}>
        <IconBox />
        Artikel
      </NavLink>
      <NavLink to="/offers" className={itemClass}>
        <IconTag />
        Angebote
      </NavLink>
    </nav>
  );
}
