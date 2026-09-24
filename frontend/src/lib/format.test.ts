/**
 * Mengen-Darstellung. Sie muss zur Backend-Formatierung passen - im Laden wird sie
 * gelesen, und 1500 g liest niemand als "1,5 kg", wenn dort 1500 g steht.
 */
import { describe, expect, it } from "vitest";
import { formatEuro, formatNumber, formatQuantity, formatScore, stars } from "./format";

describe("formatQuantity", () => {
  it("skaliert Gramm ab 1000 auf Kilo", () => {
    expect(formatQuantity("1500", "G")).toBe("1,5 kg");
    expect(formatQuantity("999", "G")).toBe("999 g");
  });

  it("skaliert Milliliter ab 1000 auf Liter", () => {
    expect(formatQuantity("1250", "ML")).toBe("1,25 l");
  });

  it("kürzt Stück ab", () => {
    expect(formatQuantity("2", "STUECK")).toBe("2 Stk");
  });

  it("nennt fehlende Mengen „nach Bedarf“ statt 0", () => {
    expect(formatQuantity(null, "G")).toBe("nach Bedarf");
  });

  it("kommt mit den Decimal-Strings des Backends zurecht", () => {
    expect(formatQuantity("250.000", "G")).toBe("250 g");
    expect(formatQuantity("0.500", "STUECK")).toBe("0,5 Stk");
  });
});

describe("formatScore", () => {
  it("zeigt das Vorzeichen und ein Komma", () => {
    expect(formatScore(12)).toBe("+12,0");
    expect(formatScore(-4.5)).toBe("-4,5");
    expect(formatScore(0)).toBe("0,0");
  });
});

describe("formatNumber", () => {
  it("schreibt deutsch und ohne Nullschwanz", () => {
    expect(formatNumber("1500")).toBe("1.500");
    expect(formatNumber("0.50")).toBe("0,5");
    expect(formatNumber(null)).toBe("");
  });
});

describe("formatEuro", () => {
  it("zeigt zwei Stellen", () => {
    expect(formatEuro("4.9")).toBe("4,90 €");
  });
});

describe("stars", () => {
  it("füllt auf fünf auf", () => {
    expect(stars(3)).toBe("★★★☆☆");
    expect(stars(null)).toBe("");
  });
});
