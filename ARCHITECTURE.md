# Softwarearchitektur – Wochenplan- & Einkaufs-App

Ergänzt `general_plan.md` (Features, Domänenlogik, Recherche) um den Bauplan.
Beantwortet die in `general_plan.md` §10 offen gelassenen Architekturfragen.

## 0. Leitgedanken

Zwei Dinge treiben jede Entscheidung in diesem Dokument:

1. **Der Wert liegt im Datenmodell und der Planungslogik** (Portions-Reste-Ketten, Anwesenheit pro
   Slot, Abwechslungsregeln, Angebots-Bonus). Das muss pure, deterministisch und ohne UI testbar sein,
   damit Spike 4 (Gewichtungen kalibrieren) *vor* dem UI-Bau möglich ist.
2. **Zwei Integrationen sind fragil** und brechen laut Recherche 1–2× pro Jahr (Bring!,
   Angebots-Scraper). Sie gehören hinter dünne Ports, damit ein Bruch nur ein Feature lähmt und nicht
   die App.

Ergebnis: geschichtete Architektur mit purem Domänenkern, dünner Service-Schicht, austauschbaren
Integrations-Adaptern und einer SPA, die den Kern nur rendert (keine Logik-Duplikate im Frontend).

### Getroffene Entscheidungen

| Thema | Entscheidung | Konsequenz |
|---|---|---|
| Frontend | React + TS SPA, FastAPI liefert nur JSON | TS-Client aus OpenAPI generiert, ein Vertrag |
| Deployment | Docker Compose, x86-Heimserver/NAS | Korbunio als Sidecar, Frontend-Build außerhalb des Servers |
| LLM | **Keins.** Statt Schnellerfassung ein *schneller* manueller Einfüge-Workflow | Deterministischer Zeilen-Parser + Tastatur-Flow; `LlmPort` nur als Naht für später |
| Auth | Keine App-Auth. Im Heimnetz offen erreichbar, von außen über Tailscale | Bind auf `0.0.0.0`; jedes Gerät im LAN hat Voll- und Schreibzugriff (bewusst gewählt); Nutzeridentität nur als Profil |
| Datenbank | SQLite | 2 Nutzer, ein Writer, WAL – Postgres wäre reine Betriebslast |

### Abweichungen von `general_plan.md`, die daraus folgen

- **§5 Phase 0 „Schnellerfassung per LLM“ entfällt.** Ersatz: Paste-Textarea + deterministischer
  Parser + Combobox mit Inline-Artikelanlage (§7). Nebenwirkung: die automatischen
  Kategorie-Vorschläge fallen weg → Kategorien als Chip-Picker, häufigste Chips vorne.
- **§7 „LLM als Schiedsrichter“ beim Angebots-Matching wird verschoben.** MVP: Alias-Liste +
  RapidFuzz + „Unzugeordnet“-Ansicht. Der Port existiert, die Implementierung nicht.
- **§8 Nr. 11 umgedreht:** statt „gekocht“ zu bestätigen, gilt ein geplantes Gericht ab seinem
  Tag als gekocht, und nur „ausgefallen“ ist ein Klick. Ein vergessenes Bestätigen hätte die
  Rotation über die Wochen ganz abgeschaltet; ein vergessenes „ausgefallen“ kostet nur einen
  kleinen Abzug für ein paar Wochen.
- **§8 Nr. 13 wird weiter gefasst:** die App ist im Heimnetz ohne Anmeldung erreichbar – bewusst,
  weil das den Alltag spürbar vereinfacht (kein Login, kein Tailscale-Client auf jedem Gerät).
  Von außen bleibt Tailscale der Weg, im Router wird **kein** Port weitergeleitet. Preis der
  Entscheidung: jedes Gerät im LAN kann lesen *und* schreiben, IoT-Geräte eingeschlossen; das
  Gegenmittel wäre bei Bedarf ein getrenntes Gast-WLAN, keine App-Auth.

---

## 1. Systemüberblick

```
┌─ Heimnetz / Tailnet ───────────────────────────────────┐
│  Browser (Laptop / Handy-PWA)                          │
│        │ HTTP, JSON                                    │
│  ┌─────▼──────────────── app-Container ─────────────┐  │
│  │ FastAPI                                          │  │
│  │  api/      Router + Pydantic-DTOs                │  │
│  │  services/ Use-Cases, Transaktionen              │  │
│  │  domain/   PURE: Score, Planer, Reste, Mengen    │  │
│  │  db/       SQLAlchemy + Alembic → SQLite         │  │
│  │  integrations/ bring | offers | catalog          │  │
│  │  jobs/     APScheduler (Mo/Do früh)              │  │
│  │  static/   gebautes React-Bundle                 │  │
│  └───┬──────────────────────┬───────────────────────┘  │
│      │                      │                          │
│  ┌───▼─────────┐      ┌─────▼────────┐                 │
│  │ ./data      │      │ korbunio     │ (Phase 2)       │
│  │ sqlite+media│      │ Container    │                 │
│  └─────────────┘      └─────┬────────┘                 │
└─────────────────────────────┼──────────────────────────┘
                              ▼ Heim-IP → Edeka/Aldi/Netto/Rewe
                         api.getbring.com ◀── bring-api
```

