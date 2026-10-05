/**
 * ISO-Wochen-Arithmetik. Getestet, weil sie an Jahresgrenzen gern kippt und die ganze
 * App an der Woche hängt (ARCHITECTURE.md §9: Vitest für die kleinen, riskanten Teile).
 */
import { describe, expect, it } from "vitest";
import {
  currentIsoWeek,
  formatDay,
  formatRange,
  hasArrived,
  isoWeekOf,
  mondayOf,
  parseIso,
  shiftIsoWeek,
  todayIsoDate,
} from "./dates";

describe("isoWeekOf", () => {
  it("nummeriert eine Woche mitten im Jahr", () => {
    expect(isoWeekOf(new Date(2026, 8, 9))).toBe("2026-W37");
  });

  it("zählt den 1. Januar zur Vorjahreswoche, wenn er ein Donnerstag+ ist", () => {
    // 1.1.2027 ist ein Freitag -> gehört noch zur KW 53 von 2026
    expect(isoWeekOf(new Date(2027, 0, 1))).toBe("2026-W53");
  });

  it("zählt den 31. Dezember zur KW 1 des Folgejahres, wenn nötig", () => {
    // 31.12.2024 ist ein Dienstag -> KW 1 von 2025
    expect(isoWeekOf(new Date(2024, 11, 31))).toBe("2025-W01");
  });
});

describe("mondayOf", () => {
  it("liefert den Montag der Woche", () => {
    expect(mondayOf("2026-W37").toISOString().slice(0, 10)).toBe("2026-09-07");
  });

  it("passt über die Jahresgrenze", () => {
    expect(mondayOf("2026-W53").toISOString().slice(0, 10)).toBe("2026-12-28");
  });
});

describe("shiftIsoWeek", () => {
  it("geht eine Woche vor und zurück", () => {
    expect(shiftIsoWeek("2026-W37", 1)).toBe("2026-W38");
    expect(shiftIsoWeek("2026-W37", -1)).toBe("2026-W36");
  });

  it("springt korrekt über den Jahreswechsel", () => {
    expect(shiftIsoWeek("2026-W53", 1)).toBe("2027-W01");
    expect(shiftIsoWeek("2027-W01", -1)).toBe("2026-W53");
  });

  it("ist umkehrbar", () => {
    for (const iso of ["2026-W01", "2026-W37", "2026-W52"]) {
      expect(shiftIsoWeek(shiftIsoWeek(iso, 4), -4)).toBe(iso);
    }
  });
});

describe("Darstellung", () => {
  it("zeigt die Datumsspanne innerhalb eines Monats kompakt", () => {
    expect(formatRange("2026-W37")).toBe("7. – 13. Sep. 2026");
  });

  it("nennt beide Monate, wenn die Woche sie überspannt", () => {
    expect(formatRange("2026-W40")).toBe("28. Sep. – 4. Okt. 2026");
  });

  it("formatiert einen Wochentag als Datum", () => {
    expect(formatDay("2026-W37", 0)).toBe("7.9.");
    expect(formatDay("2026-W37", 6)).toBe("13.9.");
  });
});

describe("parseIso", () => {
  it("liest Jahr und Woche", () => {
    expect(parseIso("2026-W37")).toEqual({ year: 2026, week: 37 });
  });

  it("akzeptiert Kleinschreibung", () => {
    expect(parseIso("2026-w05")).toEqual({ year: 2026, week: 5 });
  });
});

describe("currentIsoWeek", () => {
  it("liefert ein gültiges Format", () => {
    expect(currentIsoWeek()).toMatch(/^\d{4}-W\d{2}$/);
  });
});

describe("todayIsoDate", () => {
  it("nimmt den Kalendertag in Ortszeit, auch kurz nach Mitternacht", () => {
    expect(todayIsoDate(new Date(2026, 9, 5, 0, 30))).toBe("2026-10-05");
    expect(todayIsoDate(new Date(2026, 0, 9, 23, 59))).toBe("2026-01-09");
  });
});

describe("hasArrived", () => {
  const monday = new Date(2026, 9, 5, 8, 0);

  it("zählt vergangene Tage und heute, aber nicht morgen", () => {
    expect(hasArrived("2026-10-04", monday)).toBe(true);
    expect(hasArrived("2026-10-05", monday)).toBe(true);
    expect(hasArrived("2026-10-06", monday)).toBe(false);
  });
});
