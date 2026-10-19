/**
 * Ein Vertrag, eine Quelle (ARCHITECTURE.md §7): `schema.d.ts` wird aus
 * `/openapi.json` generiert (`npm run gen:api`). Backend-Änderungen brechen damit im
 * TS-Build, nicht erst zur Laufzeit.
 */
import createClient from "openapi-fetch";
import type { paths, components } from "./schema";

export const api = createClient<paths>({ baseUrl: "" });

export type Schemas = components["schemas"];

export type Week = Schemas["WeekOut"];
export type Slot = Schemas["SlotOut"];
export type SlotIn = Schemas["SlotIn"];
export type StandardSlot = Schemas["StandardSlotOut"];
export type Assignment = Schemas["AssignmentOut"];
export type Candidate = Schemas["CandidateOut"];
export type Score = Schemas["ScoreOut"];
export type Warning = Schemas["WarningOut"];
export type DishSummary = Schemas["DishSummary"];
export type Dish = Schemas["DishOut"];
export type DishIn = Schemas["DishIn"];
export type Article = Schemas["ArticleOut"];
export type ParsedLine = Schemas["ParsedLineOut"];
export type ShoppingList = Schemas["ShoppingListOut"];
export type ShoppingItem = Schemas["ShoppingItemOut"];
export type PushResult = Schemas["PushOut"];
export type Health = Schemas["HealthOut"];
export type SyncRun = Schemas["SyncRunOut"];
export type Settings = Schemas["SettingsOut"];
export type Offer = Schemas["OfferOut"];
export type Store = Schemas["StoreOut"];
export type StoreIn = Schemas["StoreIn"];
export type StorePatch = Schemas["StorePatch"];
export type StoreStatus = Schemas["StoreStatusOut"];
export type Chain = Schemas["Chain"];
export type Category = Schemas["CategoryOut"];
export type ArticleSuggestion = Schemas["ArticleSuggestion"];
export type DishNutrition = Schemas["DishNutritionOut"];
export type Nutrients = Schemas["NutrientsOut"];
export type Meal = Schemas["Meal"];
export type Effort = Schemas["Effort"];
export type TimeBudget = Schemas["TimeBudget"];
export type SlotSpecial = Schemas["SlotSpecial"];
export type SuitableFor = Schemas["SuitableFor"];
export type Unit = Schemas["Unit"];
export type AssignmentKind = Schemas["AssignmentKind"];

/**
 * Fehler aus dem Backend haben ein `detail`-Feld (ARCHITECTURE.md §6). 409 trägt
 * zusätzlich die aktuelle Version - der Konflikt Laptop/Handy.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly currentVersion?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isConflict() {
    return this.status === 409;
  }
}

type ErrorBody = { detail?: unknown; current_version?: number };

export function toApiError(status: number, body: unknown): ApiError {
  const payload = (body ?? {}) as ErrorBody;
  let message = `Fehler ${status}`;
  if (typeof payload.detail === "string") {
    message = payload.detail;
  } else if (Array.isArray(payload.detail)) {
    // FastAPI-Validierungsfehler: die erste Meldung reicht für einen Toast.
    const first = payload.detail[0] as { msg?: string; loc?: string[] } | undefined;
    message = first?.msg ? `${first.loc?.slice(-1) ?? ""} ${first.msg}`.trim() : message;
  }
  return new ApiError(status, message, payload.current_version);
}

/** Hebt openapi-fetch-Ergebnisse in Promises, damit TanStack Query sie kennt. */
export async function unwrap<T>(
  result: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await result;
  if (error !== undefined || !response.ok) {
    throw toApiError(response.status, error);
  }
  return data as T;
}
