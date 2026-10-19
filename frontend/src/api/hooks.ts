/** TanStack-Query-Hooks. Eine Datei, damit Cache-Keys und Invalidierung zusammenliegen. */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { api, unwrap } from "./client";
import type {
  Article,
  DishNutrition,
  Candidate,
  Category,
  Dish,
  DishIn,
  DishSummary,
  Health,
  Meal,
  Offer,
  ParsedLine,
  Settings,
  ShoppingList,
  SlotIn,
  StandardSlot,
  Store,
  StoreIn,
  StorePatch,
  StoreStatus,
  SyncRun,
  Week,
} from "./client";

export const keys = {
  week: (iso: string) => ["week", iso] as const,
  candidates: (iso: string, day: number, meal: Meal) =>
    ["candidates", iso, day, meal] as const,
  dishes: (q?: string) => ["dishes", q ?? ""] as const,
  dish: (id: number) => ["dish", id] as const,
  articles: (q?: string) => ["articles", q ?? ""] as const,
  categories: ["categories"] as const,
  shopping: (iso: string) => ["shopping", iso] as const,
  health: ["health"] as const,
  runs: ["sync-runs"] as const,
  settings: ["settings"] as const,
  standardWeek: ["settings", "standard-week"] as const,
  offers: ["offers"] as const,
  offerStatus: ["offers", "status"] as const,
  stores: ["stores"] as const,
};

// ------------------------------------------------------------------------------- Woche

export function useWeek(iso: string, options?: Partial<UseQueryOptions<Week>>) {
  return useQuery({
    queryKey: keys.week(iso),
    queryFn: () => unwrap(api.GET("/api/weeks/{iso}", { params: { path: { iso } } })),
    ...options,
  });
}

export function useCandidates(iso: string, day: number, meal: Meal, enabled: boolean) {
  return useQuery({
    queryKey: keys.candidates(iso, day, meal),
    enabled,
    queryFn: () =>
      unwrap<Candidate[]>(
        api.GET("/api/weeks/{iso}/slots/{day}/{meal}/candidates", {
          params: { path: { iso, day, meal }, query: { include_ineligible: true } },
        }),
      ),
  });
}

/** Alle Wochen-Mutationen liefern die neue Woche zurück - ein Refetch entfällt. */
function useWeekMutation<TVars>(
  iso: string,
  run: (vars: TVars) => Promise<Week>,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (week) => {
      client.setQueryData(keys.week(iso), week);
      client.invalidateQueries({ queryKey: keys.shopping(iso) });
      // Der Plan ist zugleich der Koch-Verlauf: "vor N Wo." bei den Gerichten und die
      // Abwechslung in den Kandidaten der anderen Wochen hängen an ihm.
      client.invalidateQueries({ queryKey: ["candidates"] });
      client.invalidateQueries({ queryKey: ["dishes"] });
      client.invalidateQueries({ queryKey: ["dish"] });
    },
  });
}

export function useSaveGrid(iso: string) {
  return useWeekMutation<{ slots: SlotIn[]; version: number }>(iso, (vars) =>
    unwrap(
      api.PUT("/api/weeks/{iso}/grid", {
        params: { path: { iso } },
        body: { slots: vars.slots, version: vars.version },
      }),
    ),
  );
}

export function usePropose(iso: string) {
  return useWeekMutation<{ onlyEmpty?: boolean; version?: number }>(iso, (vars) =>
    unwrap(
      api.POST("/api/weeks/{iso}/propose", {
        params: { path: { iso } },
        body: {
          keep_pins: true,
          only_empty: vars.onlyEmpty ?? false,
          version: vars.version ?? null,
        },
      }),
    ),
  );
}

export function useReroll(iso: string) {
  return useWeekMutation<{ day: number; meal: Meal }>(iso, (vars) =>
    unwrap(
      api.POST("/api/weeks/{iso}/slots/{day}/{meal}/reroll", {
        params: { path: { iso, day: vars.day, meal: vars.meal } },
      }),
    ),
  );
}

export type AssignmentPayload = {
  day: number;
  meal: Meal;
  kind: "DISH" | "LEFTOVER" | "PANTRY" | "EMPTY";
  dish_id?: number | null;
  factor?: number; // 2 = doppelt, 3 = dreifach gekocht
  leftover_source_day?: number | null;
  leftover_source_meal?: Meal | null;
  portions_used?: number | null;
};