Ein Deployable für App + Frontend. Kein Message-Broker, kein Redis, kein separater Worker – bei zwei
Angebots-Abrufen pro Woche ist In-Process-Scheduling korrekt und alles andere Overhead.

---

## 2. Repo-Struktur

```
shopping_app/
  general_plan.md
  ARCHITECTURE.md
  compose.yaml
  Dockerfile                 # multi-stage: node build → python runtime
  .env.example               # Bring!-Bot-Account, Markt-IDs, Korbunio-URL
  backend/
    pyproject.toml           # uv, Python 3.13
    alembic.ini
    migrations/versions/
    src/mealplan/
      config.py              # pydantic-settings; .env + data/config.local.toml
      main.py                # App-Factory, StaticFiles-SPA-Fallback, Lifespan
      ports.py               # Protocols (s. §5)
      domain/                # KEIN Import von db/api/httpx – per Test erzwungen
        model.py             # frozen dataclasses: DishSpec, SlotSpec, Assignment, Plan
        units.py             # Unit, Quantity, Aggregation, Formatierung
        eligibility.py       # harte Kriterien
        scoring.py           # weiche Kriterien → ScoreBreakdown
        leftovers.py         # PortionLedger, Haltbarkeit, Reste-Ketten
        planner.py           # Kandidaten, Vorschlag, Reroll; Greedy als Startlösung/Rückfall
        optimizer.py         # die Woche als Ganzes: OR-Tools CP-SAT, deterministisch
        diagnostics.py       # Plan-Warnungen
        shopping.py          # Plan → aggregierte Einkaufsliste
        weights.py           # PlannerWeights + Defaults
      services/
        dishes.py  articles.py  weeks.py  planning.py
        shopping_list.py  bring_sync.py  offers.py  matching.py
        ingredient_parsing.py
      db/
        models.py  session.py  mappers.py     # ORM ↔ Domain-Snapshots
      integrations/
        bring/  offers/  catalog/
      matching/normalize.py                   # + rapidfuzz
      api/routers/  api/schemas/  api/deps.py
      jobs/scheduler.py
    tests/
      domain/  integration/  contract/  conftest.py
  frontend/
    package.json  vite.config.ts  tailwind.config.ts
    src/
      api/            # openapi-typescript generiert + openapi-fetch Wrapper
      routes/         # Week, Dishes, DishEdit, Articles, ShoppingList, Offers
      features/week/  # Board, WeekGrid, SlotCard, SlotSettings (Raster-Menü), CandidateSheet, Standardwoche, DnD
      features/dishes/# QuickEntry, IngredientRows, ArticleCombobox
      components/  lib/
    public/manifest.webmanifest
```

**Bewusst weggelassen:** kein Repository-Interface pro Entität, kein Monorepo-Package-Split, kein
CQRS. Services sprechen SQLAlchemy direkt; Domain-Objekte werden nur da gemappt, wo der Planer sie
braucht. Die Trennlinie, die sich lohnt, ist genau eine: **`domain/` ist I/O-frei** – abgesichert durch
einen Test, der die Importe von `domain/*` prüft.

---

## 3. Datenmodell (SQLite / SQLAlchemy 2.0)

Kern (Phase 1):

