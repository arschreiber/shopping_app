/**
 * Rückmeldungen für Aktionen, die fehlschlagen können - Push nach Bring!, 409-Konflikte,
 * erschöpfter Gerichte-Pool. Absichtlich kein Fehler-Banner irgendwo im Layout: der
 * Hinweis erscheint dort, wo geklickt wurde, und verschwindet wieder.
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { IconCheck, IconClose, IconWarn } from "./Icons";

type Tone = "ok" | "error" | "info";
type Toast = { id: number; tone: Tone; text: string };

const ToastContext = createContext<{
  show: (text: string, tone?: Tone) => void;
} | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const show = useCallback((text: string, tone: Tone = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, tone, text }]);
    window.setTimeout(
      () => setToasts((current) => current.filter((toast) => toast.id !== id)),
      tone === "error" ? 8000 : 4000,
    );
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col
                      items-center gap-2 p-4 sm:items-end">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role="status"
            className={[
              "pointer-events-auto flex max-w-md items-start gap-2 rounded-md border px-3 py-2",
              "text-sm shadow-pop",
              toast.tone === "error"
                ? "border-danger-line bg-danger-soft text-danger"
                : toast.tone === "ok"
                  ? "border-accent-line bg-accent-soft text-accent"
                  : "border-line bg-surface text-ink",
            ].join(" ")}
          >
            {toast.tone === "error" ? (
              <IconWarn className="mt-0.5 h-4 w-4" />
            ) : toast.tone === "ok" ? (
              <IconCheck className="mt-0.5 h-4 w-4" />
            ) : null}
            <span className="flex-1 whitespace-pre-wrap">{toast.text}</span>
            <button
              type="button"
              aria-label="Ausblenden"
              onClick={() =>
                setToasts((current) => current.filter((entry) => entry.id !== toast.id))
              }
              className="opacity-60 hover:opacity-100"
            >
              <IconClose className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast außerhalb des ToastProvider");
  return context;
}

/** Fehlermeldungen aus `ApiError` menschlich anzeigen. */
export function errorText(error: unknown): string {
  if (error && typeof error === "object" && "message" in error) {
    return String((error as Error).message);
  }
  return "Unbekannter Fehler";
}