export function useAssign(iso: string) {
  return useWeekMutation<AssignmentPayload>(iso, ({ day, meal, ...body }) =>
    unwrap(
      api.PUT("/api/weeks/{iso}/slots/{day}/{meal}/assignment", {
        params: { path: { iso, day, meal } },
        body: {
          kind: body.kind,
          dish_id: body.dish_id ?? null,
          factor: body.factor ?? 1,
          leftover_source_day: body.leftover_source_day ?? null,
          leftover_source_meal: body.leftover_source_meal ?? null,
          portions_used: body.portions_used ?? null,
          version: null,
        },
      }),
    ),
  );
}

export function useClearSlot(iso: string) {
  return useWeekMutation<{ day: number; meal: Meal }>(iso, ({ day, meal }) =>
    unwrap(
      api.DELETE("/api/weeks/{iso}/slots/{day}/{meal}/assignment", {
        params: { path: { iso, day, meal } },
      }),
    ),
  );
}

export function usePin(iso: string) {
  return useWeekMutation<{ day: number; meal: Meal; pinned: boolean }>(
    iso,
    ({ day, meal, pinned }) =>
      unwrap(
        api.PUT("/api/weeks/{iso}/slots/{day}/{meal}/pin", {
          params: { path: { iso, day, meal } },
          body: { pinned },
        }),
      ),
  );
}

/** Gericht ausgefallen (oder doch gekocht) - zählt dann nicht für die Abwechslung. */
export function useSetCancelled(iso: string) {
  return useWeekMutation<{ day: number; meal: Meal; cancelled: boolean }>(
    iso,
    ({ day, meal, cancelled }) =>
      unwrap(
        api.PUT("/api/weeks/{iso}/slots/{day}/{meal}/cancelled", {
          params: { path: { iso, day, meal } },
          body: { cancelled },
        }),
      ),
  );
}

export function useClearWeek(iso: string) {
  return useWeekMutation<{ keepPinned: boolean }>(iso, ({ keepPinned }) =>
    unwrap(
      api.DELETE("/api/weeks/{iso}/assignments", {
        params: { path: { iso }, query: { keep_pinned: keepPinned } },
      }),
    ),
  );
}

export function useCopyWeek(iso: string) {
  return useWeekMutation<{ sourceIso: string }>(iso, ({ sourceIso }) =>
    unwrap(
      api.POST("/api/weeks/{iso}/copy-from/{source_iso}", {
        params: { path: { iso, source_iso: sourceIso }, query: { grid_only: true } },
      }),
    ),
  );
}

// ---------------------------------------------------------------------------- Gerichte

export function useDishes(q?: string) {
  return useQuery({
    queryKey: keys.dishes(q),
    queryFn: () =>
      unwrap<DishSummary[]>(
        api.GET("/api/dishes", { params: { query: q ? { q } : {} } }),
      ),
  });
}

export function useDish(id: number | null) {
  return useQuery({
    queryKey: keys.dish(id ?? 0),
    enabled: id !== null,
    queryFn: () =>
      unwrap<Dish>(api.GET("/api/dishes/{dish_id}", { params: { path: { dish_id: id! } } })),
  });
}

export function useCategories() {
  return useQuery({
    queryKey: keys.categories,
    queryFn: () => unwrap<Category[]>(api.GET("/api/categories", {})),
  });
}

export function useSaveDish() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { id?: number; body: DishIn }) =>
      vars.id
        ? unwrap<Dish>(
            api.PATCH("/api/dishes/{dish_id}", {
              params: { path: { dish_id: vars.id } },
              body: vars.body,
            }),
          )
        : unwrap<Dish>(api.POST("/api/dishes", { body: vars.body })),
    onSuccess: (dish) => {
      client.invalidateQueries({ queryKey: ["dishes"] });
      client.invalidateQueries({ queryKey: keys.dish(dish.id) });
      client.invalidateQueries({ queryKey: keys.categories });
    },
  });
}

export function useArchiveDish() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      unwrap<Dish>(api.DELETE("/api/dishes/{dish_id}", { params: { path: { dish_id: id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["dishes"] }),
  });
}

export function useConfirmCooked() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      dish_id: number;
      cooked_at: string;
      slot_day?: number;
      slot_meal?: Meal;
      rating?: number;
    }) =>
      unwrap<Dish>(
        api.POST("/api/cook-log", {
          body: {
            dish_id: vars.dish_id,
            cooked_at: vars.cooked_at,
            slot_day: vars.slot_day ?? null,
            slot_meal: vars.slot_meal ?? null,
            rating: vars.rating ?? null,
            note: null,
          },
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["dishes"] });
      client.invalidateQueries({ queryKey: ["week"] });
    },
  });
}