| Tabelle | Wichtige Felder | Anmerkung |
|---|---|---|
| `article` | `canonical_name`, `unit`, `bring_category`, `bring_catalog_name`, `is_staple`, `is_watchlist`, `max_unit_price`, `min_offer_amount` | `unit` ist **eine** kanonische Einheit pro Artikel (Plan §8 Nr. 10) |
| `article_alias` | `article_id`, `alias`, `kind` (ALIAS/EIGENMARKE), `store_id?` | Basis für Angebots-Matching |
| `category` | `axis` (SIDE/PROTEIN/CUISINE), `name` | Achsen als Enum, Werte als Zeilen → keine Spaltenwucherung |
| `dish` | `name`, `portions` (1/2/3), `packable`, `reheatable`, `allow_double`, `allow_triple`, `effort` (NORMAL/QUICK), `suitable_for`, `rating`, `prep_text`, `archived` | erlaubte Faktoren: 1er-Gericht ×2/×3 per Schalter, 2er-Gericht ×2 per `allow_double`, 3er nie (`DishSpec.factors`) |
| `dish_category` | `dish_id`, `category_id` | m:n |
| `ingredient` | `dish_id`, `article_id`, `quantity` (Decimal, NULL = „nach Bedarf“), `unit`, `sort_order` | `unit` muss zu `article.unit` dimensionsgleich sein |
| `week` | `iso_year`, `iso_week`, `primary_store_id`, `secondary_store_id?`, `planner_seed`, `version` | `version` = optimistisches Locking (Laptop + Handy gleichzeitig) |
| `slot` | `week_id`, `day` 0–6, `meal` (LUNCH/DINNER), `eaters_home` 0–2, `packed_portions` 0–2, `packed_fresh`, `time_budget` (NORMAL/LITTLE), `special` (NONE/EATING_OUT/FROM_PANTRY), `pinned` | Das Wochenraster; `packed_fresh` = Mitnehm-Portionen frisch gekocht statt vorgekocht (keine Reste) |
| `slot_assignment` | `slot_id` PK, `kind` (DISH/LEFTOVER/PANTRY/EMPTY), `dish_id?`, `factor` 1–3, `leftover_source_slot_id?`, `portions_used?`, `score_snapshot` JSON | Union-Type als tagged column; `score_snapshot` friert die Begründung ein |
| `cook_log` | `slot_id`, `dish_id`, `cooked_at`, `confirmed`, `rating`, `note` | Trennt „geplant“ von „gekocht“ (Plan §8 Nr. 11): ohne Zeile zählt ein geplantes Gericht ab seinem Tag als gekocht; `confirmed = false` mit `slot_id` = ausgefallen, `confirmed = true` = ausdrücklich gekocht (auch ohne Plan) |
| `shopping_list` | `week_id`, `status` (DRAFT/SENT), `sent_at` | |
| `shopping_list_item` | `article_id`, `quantity`, `unit`, `source` (RECIPE/MANUAL/WATCHLIST), `have_already`, `store_id?`, `spec_text`, `from_dish_ids` JSON | `from_dish_ids` = „warum steht das drauf?“ |
| `bring_sync_item` | `article_id`, `bring_list_uuid`, `bring_item_uuid`, `last_name`, `last_spec`, `last_pushed_at` | Eigene UUIDs → nie Fremdeinträge anfassen (Plan §8 Nr. 8) |
| `sync_run` | `kind`, `status`, `error`, `summary` JSON | Jeder Push/Fetch wird protokolliert und ist in der UI sichtbar |
| `setting` | `key`, `value` JSON | Planer-Gewichte, Split-Schwelle €, Haushaltsnamen, Standardwoche (Raster neuer Wochen) |

Phase 2 (Schema von Anfang an anlegen, erst später bespielt – Migrationen sind billiger als Rework):

| Tabelle | Wichtige Felder | Anmerkung |
|---|---|---|
| `store` | `name`, `chain`, `market_id`, `offer_source` | |
| `article_store_availability` | `article_id`, `store_id`, `available` | „nicht verfügbar“ → dort gar nicht suchen |
| `offer_snapshot` | `store_id`, `source`, `fetched_at`, `valid_from/to`, `status`, `offer_count`, `raw_payload` JSON | |
| `offer` | `snapshot_id`, `raw_name`, `brand`, `price`, `old_price`, `base_price`, `valid_from/to`, `image_path` | |
| `offer_match` | `normalized_offer_name`, `store_id`, `article_id`, `score`, `decided_by` (FUZZY/USER/LLM), `confirmed` | Cache auf normalisiertem Namen, **nicht** auf `offer_id` → überlebt den Wochenwechsel |

**Einheiten-Entscheidung (der unangenehmste Teil von Plan §8 Nr. 10):** Jeder Artikel hat genau eine
kanonische Einheit (`STUECK`, `G`, `ML`). `units.py` rechnet innerhalb einer Dimension (g↔kg, ml↔l).
Dimensionswechsel (2 Zwiebeln vs. 150 g Zwiebeln) wird beim **Erfassen** abgelehnt, mit Hinweis auf die
gewählte Einheit – nicht stillschweigend geraten. `article.piece_size` („1 Stück ≈ 200 g“, in der
Einheit des Artikels) rechnet bisher nur Stück-Angebote in kg-Preise um; die Mengen der Einkaufsliste
bleiben davon unberührt.

---

## 4. Domänenkern (der eigentliche Wert)

