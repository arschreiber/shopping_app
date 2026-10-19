/**
 * Kleine Vorlieben pro Gerät ("Bilder an" am Laptop, aus am Handy) - im Browser, nicht in
 * der Datenbank. Privates Fenster oder gesperrter Speicher: dann gilt der Standard.
 */
import { useState } from "react";

const PREFIX = "mealplan.";

export function readFlag(key: string, fallback: boolean): boolean {
  try {
    const stored = window.localStorage.getItem(PREFIX + key);
    return stored === null ? fallback : stored === "1";
  } catch {
    return fallback;
  }
}

export function writeFlag(key: string, value: boolean): void {
  try {
    window.localStorage.setItem(PREFIX + key, value ? "1" : "0");
  } catch {
    // nicht merken können ist kein Fehler
  }
}

export function useStoredFlag(key: string, fallback = false): [boolean, (value: boolean) => void] {
  const [value, setValue] = useState(() => readFlag(key, fallback));
  return [
    value,
    (next: boolean) => {
      setValue(next);
      writeFlag(key, next);
    },
  ];
}