// ----------------------------------------------------------------------------- Artikel

export function useArticles(q?: string) {
  return useQuery({
    queryKey: keys.articles(q),
    queryFn: () =>
      unwrap<Article[]>(api.GET("/api/articles", { params: { query: q ? { q } : {} } })),
  });
}

export type ArticleBody = {
  canonical_name: string;
  unit: Article["unit"];
  bring_catalog_name?: string | null;
  is_staple?: boolean;
  is_watchlist?: boolean;
  aliases?: string[];
  max_unit_price?: string | null; // Richtpreis; null = jedes Angebot zählt
  min_offer_amount?: string | null; // Angebote erst ab dieser Menge; null = jede Packung
  regular_pack_amount?: string | null; // Normalpreis: Menge in der Einheit des Artikels …
  regular_pack_price?: string | null; // … und was sie ohne Angebot kostet
  regular_pack_unit?: "STUECK" | null; // Menge zählt Stück statt g/ml
  piece_size?: string | null; // 1 Stück ≈ so viel g/ml
};

export function useSaveArticle() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (vars: { id?: number; body: ArticleBody }): Promise<Article> => {
      // Felder mit Default sind im generierten Schema verpflichtend (der Server füllt
      // sie sonst selbst) - hier einmal auffüllen statt an jeder Aufrufstelle.
      const body = {
        ...vars.body,
        is_staple: vars.body.is_staple ?? false,
        is_watchlist: vars.body.is_watchlist ?? false,
      };
      if (vars.id !== undefined) {
        return unwrap<Article>(
          api.PATCH("/api/articles/{article_id}", {
            params: { path: { article_id: vars.id } },
            body,
          }),
        );
      }
      return unwrap<Article>(api.POST("/api/articles", { body }));
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["articles"] }),
  });
}

/** Versehentlich doppelt angelegte Zutaten zusammenführen - Zeilen wandern mit. */
export function useMergeArticles() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (vars: { target_id: number; source_ids: number[] }) =>
      unwrap<Article>(
        api.POST("/api/articles/{article_id}/merge", {
          params: { path: { article_id: vars.target_id } },
          body: { source_ids: vars.source_ids },
        }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["articles"] });
      client.invalidateQueries({ queryKey: ["dishes"] });
      client.invalidateQueries({ queryKey: ["shopping"] });
      client.invalidateQueries({ queryKey: ["week"] });
    },
  });
}

export async function suggestArticles(q: string) {
  return unwrap(api.GET("/api/articles/suggest", { params: { query: { q } } }));
}

export async function suggestCatalog(q: string) {
  return unwrap(api.GET("/api/articles/catalog-suggest", { params: { query: { q } } }));
}

/**
 * Nährwerte für ein noch nicht gespeichertes Gericht. Bewusst ein Server-Aufruf: die
 * Rechnung liegt in `domain/nutrition.py` und wird im Frontend nicht nachgebaut.
 */
export async function previewNutrition(
  portions: number,
  ingredients: { article_id: number; quantity: string | null; unit: Article["unit"] }[],
): Promise<DishNutrition> {
  return unwrap<DishNutrition>(
    api.POST("/api/nutrition/preview", { body: { portions, ingredients } }),
  );
}

export async function parseIngredients(text: string): Promise<ParsedLine[]> {
  const result = await unwrap(api.POST("/api/parse/ingredients", { body: { text } }));
  return result.lines;
}

// ------------------------------------------------------------------------ Einkaufsliste

export function useShoppingList(iso: string, enabled = true) {
  return useQuery({
    queryKey: keys.shopping(iso),
    enabled,
    queryFn: () =>
      unwrap<ShoppingList>(
        api.GET("/api/weeks/{iso}/shopping-list", {
          params: { path: { iso }, query: { rebuild: true } },
        }),
      ),
  });
}

function useShoppingMutation<TVars>(iso: string, run: (vars: TVars) => Promise<ShoppingList>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: (list) => client.setQueryData(keys.shopping(iso), list),
  });
}

export function useToggleHave(iso: string) {
  return useShoppingMutation<{ article_id: number; have_already: boolean }>(iso, (body) =>
    unwrap(
      api.PATCH("/api/weeks/{iso}/shopping-list/have-already", {
        params: { path: { iso } },
        body,
      }),
    ),
  );
}

export function useAddItem(iso: string) {
  return useShoppingMutation<{ article_id: number; source?: "MANUAL" | "WATCHLIST" }>(
    iso,
    (body) =>
      unwrap(
        api.POST("/api/weeks/{iso}/shopping-list/items", {
          params: { path: { iso } },
          body: { article_id: body.article_id, quantity: null, source: body.source ?? "MANUAL" },
        }),
      ),
  );
}