Alles pure Funktionen über frozen dataclasses. Kein ORM, keine Session, keine Uhr – `Clock` kommt als
Parameter. Signaturen:

```python
def eligible(dish: DishSpec, slot: SlotSpec, ctx: PlanContext) -> Eligibility
    # -> ok=False + reasons: ["Aufwand passt nicht zu 'wenig Zeit'", "nicht mitnehmbar"]

def score(dish, slot, plan, snap: PlanningSnapshot) -> ScoreBreakdown
    # ScoreBreakdown(total, contributions=[Contribution(rule, delta, text)])

def candidates(slot, plan, snap) -> list[Candidate]        # sortiert, mit Breakdown + Warnungen
def propose(snap, pinned: Mapping[SlotId, Assignment], seed: int) -> Plan
def diagnose(plan, snap) -> list[PlanWarning]
def build_shopping_list(plan, snap) -> ShoppingListDraft
```

Drei Entscheidungen, die den Rest tragen:

1. **Score ist immer eine Liste benannter Beiträge, nie eine Zahl.** Die Begründung aus Plan §4
   („mitnehmbar, 3 Portionen, seit 5 Wochen nicht gekocht, Lachs im Angebot“) *ist* der Score, in
   umgekehrter Richtung gelesen. Kein Erklärungstext im Frontend, keine zweite Wahrheit.
2. **Gewichte kommen aus `setting`, nicht aus dem Code.** Spike 4 kalibriert über eine Config-Seite
   bzw. ein CLI-Flag, ohne Deploy. `PlannerWeights` hat Defaults, die Plan §4 entsprechen.
3. **`seed` wird an der Woche persistiert.** „Neu würfeln“ = neuer Seed für diesen Slot; damit ist
   jeder Vorschlag reproduzierbar und Tests sind stabil.

**Planer-Algorithmus** – die Woche als Ganzes (Plan §4 sah OR-Tools als spätere Ausbaustufe vor):
1. Greedy als Startlösung: Slots nach Schwierigkeit, jeweils der beste Kandidat, dann paarweise
   Tauschs. Schnell, aber blind für Reste-Ketten – am Montagabend weiß er nicht, dass ein
   3er-Gericht den Dienstagmittag dessen deckt, der allein isst.
2. `optimizer.py`: jede Belegung ist eine Entscheidung (Gericht × Größe pro Slot, Reste aus
   Topf *s* in Slot *t*); CP-SAT maximiert die Gesamtpunktzahl mit denselben Regeln und Gewichten
   wie `scoring.py`. Abwechslung über Kategorien statt Gericht-Paare, das hält das Modell klein.
   Harte Regeln: `eligible()`, ein Gericht einmal pro Woche, Reste decken einen Slot ganz und
   innerhalb der Haltbarkeit, keine Reste Mittag → Abend am selben Tag (außer abends *keine
   Zeit*), bei *keine Zeit* wird nicht gekocht.
3. Rechenmenge statt Zeitlimit: erst kurz mit einer Strategie (kleine Wochen sind damit bewiesen
   optimal), sonst 16 Strategien deterministisch verzahnt – ~2 s, derselbe Seed gibt denselben
   Plan. Das Ergebnis wird mit `rescore()` bewertet; ist es nicht besser als der Greedy-Plan (oder
   widersprechen sich Pins), bleibt der Greedy-Plan.
4. `diagnose()` erzeugt die Warnungen aus Plan §5 Phase 1 (dreimal Reis, Dienstag nichts zum
   Mitnehmen, Aufwand passt nicht zur Zeit, Portion bleibt übrig).

Tests prüfen den Optimierer gegen Durchprobieren: auf kleinen Wochen findet kein erlaubter Plan
mehr Punkte, und seine Punkte sind die von `rescore()`.

**`PortionLedger`** ist die Stelle, an der die untersuchten Konkurrenzprodukte scheitern, also die
Stelle mit den meisten Tests: `produced = portions × factor`,
`needed = eaters_home + packed_portions`, Überschuss mit Haltbarkeit 1–2 Tagen, `LEFTOVER`-Zuweisungen
ziehen aus einer unverfallenen Quelle. Invarianten (nie überziehen, nie über Haltbarkeit hinaus,
Verschwendung = Abzug) als Hypothesis-Property-Tests.

**Einkaufs-Split** (Plan §7): `split_proposal(plan, availability, offers, threshold)` vergleicht
„Hauptladen komplett“ gegen „Haupt + Zweit“, gibt Ersparnis in € zurück und schlägt nur vor, wenn ein
Artikel im Hauptladen fehlt **oder** die Ersparnis über der Schwelle liegt. Harte Regel „alles bis
Dienstagmittag aus dem Hauptladen“ ist ein Filter in dieser Funktion, kein UI-Hinweis.

