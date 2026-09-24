/**
 * Bottom-Sheet am Handy, seitliches Panel am Laptop (ARCHITECTURE.md §7).
 * Eine Komponente für beide, weil der Inhalt derselbe ist - nur die Kante wechselt.
 */
import { useEffect, useRef, type ReactNode } from "react";
import { IconClose } from "./Icons";

export function Sheet({
  open,
  title,
  subtitle,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    // Fokus ins Panel, damit Tastaturbedienung dort weiterläuft.
    panel.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex items-end sm:items-stretch sm:justify-end">
      <button
        type="button"
        aria-label="Schließen"
        onClick={onClose}
        className="absolute inset-0 bg-ink/20 backdrop-blur-[1px]"
      />
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative flex max-h-[85dvh] w-full flex-col border-line bg-surface
                   shadow-sheet sm:h-full sm:max-h-none sm:w-[26rem] sm:border-l
                   rounded-t-xl sm:rounded-none"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold">{title}</h2>
            {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
          </div>
          <button type="button" onClick={onClose} className="btn-ghost btn-sm -mr-1.5 -mt-0.5">
            <IconClose />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{children}</div>
        {footer && <footer className="border-t border-line px-4 py-3">{footer}</footer>}
      </div>
    </div>
  );
}
