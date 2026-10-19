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
  NONE: "keine Zeit",
};

/** Was die Zeit für den Planer heißt - als Tooltip und im Raster-Menü. */
export const TIME_HINT: Record<TimeBudget, string> = {
  NORMAL: "jedes Gericht",
  LITTLE: "nur schnelle Gerichte oder Reste",
  NONE: "hier wird nicht gekocht - nur Reste",
};

export const TIME_SHORT: Record<TimeBudget, string> = {
  NORMAL: "normal",
  LITTLE: "wenig",
  NONE: "keine",
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

/** In welcher Einheit ein Richtpreis gilt: die Grundpreis-Einheit zur Artikel-Einheit. */
export const PRICE_UNIT: Record<Unit, string> = {
  G: "kg",
  KG: "kg",
  ML: "l",
  L: "l",
  STUECK: "Stück",
};

/** "5,96 €/kg" */
export function formatUnitPrice(
  value: string | number | null | undefined,
  unit: string | null | undefined,
): string {
  if (value === null || value === undefined || !unit) return "";
  return `${formatEuro(value)}/${unit}`;
}

// Einheit, in der Richt- und Normalpreis gelten -> Einheit der Menge
const AMOUNT_UNIT: Record<string, string> = { kg: "g", l: "ml", Stück: "Stück" };

/** Packungsgröße in der Einheit des Artikels: ("300", "kg") -> "300 g". */
export function formatPackAmount(
  amount: string | number | null | undefined,
  priceUnit: string | null | undefined,
): string {
  if (amount === null || amount === undefined || !priceUnit) return "";
  return `${formatNumber(amount)} ${AMOUNT_UNIT[priceUnit] ?? priceUnit}`;
}

/** "−0,80 €/kg ggü. normal (−16 %)" - negativ heißt: günstiger als euer Normalpreis. */
export function formatNormalDiff(
  diff: string | number | null | undefined,
  percent: number | null | undefined,
  unit: string | null | undefined,
): string {
  if (diff === null || diff === undefined || !unit) return "";
  const value = Number(diff);
  if (value === 0) return "wie normal";
  const sign = value < 0 ? "−" : "+";
  const share = percent === null || percent === undefined ? "" : ` (${sign}${Math.abs(percent)} %)`;
  return `${sign}${formatUnitPrice(Math.abs(value), unit)} ggü. normal${share}`;
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