---

## 5. Ports & Adapter

`ports.py` definiert `typing.Protocol`s; Adapter leben unter `integrations/`; die Auswahl passiert in
`config.py`. Das ist die Versicherung gegen die 1–2 Brüche pro Jahr.

```python
class ShoppingListSync(Protocol):
    def push(self, desired: list[SyncItem], state: SyncState) -> SyncResult: ...

class OfferSource(Protocol):
    def fetch(self, store: Store, queries: list[str]) -> OfferSnapshot: ...

class BringCatalog(Protocol):
    def suggest(self, name: str) -> list[CatalogSuggestion]: ...

class LlmPort(Protocol):      # Naht, MVP-Implementierung: NullLlm
    def judge_match(self, offer_name: str, article: Article) -> MatchVerdict: ...
```

### Bring! (`integrations/bring/`)

- `BringSync` nutzt `bring-api` (miaucl). Eigener Bot-Account (`…+app@…`), zur gemeinsamen Liste
  eingeladen.
- Push ist ein **Diff**, kein Neuschreiben: Soll-Zustand (Items mit `have_already == false`) gegen
  `bring_sync_item` → create / update-spec / remove, ein Batch-Call, alles in einem `sync_run`.
  Einträge ohne unsere UUID werden nie berührt.
- `TextExportSync` als zweite Implementierung: rendert die Liste als Text zum Teilen. Bei
  `BringSync`-Fehler zeigt die UI direkt diesen Fallback an, statt den Montag zu blockieren.
- Katalog (`catalog.de-DE.json`, ~380 Artikel) wird beim Start in `./data/catalog/` gecacht und
  liefert die Fuzzy-Vorschläge beim Anlegen eines Artikels (Plan §8 Nr. 9).

### Angebote (`integrations/offers/`)

- `KorbunioOfferSource` spricht den Sidecar über `POST /api/v1/compare` an: pro Laden der *ganze*
  Prospekt (`postal_code`, `retailers`, bei Rewe/Netto die Markt-ID, ohne `keywords`), seitenweise.
  Zugeordnet wird bei uns – die Wortsuche der Quelle findet „Schafskäse“ nicht unter „Hirtenkäse“.
  Format geprüft gegen Korbunio 0.1.57 (`tests/contract/cassettes/`). `MarktguruOfferSource` als
  zweite Meinung, Phase 2b.
- Läden stehen in der Tabelle `store` (Kette, eigene PLZ, Markt-ID, `offer_source` NULL = keine
  Angebote), gepflegt unter *Einstellungen → Läden* – nicht in `config.local.toml`, weil `data/` im
  Container root gehört.
- Jeder Fetch schreibt einen `offer_snapshot` **inklusive `raw_payload`** – Reprocessing bei
  Mapping-Änderungen ohne erneuten Abruf, und die Schema-Prüfung hat ein Beweisstück.
- `status = OK` nur bei `offer_count > 0`. Der letzte OK-Snapshot bleibt der, den die App liest → ein
  fehlgeschlagener Abruf leert nie die Angebotsansicht (Plan §8 Nr. 2). Bilder werden nach
  `./data/media/` gespiegelt, nicht gehotlinkt (noch offen – bis dahin lädt das Detailfenster eines
  Angebots das Bild erst beim Öffnen direkt von der Quelle, ohne Referrer; die Bilderansicht der
  Liste ebenso, Vorschaubilder erst, wenn die Zeile in Sicht kommt: `loading="lazy"`). Pro Laden bleiben die
  letzten sechs Abrufe plus der letzte gute.
- Der Grundpreis wird beim Speichern vergleichbar gemacht (`domain/unit_price.py`: €/kg, €/l,
  €/Stück; aus dem Text der Quelle, sonst aus Preis und Packung, zuletzt aus der Stückzahl
  im Prospekttext - „2er-Schale“, „je St.“). Hat ein Artikel einen Richtpreis
  (`article.max_unit_price`), zählt ein Angebot nur darunter; ein nicht vergleichbarer Grundpreis
  zählt dann nie. Ebenso die Mindestpackung (`article.min_offer_amount`, in der Einheit des
  Artikels): die Größe eines Angebots kommt aus Packung, Stückzahl × Stückgewicht oder Preis ÷
  Grundpreis (`offer_quantity`); kleiner oder unbekannt zählt nicht (`pack_verdict`).
