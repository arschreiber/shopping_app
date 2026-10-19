/** "Bilder an" wird pro Gerät gemerkt - und ein gesperrter Speicher bricht nichts. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFlag, writeFlag } from "./storage";

function fakeStorage() {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
  };
}

afterEach(() => vi.unstubAllGlobals());

describe("gemerkte Schalter", () => {
  it("gilt der Standard, bis jemand umschaltet", () => {
    vi.stubGlobal("window", { localStorage: fakeStorage() });
    expect(readFlag("offers.images", false)).toBe(false);
    writeFlag("offers.images", true);
    expect(readFlag("offers.images", false)).toBe(true);
    writeFlag("offers.images", false);
    expect(readFlag("offers.images", true)).toBe(false);
  });

  it("bricht nicht, wenn der Browser nichts speichern lässt", () => {
    const blocked = {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("QuotaExceededError");
      },
    };
    vi.stubGlobal("window", { localStorage: blocked });
    expect(() => writeFlag("offers.images", true)).not.toThrow();
    expect(readFlag("offers.images", false)).toBe(false);
  });
});
