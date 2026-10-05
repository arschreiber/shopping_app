/** Deutsche Beschriftungen an *einer* Stelle - die Enums kommen englisch aus der API. */
import type { Effort, Meal, SlotSpecial, SuitableFor, TimeBudget, Unit } from "../api/client";

export const MEAL_LABEL: Record<Meal, string> = { LUNCH: "Mittag", DINNER: "Abend" };

export const EFFORT_LABEL: Record<Effort, string> = {
  NORMAL: "normal",
  QUICK: "schnell",
};

export const EFFORT_HINT: Record<Effort, string> = {
  NORMAL: "braucht normale Zeit",
  QUICK: "unter 20 Minuten - passt auch an Tagen mit wenig Zeit",
};

export const TIME_LABEL: Record<TimeBudget, string> = {
  NORMAL: "normale Zeit",
  LITTLE: "wenig Zeit",
};

export const TIME_SHORT: Record<TimeBudget, string> = {
  NORMAL: "normal",
  LITTLE: "wenig",
};

/** Wie oft ein Gericht auf einmal gekocht wird - dieselben Wörter wie im Planer. */
export const FACTOR_WORD: Record<number, string> = { 2: "doppelt", 3: "dreifach" };

export const SPECIAL_LABEL: Record<SlotSpecial, string> = {
  NONE: "normal",
  EATING_OUT: "auswärts",
  FROM_PANTRY: "aus Vorhandenem",
};

export const SUITABLE_LABEL: Record<SuitableFor, string> = {
  LUNCH: "nur Mittag",
  DINNER: "nur Abend",
  BOTH: "Mittag & Abend",
};

export const UNIT_LABEL: Record<Unit, string> = {
  STUECK: "Stück",
  G: "g",
  KG: "kg",
  ML: "ml",
  L: "l",
};

export const AXIS_LABEL: Record<string, string> = {
  SIDE: "Beilage",
  PROTEIN: "Protein",
  CUISINE: "Küche",
};

/** Zahlen deutsch, ohne Nullschwanz. */
export function formatNumber(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const asNumber = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(asNumber)) return String(value);
  return asNumber.toLocaleString("de-DE", { maximumFractionDigits: 2 });
}

export function formatQuantity(
  quantity: string | number | null | undefined,
  unit: Unit,
): string {
  if (quantity === null || quantity === undefined) return "nach Bedarf";
  const amount = typeof quantity === "string" ? Number(quantity) : quantity;
  if (unit === "G" && amount >= 1000) return `${formatNumber(amount / 1000)} kg`;
  if (unit === "ML" && amount >= 1000) return `${formatNumber(amount / 1000)} l`;
  return `${formatNumber(amount)} ${unit === "STUECK" ? "Stk" : UNIT_LABEL[unit]}`;
}

export function formatScore(total: number): string {
  return `${total > 0 ? "+" : ""}${total.toFixed(1).replace(".", ",")}`;
}

export function formatEuro(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return "";
  const amount = typeof value === "string" ? Number(value) : value;
  return `${amount.toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`;
}

export function stars(rating: number | null | undefined): string {
  return rating ? "★".repeat(rating) + "☆".repeat(5 - rating) : "";
}

export function pluralPortions(count: number): string {
  return `${count} ${count === 1 ? "Portion" : "Portionen"}`;
}