- Der Normalpreis (`article.regular_pack_amount` + `regular_pack_price`, „250 g für 1,19 €“) ist vom
  Richtpreis unabhängig: der Richtpreis entscheidet, *ob* ein Angebot zählt, der Normalpreis, *was es
  bringt*. Jedes Angebot trägt seinen Abstand dazu (`normal_diff`) – Grundlage für den späteren
  Planer-Bonus anstelle der „statt“-Preise, die die Quellen kaum liefern.
- Erst alle Quellen abfragen, dann in einem Rutsch schreiben – ein Abruf dauert Sekunden pro Laden,
  so lange soll niemand auf die SQLite-Schreibsperre warten. Ein Lock verhindert zwei Abrufe
  gleichzeitig (Knopf + Cron).
- Scheduler: `APScheduler` in-process, Mo 05:00 und Do 05:00, verpasste Termine bis mittags nachgeholt.
  Dazu der Knopf `POST /api/offers/fetch`.
- Plan und Einkaufsliste lesen nur **bestätigte** Zuordnungen (`offer_match.confirmed`): die
  automatische hält „Gefüllte Paprika“ für Paprika.

### Matching (`matching/` + `services/matching.py`)

Normalisieren (lowercase, Umlaut-Faltung, Mengen-Regex strippen, Eigenmarken-Token entfernen) →
Treffer in `offer_match` (bestätigter Cache) → sonst RapidFuzz `token_set_ratio ≥ 85` gegen die
Alias-Liste (Name, Aliase, Bring!-Katalogname) → sonst „Unzugeordnet“-Ansicht mit
Ein-Klick-Zuordnung. Verglichen wird in `match_form`: ohne Verneintes („ohne Zucker“), Sorten-
Vorsilben als eigenes Wort („speise kartoffeln“). Der Cache-Schlüssel bleibt `normalize` – eine
neue Vorsilbe macht keine bestätigte Zuordnung ungültig. Artikel mit
`article_store_availability.available = false` werden für diesen Laden gar nicht gesucht.

---

## 6. API-Schicht

FastAPI, Router pro Aggregat, Pydantic-DTOs getrennt von ORM und Domain. Router sind dünn:
DTO → Service → DTO. Fehler-Mapping zentral (Domain-`ValidationError` → 422, optimistischer
Lock-Konflikt → 409 mit aktuellem Stand).

```
GET/POST/PATCH  /api/dishes            /api/dishes/{id}
GET/POST        /api/articles           /api/articles/suggest?q=       # Combobox + Bring!-Katalog
POST            /api/parse/ingredients                                 # Zeilen → Rows (s. §7)
GET/PUT         /api/weeks/{iso}                                        # Raster incl. version
POST            /api/weeks/{iso}/copy-from/{iso}                        # „wie letzte Woche“
GET/PUT         /api/settings/standard-week                             # Raster, mit dem neue Wochen anfangen
GET             /api/weeks/{iso}/slots/{slot_id}/candidates             # sortiert + Breakdown
POST            /api/weeks/{iso}/propose        {reroll_slot_id?, keep_pins}
PUT             /api/weeks/{iso}/slots/{slot_id}/assignment
GET             /api/weeks/{iso}/diagnostics
GET/PATCH       /api/weeks/{iso}/shopping-list                          # incl. have_already
POST            /api/weeks/{iso}/shopping-list/push                     # → Bring! | Textexport
GET             /api/weeks/{iso}/split-proposal
GET             /api/offers  /api/offers/unmatched  POST /api/offers/match
GET             /api/sync-runs                                          # Bruch-Diagnose in der UI
GET/PUT         /api/settings
```

Keine Auth-Middleware (Entscheidung). Alle Endpunkte stehen jedem Gerät im Heimnetz offen, auch die
schreibenden. `main.py` hält das als Kommentar fest – die eine Regel, die daraus folgt: niemals einen
öffentlich erreichbaren Reverse-Proxy davorsetzen, ohne vorher Auth nachzurüsten.

---

## 7. Frontend

Vite + React 19 + TypeScript + Tailwind + React Router + TanStack Query. `openapi-typescript` +
`openapi-fetch` generieren den Client aus `/openapi.json` (`npm run gen:api`) → Backend-Änderungen
brechen im TS-Build, nicht erst zur Laufzeit.

**Der schnelle Einfüge-Workflow** (ersetzt die LLM-Schnellerfassung – der Teil, der über Phase 0
entscheidet):

- Gerichts-Formular mit einer **Zutaten-Textarea**: eine Zeile pro Zutat, `250 g Basmatireis`.
  `POST /api/parse/ingredients` liefert pro Zeile `{quantity, unit, article_match, confidence}`.
  Der Parser ist regelbasiert und deterministisch: Mengen-Regex + Einheiten-Synonyme
  (`g|gr|Gramm|kg|ml|l|Stk|Stück|Dose|Packung`) + RapidFuzz gegen den Artikelkorpus.