export function useRemoveItem(iso: string) {
  return useShoppingMutation<{ article_id: number }>(iso, ({ article_id }) =>
    unwrap(
      api.DELETE("/api/weeks/{iso}/shopping-list/items/{article_id}", {
        params: { path: { iso, article_id } },
      }),
    ),
  );
}

export function usePush(iso: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/weeks/{iso}/shopping-list/push", { params: { path: { iso } } }),
      ),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.shopping(iso) });
      client.invalidateQueries({ queryKey: keys.runs });
      client.invalidateQueries({ queryKey: keys.health });
    },
  });
}

// ----------------------------------------------------------------------------- Betrieb

export function useHealth() {
  return useQuery({
    queryKey: keys.health,
    queryFn: () => unwrap<Health>(api.GET("/api/health", {})),
    refetchInterval: 60_000,
  });
}

export function useSyncRuns() {
  return useQuery({
    queryKey: keys.runs,
    queryFn: () => unwrap<SyncRun[]>(api.GET("/api/sync-runs", { params: { query: {} } })),
  });
}

export function useSettings() {
  return useQuery({
    queryKey: keys.settings,
    queryFn: () => unwrap<Settings>(api.GET("/api/settings", {})),
  });
}

export function useSaveSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      planner_weights?: Record<string, number>;
      household?: Record<string, unknown>;
      shopping?: Record<string, unknown>;
    }) =>
      unwrap<Settings>(
        api.PUT("/api/settings", {
          body: {
            planner_weights: body.planner_weights ?? null,
            household: body.household ?? null,
            shopping: body.shopping ?? null,
          },
        }),
      ),
    onSuccess: (settings) => {
      client.setQueryData(keys.settings, settings);
      client.invalidateQueries({ queryKey: ["week"] });
    },
  });
}

/** Das Raster, mit dem neue Wochen anfangen. */
export function useStandardWeek() {
  return useQuery({
    queryKey: keys.standardWeek,
    queryFn: () =>
      unwrap<StandardSlot[]>(api.GET("/api/settings/standard-week", {})),
  });
}

export function useSaveStandardWeek() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (slots: StandardSlot[]) =>
      unwrap<StandardSlot[]>(api.PUT("/api/settings/standard-week", { body: { slots } })),
    onSuccess: (saved) => client.setQueryData(keys.standardWeek, saved),
  });
}

export function useOffers() {
  return useQuery({
    queryKey: keys.offers,
    queryFn: () => unwrap<Offer[]>(api.GET("/api/offers", {})),
  });
}

/** Stand pro Laden: letzter Abruf, welcher Markt, wie viele Angebote noch gelten. */
export function useOfferStatus() {
  return useQuery({
    queryKey: keys.offerStatus,
    queryFn: () => unwrap<StoreStatus[]>(api.GET("/api/offers/status", {})),
  });
}

/** Der Knopf "Angebote abrufen" - dauert ein paar Sekunden pro Laden. */
export function useFetchOffers() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap<StoreStatus[]>(api.POST("/api/offers/fetch", {})),
    onSuccess: (status) => {
      client.setQueryData(keys.offerStatus, status);
      client.invalidateQueries({ queryKey: keys.offers });
      client.invalidateQueries({ queryKey: ["shopping"] });
      client.invalidateQueries({ queryKey: ["candidates"] });
    },
  });
}

// ------------------------------------------------------------------------------- Läden

export function useStores() {
  return useQuery({
    queryKey: keys.stores,
    queryFn: () => unwrap<Store[]>(api.GET("/api/stores", {})),
  });
}

/** Läden ändern heißt auch: andere Angebote, anderer Abruf-Stand. */
function useStoreMutation<TVars>(run: (vars: TVars) => Promise<unknown>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: run,
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.stores });
      client.invalidateQueries({ queryKey: keys.offers });
    },
  });
}

export function useCreateStore() {
  return useStoreMutation((body: StoreIn) => unwrap(api.POST("/api/stores", { body })));
}

export function useUpdateStore() {
  return useStoreMutation(({ id, ...body }: StorePatch & { id: number }) =>
    unwrap(api.PATCH("/api/stores/{store_id}", { params: { path: { store_id: id } }, body })),
  );
}

export function useDeleteStore() {
  return useStoreMutation((id: number) =>
    unwrap(api.DELETE("/api/stores/{store_id}", { params: { path: { store_id: id } } })),
  );
}