- Unerkannte Artikel erscheinen als Chip „als neuen Artikel anlegen“, Einheit aus der Zeile
  vorbefüllt, Bring!-Katalogvorschlag daneben. Ein Klick, kein Modal, kein Seitenwechsel.
- Zeilenmodus für Nachpflege: `Tab` zwischen Menge/Einheit/Artikel, Combobox mit Fuzzy-Suche,
  `Enter` legt bei Nichttreffer den Artikel inline an.
- Kategorien als Chip-Picker, häufigste Chips vorne (ersetzt die weggefallenen LLM-Vorschläge).

**Wochenboard**: 7×2-Grid. Laptop = `dnd-kit` (Gericht aus Kandidatenliste ziehen, Slots tauschen);
Handy = Slot antippen → Bottom-Sheet mit sortierter Kandidatenliste, Score-Beiträge als Zeilen,
Warnungen rot. Reste-Portionen erscheinen als eigene Karte im Folgeslot und sind verschiebbar.
Pin-Toggle pro Slot, „Neu würfeln“ pro Slot und für die ganze Woche.

**Routen**: `/week/:iso` (Raster + Board + Warnungen), `/dishes`, `/dishes/:id`, `/articles`,
`/week/:iso/list`, `/offers`, `/settings`.

**PWA** via `vite-plugin-pwa`: Manifest + Shell-Precache. Offline nur lesend (letzte Woche +
Einkaufsliste) – im Laden ist Bring! die Wahrheit, echte Offline-Mutationen wären unnötige
Komplexität. Haushaltsprofil („wer bin ich“, für Mitnehm-Defaults) in `localStorage`, kein Login.

**Wichtige Folge des offenen LAN-Zugangs:** `http://<lan-ip>:8080` ist kein *secure context*, also
registriert dort kein Service-Worker – über die LAN-IP gibt es die App nur als normalen Browser-Tab,
ohne Homescreen-Installation und ohne Offline-Cache. Empfohlene Aufteilung, ohne Zusatzaufwand im
Netz: Laptop und Gelegenheitszugriff über `http://<lan-ip>:8080`, die beiden Handys installieren die
PWA einmalig über den HTTPS-Tailnet-Hostnamen (`tailscale cert` + Caddy, s. §8) – der funktioniert
zu Hause und unterwegs gleich. Die Alternative wäre ein eigener LAN-Hostname mit vertrauenswürdigem
Zertifikat (mkcert-Root auf jedem Gerät installieren oder DNS-01-Zertifikat für einen echten Namen,
der auf die LAN-IP zeigt) – mehr Einrichtung als der Tailnet-Weg, deshalb nicht empfohlen.

---

## 8. Deployment & Betrieb

`Dockerfile`, zweistufig: `node:22` baut das Frontend → `python:3.13-slim` mit `uv`, kopiert `dist/`
nach `/app/static`, FastAPI mountet `StaticFiles(html=True)` als SPA-Fallback.

`compose.yaml`:

- `app`: Port `8080` auf allen Interfaces (`0.0.0.0:8080`) – damit erreicht jedes Gerät im Heimnetz
  die App ohne Tailscale-Client. Volume `./data` (SQLite, `media/`, `catalog/`, `backups/`).
  Env aus `.env`. `alembic upgrade head` im Entrypoint. Im Router kein Port-Forward auf 8080.
- `korbunio`: Sidecar, nur im internen Compose-Netz erreichbar (Phase 2).
- `caddy`: HTTPS auf dem Tailnet-Hostnamen via `tailscale cert`, parallel zum offenen HTTP-Port im
  LAN. Nötig, sobald die PWA auf dem Homescreen liegen soll (s. §7) – bis dahin optional.

SQLite: WAL, `foreign_keys=ON`, `busy_timeout`. Backup: nächtlicher `sqlite3 .backup` nach
`./data/backups` (7 Generationen) – ein Cron-Einzeiler, weil die Gerichteliste die Handarbeit von zwei
Abenden ist und nicht am NAS-Snapshot hängen soll.

Beobachtbarkeit für den Alltag, ohne Stack: strukturierte Logs auf stdout, `sync_run`-Tabelle als
sichtbare Historie in der UI, Health-Endpoint `/api/health` mit „letzter erfolgreicher
Angebots-Fetch“ und „letzter Bring!-Push“. Damit ist ein Integrationsbruch an der Oberfläche sichtbar,
statt still zu sein.

---

## 9. Tests

| Ebene | Umfang | Warum |
|---|---|---|
| `tests/domain/` | pure, Millisekunden. Golden-File-Test von `propose()` auf einer echten Woche | Gewichtungsänderungen erzeugen einen lesbaren Diff → Spike 4 wird messbar |
| Property-Tests (Hypothesis) | `PortionLedger`-Invarianten, `units.py`-Aggregation | Der Reste-Teil ist der Kern und die häufigste Fehlerquelle |
| `tests/integration/` | FastAPI `TestClient` + temporäre SQLite, Alembic-Upgrade | Router/Service/Schema zusammen |
| `tests/contract/` | `respx`-Cassettes für Bring! und Korbunio | Schema-Bruch = roter Test, statt Montag-früh-Überraschung (Plan §8 Nr. 1/2) |
| `@pytest.mark.live` | echter Bot-Account, echter Korbunio – manuell | Spikes 1 und 2 laufen als Test, nicht als Wegwerf-Skript |
| Architektur-Test | `domain/*` importiert nichts aus `db/api/integrations` | Hält die eine Grenze, die zählt |
| Frontend | Vitest für den Zeilen-Parser-Client und Score-Rendering; kein E2E | Aufwand/Nutzen bei zwei Nutzern |

---

## 10. Bau-Reihenfolge

| Meilenstein | Inhalt | Fertig, wenn |
|---|---|---|
| **A – Skelett & Daten rein** | Repo, Docker, SQLite+Alembic, `article`/`dish` CRUD, Zeilen-Parser, Combobox, Bring!-Katalog-Cache, `units.py` | 30–50 Gerichte lassen sich abends flüssig eintippen (Plan Phase 0) |
| **B – Planungskern** | `eligibility`, `scoring`, `leftovers`, `planner`, `diagnostics`, Gewichte in `setting`, CLI `mealplan plan --week` | Spike 4 läuft gegen echte Daten – **ohne UI** |
| **C – Wochen-UI** | Rasterseite, Board, Kandidaten-Sheet, Pins, Reroll, Warnungen, „wie letzte Woche“ | Eine echte Woche in unter 5 Minuten geplant |
| **D – Liste & Bring!** | Aggregation, Grundvorrat-Filter, Abhaken, Diff-Push, Textexport, `sync_run`-Ansicht, PWA | Plan Phase 1 komplett: kein Tippen in Bring! mehr |
| **E – Angebote** | Korbunio-Sidecar, Snapshots, Matching, „Unzugeordnet“, Score-Bonus, Watchlist, Split-Vorschlag | Plan Phase 2 – erst nach 3 Wochen Alltag mit D |

Meilenstein B vor C ist die wichtigste Reihenfolge-Entscheidung: die Gewichtungen sind laut Plan §10
offen, und sie zu kalibrieren ist billig ohne UI und teuer mit.

---

## 11. Verifikation

Nach jedem Meilenstein, in dieser Reihenfolge:

1. `cd backend && uv run pytest -m "not live"` – Domain + Integration + Contract grün.
2. `uv run pytest -m live` gegen Bring!-Bot-Account und Korbunio (Spikes 1/2 des Plans): Item mit
   Spezifikation anlegen, Icon prüfen, abhaken, zurücklesen; zehn typische Artikel über vier Ketten.
3. `docker compose up --build`, dann `curl http://127.0.0.1:8080/api/health` – erwartet
   `{"db":"ok","last_offer_fetch":…,"last_bring_push":…}`.
4. Vom Handy über Tailscale öffnen, PWA installieren, eine Woche planen, Liste pushen, in Bring!
   prüfen: keine Duplikate, Mengen als Spezifikation, Fremdeinträge unberührt.
5. Netzzugang: `http://<server-ip>:8080` von einem Gerät im LAN **ohne** Tailscale-Client öffnen –
   muss funktionieren. Gegenprobe nach außen: kein Port-Forward auf 8080 im Router gesetzt.
6. Alltags-Kriterium aus Plan §9: Montags-Ritual unter 5 Minuten, gemessen an der Zahl manueller
   Korrekturen nach dem Auto-Vorschlag und der Zahl nachträglich in Bring! getippter Einträge.

---

## 12. Offene Punkte

- Konkrete Score-Gewichte → Ergebnis von Meilenstein B (Spike 4), landen in `setting`, nicht im Code.
- Markt-ID des Allfrisch-Marktes und PLZ → `data/config.local.toml`, **nicht** ins Repo.
- Ob Korbunio die vier Läden abdeckt → entscheidet in Meilenstein E über eigene Adapter.
- `article.piece_size` auch für die Einkaufsliste nutzen („2 Dosen Mais“ statt „570 g Mais“) – dann
  mit einer Bezeichnung pro Artikel (Stück, Dose, Bund).
