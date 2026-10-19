# Wochenplan & Einkauf

Aus einer Liste bekannter Gerichte einen Wochenplan bauen, der zu Bürotagen, Zeitbudget
und Abwechslung passt – und daraus die Einkaufsliste nach Bring! pushen.

Fachliche Grundlage: [`general_plan.md`](general_plan.md) (Features, Domänenlogik,
Recherche) und [`ARCHITECTURE.md`](ARCHITECTURE.md) (Bauplan).

---

## Was fertig ist

| Meilenstein | Inhalt | Stand |
|---|---|---|
| **A** Skelett & Daten rein | SQLite + Alembic, Artikel- und Gerichte-CRUD, Zeilen-Parser, Bring!-Katalog-Cache, Einheiten-Logik | ✅ |
| **B** Planungskern | `eligibility`, `scoring`, `leftovers`, `planner`, `diagnostics`, Gewichte in `setting`, CLI | ✅ |
| **C** Wochen-UI | Rasterseite, Board mit Drag & Drop, Kandidaten-Sheet mit Begründung, Pins, Neu-würfeln, Warnungen, „wie letzte Woche“ | ✅ |
| **D** Liste & Bring! | Aggregation, Grundvorrat-Filter, Abhaken, Diff-Push, Textexport, Sync-Historie, PWA | ✅ |
| **E** Angebote | Läden, Abruf über Korbunio, Angebote-Seite (Stufe 1) · Zuordnen bestätigen (Stufe 2) · Bonus im Plan, Hinweise auf der Liste (Stufe 3) | 🟡 Stufe 1 fertig |

Phase 2 läuft in Stufen, siehe [Angebote](#angebote).

---

## Schnellstart (Entwicklung)

**Voraussetzungen:** Python 3.13 (`uv` holt es selbst), Node 22.

```bash
cd backend && uv venv --python 3.13 && uv pip install -e ".[dev]"
```

```bash
cd frontend && npm install
```

Datenbank anlegen und Beispieldaten laden:

```bash
cd backend && MEALPLAN_DATA_DIR=../data uv run alembic upgrade head && uv run mealplan seed-demo
```

Backend und Frontend getrennt starten (Vite proxyt `/api` auf 8080):

```bash
cd backend && MEALPLAN_DATA_DIR=../data uv run uvicorn mealplan.main:app --reload --port 8080
```

```bash
cd frontend && npm run dev
```

Dann [http://localhost:5173](http://localhost:5173). Ein API-Überblick liegt unter
`http://localhost:8080/docs`.

> **Hinweis zu Node:** Auf diesem Rechner liegt Node 22 unter `~/.local/node-v22`. Für
> die npm-Befehle einmal pro Shell:
> ```bash
> export PATH="$HOME/.local/node-v22/bin:$PATH"
> ```

### Ein Deployable bauen

Das Backend serviert das gebaute Frontend als SPA (mit Fallback für tiefe Routen):

```bash
cd frontend && npm run build && rm -rf ../backend/src/mealplan/static && cp -r dist ../backend/src/mealplan/static
```

---

## Betrieb auf dem Heimserver

```bash
cp .env.example .env    # Bring!-Bot-Konto eintragen, siehe unten
docker compose up -d --build
curl http://127.0.0.1:8080/api/health
```

Erwartet: `{"db":"ok","dishes":…,"sync_adapter":…,"last_bring_push":…}`.

Die Migrationen laufen im Entrypoint, der Bring!-Katalog wird beim ersten Start
gecacht. Alle Daten liegen in `./data` (SQLite, `catalog/`, `media/`, `backups/`).

### Kein Login – und was daraus folgt

Die App ist im Heimnetz **ohne Anmeldung** erreichbar. Das ist eine bewusste
Entscheidung (ARCHITECTURE.md §0): kein Login im Alltag, kein Tailscale-Client auf
jedem Gerät. Der Preis: jedes Gerät im LAN kann lesen *und* schreiben, IoT-Geräte
eingeschlossen.

Daraus folgt genau eine Regel:

> **Im Router kein Port-Forward auf 8080. Und niemals einen öffentlich erreichbaren
> Reverse-Proxy davorsetzen, ohne vorher Auth nachzurüsten.**

Von außen ist Tailscale der Weg.

### PWA auf dem Homescreen

Über `http://<lan-ip>:8080` registriert kein Service-Worker (kein secure context) – dort
läuft die App als normaler Browser-Tab. Für die Installation auf dem Handy:

```bash
tailscale cert --cert-file data/certs/host.crt --key-file data/certs/host.key \
  <host>.<tailnet>.ts.net
# MEALPLAN_TAILNET_HOST in .env setzen
docker compose --profile tailnet up -d
```

Empfohlene Aufteilung: Laptop über die LAN-IP, die beiden Handys einmalig über den
HTTPS-Tailnet-Hostnamen installieren – der funktioniert zu Hause und unterwegs gleich.

### Backups

Die Gerichteliste ist die Handarbeit von zwei Abenden. In die Crontab des Hosts:

```bash
0 3 * * * cd /pfad/zu/shopping_app && docker compose exec -T app /app/docker/backup.sh
```

Sieben Generationen in `data/backups/`, per `sqlite3 .backup` (konsistent auch bei
laufenden Schreibvorgängen).

---

## Bring! anbinden

Es gibt keine offizielle Bring!-API. Der Adapter nutzt `bring-api` und ist so gebaut,
dass ein Bruch nur den Push lähmt, nicht die App (general_plan.md §6):

1. **Eigenes Bot-Konto** anlegen, z. B. `name+app@example.com`, und es zur gemeinsamen
   Bring!-Liste einladen. So trifft ein Sperr-Risiko nur den Bot, Push-Nachrichten an
   euch funktionieren, und die privaten Passwörter bleiben aus der App heraus.
2. In `.env`:
   ```
   MEALPLAN_BRING_SYNC=bring
   MEALPLAN_BRING_EMAIL=name+app@example.com
   MEALPLAN_BRING_PASSWORD=…
   ```
3. Ohne diese Werte läuft alles normal weiter – nur der Push wird zum **Text-Export**
   zum Kopieren und Teilen. Die Oberfläche sagt das („Bring! nicht verbunden“).

**Was der Push garantiert:** Er ist ein Diff gegen die eigenen Einträge (create /
update / remove, gemerkt in `bring_sync_item`). Fremdeinträge werden nie angefasst, und
zweimal Senden erzeugt keine Duplikate – abgesichert in `tests/contract/test_bring_sync.py`.

**Icons in Bring!** erscheinen nur bei exaktem Katalognamen. Darum hat jeder Artikel ein
Feld „Bring!-Katalogname“ mit Fuzzy-Vorschlag aus dem gecachten Katalog (~360 Einträge).

---

## Angebote

Die Prospekte holt **Korbunio** (github.com/lesecuritae/Korbunio), ein zweiter Container
neben der App: Rewe direkt von rewe.de, Netto und Combi aus den regionalen
marktguru-Prospekten.

1. Korbunio starten (einmalig, danach startet er mit):
   ```bash
   sudo docker compose --profile offers up -d --build
   ```
2. Für den automatischen Abruf Mo + Do um 5 Uhr in `.env`:
   `MEALPLAN_OFFER_FETCH_ENABLED=true`. Der Knopf auf der Angebote-Seite geht auch ohne.
3. Unter *Einstellungen → Läden* eintragen, wo ihr einkauft: Kette, **PLZ des Ladens**,
   bei Rewe die Markt-ID (steht in der Angebots-Adresse des Markts,
   `rewe.de/angebote/<ort>/<markt-id>/…`), und „Angebote“ an oder aus.

**Was man wissen muss:**
- Korbunio findet einen Rewe-Markt nur über *dessen* PLZ – darum hat jeder Laden seine
  eigene. Die Angebote unterscheiden sich wirklich pro Markt (Heinrichstraße 150,
  Lengericher Landstraße 243, gemeinsam nur 133).
- Bei **Edeka** nimmt Korbunio den ersten Markt zur PLZ, wählen lässt er sich nicht.
  **Allfrisch** veröffentlicht seine Angebote ohnehin nur in der Edeka-App – er steht als
  Hauptladen ohne Angebote in der Liste.
- Ein „statt“-Preis fehlt fast immer, und „gültig bis“ steht oft nur als Text im
  Prospekt; fehlt beides, gilt ein Angebot bis Samstag. Abgelaufene verschwinden von
  selbst, ein fehlgeschlagener Abruf lässt die letzten guten stehen.
- Die **automatische Zuordnung** liegt etwa zu zwei Dritteln richtig („Gefüllte Paprika“
  ist keine Paprika). Darum wirkt auf Einkaufsliste und Planer nur, was bestätigt ist –
  bestätigen kommt mit Stufe 2.
- **Richtpreis** pro Artikel (*Artikel → bearbeiten*): in €/kg, €/l oder €/Stück, je nach
  Einheit des Artikels. Ein Angebot darüber zählt für den Artikel nicht – es fehlt unter
  „meine Artikel“, auf der Liste und im Planer, und steht unter „alle“ als „über
  Richtpreis“. Ohne Richtpreis zählt jedes Angebot; lässt sich der Grundpreis eines
  Angebots nicht vergleichen („€/Portion“, Stück-Preis für einen Gramm-Artikel), zählt es
  bei gesetztem Richtpreis nicht. Den Grundpreis liefert meist die Quelle, sonst rechnet
  die App ihn aus Preis und Packung, zuletzt aus der Stückzahl im Prospekttext
  („2er-Schale“, „je St.“ – so steht es bei Obst und Gemüse oft nur dort):
  `domain/unit_price.py`.
- **Mindestpackung** pro Artikel („Heidelbeeren ab 400 g“): kleinere Packungen zählen
  nicht und stehen unter „alle“ als „Packung zu klein“. Die Größe kommt aus der Packung,
  der Stückzahl (über das Stückgewicht) oder aus Preis ÷ Grundpreis; lässt sie sich gar
  nicht bestimmen, zählt das Angebot bei gesetzter Mindestpackung nicht.
- **Watchlist:** Was ihr nicht kocht, aber im Angebot kaufen wollt (Frischkäse, Cola,
  Orangen …), ist ein normaler Artikel mit dem Schalter „Angebots-Watchlist“ (★) –
  mit Aliasen, Richt- und Normalpreis wie jeder andere. Der Vorschlag „mit auf die
  Liste?“ kommt mit dem Bestätigen (Stufe 2).
- **Erkennung:** Vorsilben, die nur die Sorte sagen, verdecken den Artikel nicht –
  Speisekartoffeln sind Kartoffeln, Strauchtomaten sind Tomaten (Liste in
  `matching/normalize.py`). Was nach „ohne“, „wenig“ oder „weniger“ steht, zählt nicht
  („Haferdrink ohne Zucker“ ist kein Zucker). Auch der Bring!-Katalogname des Artikels
  gilt als Name – ein allgemeiner („Cola“) findet darum auch Pepsi.
- **Normalpreis** pro Artikel – was ihr ohne Angebot zahlt, meist für die Eigenmarke –,
  eingegeben wie beim Einkauf: „250 g für 1,19 €“. Die App rechnet den Grundpreis
  (4,76 €/kg) und zeigt an jedem Angebot den Abstand („+0,40 €/kg ggü. normal (+8 %)“).
  Er ist vom Richtpreis unabhängig: ein Markenangebot über dem Normalpreis kann sich
  lohnen, wenn die Qualität zählt (Richtpreis höher), bei anderen Artikeln zählt nur
  echtes Sparen (Richtpreis niedriger). Später die Grundlage für den Planer-Bonus und die
  Kosten pro Gericht.
- **Stückgewicht** („1 Stück ≈ 200 g“) für Gramm- und Milliliter-Artikel, die man
  stückweise kauft (Avocado, Gurke, Kopfsalat): damit wird ein Angebot „0,99 €/Stück“ zu
  4,95 €/kg und mit Richt- und Normalpreis vergleichbar (Avocados 1,29 € als 2er-Schale
  bei 1 Stück ≈ 150 g: 0,65 €/Stück ≈ 4,33 €/kg) – sichtbar als Umrechnung („≈“),
  weil es ein Schätzwert ist. Ohne Stückgewicht bleibt ein Stück-Angebot für einen
  Gramm-Artikel unvergleichbar. Den Normalpreis kann man dann auch pro Stück eingeben
  („1 Stück für 0,79 €“).
- **Nachprüfen:** Ein Klick auf ein Angebot zeigt Produktbild, Prospekttext, Grundpreis,
  Gültigkeit, das Urteil gegen den Richtpreis und die Quelle – bei Rewe die Angebotsseite
  des Markts, bei Combi und Netto den Prospekt bei marktguru. Auf ein *einzelnes*
  Angebot verlinkt keine der Quellen.
- **Bilder:** Der Schalter „Bilder“ über der Liste zeigt das Produktbild neben jedem
  Angebot. Gemerkt wird das pro Gerät (im Browser). Geladen wird nur, was beim Scrollen in
  Sicht kommt, direkt von der Quelle und ohne Referrer.
- Korbunio ist nur im internen Docker-Netz erreichbar (`expose`, nie `ports`): er hat
  keine eigene Anmeldung. Die Version ist fest (`0.1.57`); ein Update heißt Version in
  `compose.yaml` ändern und `tests/contract/test_korbunio.py` laufen lassen.

---

## Die Kommandozeile

Der Planungskern läuft ohne UI – so wurden die Gewichte kalibriert (Spike 4):

```bash
cd backend
uv run mealplan plan --week 2026-W37            # Vorschlag rechnen und begründen
uv run mealplan plan --week 2026-W37 --apply    # und speichern
uv run mealplan show --week 2026-W37            # gespeicherten Plan zeigen
uv run mealplan list --week 2026-W37            # Einkaufsliste als Text
uv run mealplan weights                          # Gewichte zeigen
uv run mealplan weights --set rotation_cap=15    # kalibrieren, ohne Deploy
uv run mealplan push --week 2026-W37             # nach Bring! (oder Text-Fallback)
uv run mealplan catalog-refresh                  # Bring!-Katalog neu cachen
uv run mealplan seed-demo                        # Beispieldaten
```

`plan` gibt pro Slot die Begründung aus – dieselben Score-Beiträge, die die UI zeigt:

```
Mo Abend   2+1 P, normal Zeit  ->  Hähnchen-Curry (3 P) [+16.0]
                · seit 8 Wochen nicht gekocht
                · 3 Portionen passen genau
                · gleiche Beilage wie Do Mittag (Reis)
```

---

## Zutaten sind Artikel – mit genau einem Namen

Eine Zutatenzeile eines Gerichts zeigt immer auf einen Artikel aus dem Korpus, und ein
Artikel hat **genau einen Namen**. Es gibt keine Zweitnamen und keine Synonym-Pflege für
Zutaten: was auf der Einkaufsliste steht, heißt so, wie es im Korpus heißt.

Damit daraus nicht „Reis“, „Basmatireis“ und „Vollkornreis“ werden, wird beim Erfassen
**gesucht, bevor etwas entsteht**:

- Das Zutatenfeld im Gerichts-Formular ist eine Suche. Tippen zeigt passende Zutaten
  darunter, Auswahl per Klick oder `↑`/`↓` + `Enter`.
- Erst wenn nichts passt, erscheint „*X* als neue Zutat anlegen“ – mit Einheit daneben.
- Der Textblock für mehrere Zeilen (Phase 0) macht dasselbe: sichere Treffer landen
  direkt in der Liste, und wo der Name neu ist, aber etwas Ähnliches existiert
  („Basmatireis“ bei vorhandenem „Reis“), wird das Vorhandene angeboten, statt
  stillschweigend einen zweiten Artikel anzulegen.

Sind trotzdem Dubletten entstanden, räumt die Artikel-Seite auf: Zeilen ankreuzen,
Namen wählen, **Zusammenführen**. Alle Zutatenzeilen, Listeneinträge und
Angebots-Zuordnungen wandern mit; die anderen Namen verschwinden. Verschiedene
Einheiten-Dimensionen (2 Stück vs. 150 g) werden abgelehnt statt geraten.

> Das Feld **Angebots-Aliase** auf der Artikel-Seite ist etwas anderes und gehört zu
> Phase 2: Angebote heißen im Prospekt „Gut & Günstig Schafskäse“, der Artikel heißt
> „Hirtenkäse“. Diese Aliase werden ausschließlich für den Angebotsabgleich benutzt –
> die Zutaten-Suche kennt sie nicht.

## Nährwerte

Optional und bewusst nur im **Gerichte-Tab** – der Wochenplan und die Einkaufsliste
bleiben davon frei (ein Test hält diese Grenze fest).

Jede Zutat kann vier Angaben tragen: Energie, Kohlenhydrate, Fett, Eiweiß. Die
Bezugsgröße steckt schon in der Einheit und braucht kein eigenes Feld – **je 100 g**,
**je 100 ml** oder **je Stück**. Damit trägt eine Zucchini ihre Werte je Stück; das
Stückgewicht (`piece_size`) spielt für die Nährwerte keine Rolle.

Am Gericht erscheinen die Werte **je Portion**, im Formular live beim Tippen (gerechnet
wird auf dem Server, damit die Logik nicht doppelt existiert). In der Gerichte-Liste
steht eine Spalte `je Portion` mit kcal und Eiweiß.

**Lücken werden benannt, nicht verschwiegen.** Fehlt bei einer Zutat die Angabe oder
steht sie ohne Menge im Rezept („Olivenöl nach Bedarf“), ist die Summe eine Untergrenze
– und das steht dann dabei, mit Namen:

```
je Portion   288 kcal   9 g Kohlenhydrate   23,7 g Fett   11,2 g Eiweiß
Mindestens so viel – ohne Angabe: Basmatireis
```

Eine stillschweigend zu niedrige Kalorienzahl wäre schlechter als gar keine – dieselbe
Haltung wie bei den Einheiten, die lieber abgelehnt als geraten werden. Ausnahme: trägt
eine Zutat überall Nullen (Salz, Pfeffer), ändert auch eine unbekannte Menge nichts, und
das Gericht gilt trotzdem als vollständig gerechnet.

Die Artikel-Seite zeigt im Kopf, wie weit die Erfassung ist (`30 im Korpus · 30 mit
Nährwerten`). Es lohnt sich, bei den kalorienstarken Zutaten anzufangen – Reis, Nudeln,
Kartoffeln, Öl, Käse, Fleisch; das lange Ende der Gemüsesorten bewegt die Summe kaum.

> Der Planer benutzt die Werte **nicht**. Wenn er das später soll, kostet es ein
> weiteres Gewicht in `setting` – genauso wie der Angebots-Bonus. `general_plan.md`
> zählt Nährwerte unter „Bewusst nicht geplant“; die Anzeige hier ist die kleine
> Variante davon, ohne Diät-Funktionen.

## Wie geplant wird

Jeder Slot hat einen Bedarf (Esser zu Hause + Mitnehm-Portionen, Zeitbudget). Jedes
Gericht bekommt einen Score – und **der Score ist die Begründung**: eine Liste benannter
Beiträge, die die UI direkt anzeigt. Es gibt keinen zweiten Erklärungspfad.

**Harte Kriterien** (Gericht scheidet aus): bei *wenig Zeit* ein Gericht, das nicht
*schnell* ist · bei *keiner Zeit* jedes Gericht (nur Reste) · nicht
mitnehmbar, obwohl der Slot Mitnehm-Portionen braucht · Portionen reichen nicht · nicht
*aufwärmbar*, aber es bliebe etwas übrig · falsche Mahlzeit · diese Woche schon eingeplant.

**Aufwärmbar:** Was sich nicht aufwärmen lässt (Schalter am Gericht aus), schlägt der
Planer nur in einer Größe vor, die genau aufgeht – ein 3er-Gericht also nur, wo drei
Portionen gebraucht werden, verdoppelt nur für vier. Reste entstehen daraus nie. Von Hand
geht es trotzdem; dann meldet der Plan „nicht aufwärmbar – 1 Portion bliebe übrig“.

**Vervielfachen:** Ein 2-Portionen-Gericht lässt sich verdoppeln, wenn der Schalter
*doppelt möglich* am Gericht an ist – manches passt schlicht nicht in doppelter Menge in
die Pfanne, und das weiß nur die Küche, nicht der Planer. Ein 1-Portionen-Gericht ist ein
Rezept für eine Person; *doppelt möglich* und *dreifach möglich* lassen sich dort
gleichzeitig wählen, und der Planer bietet es in jeder erlaubten Größe an („Burger
(doppelt)“). 3-Portionen-Gerichte werden nie vervielfacht.

**Weiche Kriterien** (Gewichte in der DB, Seite *Einstellungen*): Abwechslung nach
Beilage / Protein / Küche, gestaffelt nach Abstand und **summiert** (das dritte Brot
kostet mehr als das zweite) · Rotation · Bewertung · Portionsgenauigkeit ·
Reste-Verwertung · Angebots-Ersparnis.

**Zeit und Aufwand:** Ein Gericht ist *normal* oder *schnell* (unter 20 Minuten), eine
Mahlzeit hat *normale*, *wenig* oder *keine Zeit* – Standard ist *normal*. Bei wenig Zeit
kommen nur schnelle Gerichte oder Reste in Frage (im Board eine kleine Uhr), bei keiner Zeit
nur Reste (eine Reste-Schale) – dafür kocht der Planer vorher entsprechend mehr. Punkte gibt
der Aufwand keine:
ein Bonus bekäme bei wenig Zeit ohnehin jedes frische Gericht und würde nur die Reste
zurücksetzen. Von Hand lässt sich trotzdem ein normales Gericht dorthin legen – dann
meldet sich der Plan mit einem Hinweis.

**Woche vorschlagen** plant die Woche als Ganzes (OR-Tools) und dauert etwa 2 Sekunden.
Gesucht ist der Plan mit der besten Gesamtpunktzahl – Reste eingeschlossen: wer allein isst,
bekommt bevorzugt Reste vom Vortag statt eines 2er-Gerichts für eine Person.

**Zufall:** Jedes „Woche vorschlagen“ zieht einen neuen Zufallswert (an der Woche
gespeichert, also nachstellbar), und jedes frische Gericht bekommt pro Mahlzeit bis zu
±*Zufall*/2 Punkte (Standard 6, Seite *Einstellungen*). Ähnlich gute Gerichte wechseln
sich so ab; eins mit klarem Abzug bleibt draußen. Weil der Zufall um null liegt, verschiebt
er Reste gegen Kochen nicht im Schnitt. Die angezeigten Punkte und Begründungen enthalten
keinen Zufall.
**Neu würfeln** zieht aus den fünf besten *anderen* Gerichten (jedes in seiner
bestpassenden Größe) und füllt eine Mahlzeit, die von den Resten des alten Gerichts
leben sollte, gleich neu.

**Raster bearbeiten:** Jede Mahlzeit zeigt nur, was eingestellt ist; Antippen öffnet
ein kleines Menü mit *2 zu Hause*, *1 zu Hause*, *niemand da* und *1 zu Hause + 1
mitnehmen*, dazu den Schalter *wenig Zeit*. Alles Seltenere (2 mitnehmen, nur
mitnehmen …) steht unter *Anpassen*. Der Knopf *niemand da* neben dem Tagesnamen stellt
den ganzen Tag um.

**Niemand da** nimmt einer verplanten Mahlzeit ihr Gericht samt davon abhängiger Reste
aus dem Plan – und von der Einkaufsliste. Damit das nicht unbemerkt passiert, bleibt das
Gericht beim Bearbeiten klein in der Zelle stehen; das Menü sagt vorher „… fällt dann
weg“, die Zelle danach „… fällt weg“.

**Standardwoche** (Seite *Einstellungen*): Mit diesem Raster startet jede neue Woche –
etwa Wochenende frei, Dienstagabend 1 + 1 frisch. Schon angelegte Wochen bleiben, wie
sie sind; für Ausnahmen gibt es weiter „wie letzte Woche“.

**Gekocht oder ausgefallen:** Der Plan ist zugleich der Koch-Verlauf. Ein geplantes
Gericht zählt ab seinem Tag als gekocht – dafür muss niemand etwas abhaken. Ist es
ausgefallen, die Karte antippen → *ausgefallen*; dann bleibt es durchgestrichen im Plan
stehen und zählt nicht (*doch gekocht* nimmt das zurück). Für die Abwechslung sieht eine
Woche alles, was in den Wochen davor geplant ist, auch wenn es noch bevorsteht – wer
Woche 43 plant, wiederholt nicht, was in 42 dran ist. Die Woche selbst zählt nicht als
ihr eigener Verlauf. Gerechnet wird in Kalenderwochen: Mittwoch letzter Woche ist am
Montag „vor 1 Woche“.

**Reste:** Ein 3-Portionen-Gericht für zwei Esser erzeugt eine Reste-Portion mit
Haltbarkeit 1–2 Tagen. Sie erscheint als eigene Karte in einem späteren Slot – aber nur,
wenn sie dessen Bedarf **ganz** deckt. Eine Portion ernährt keine zwei Esser, und ein
unterversorgter Slot wäre schlimmer als ein leerer, weil ihn niemand bemerkt.
Wie gern der Planer Reste einplant, steuern Gewichte (Seite *Einstellungen*): eine
Reste-Mahlzeit bringt 10 Punkte, +8, wenn einer allein isst, +15 bei wenig Zeit. Aus einem
Topf dürfen zwei Reste-Mahlzeiten kommen (verdoppelt), die zweite kostet 6 Punkte. Mittags
gekocht und abends dasselbe plant er nicht – außer abends ist keine Zeit.

**Mitnehmen** wird bei der Mahlzeit eingetragen, die *unterwegs gegessen* wird, und
verlangt ein mitnehmbares Gericht. *Frisch* wird in dieser Mahlzeit mitgekocht –
„Dienstag Abend, 1 zu Hause + 1 mitnehmen (frisch)“ für das Abendessen, das zu einem
Termin mitgeht; Reste kommen dort nicht in Frage. *Vorgekocht* füllt der Planer
bevorzugt mit Resten: „Dienstag Mittag, 1 mitnehmen“ aus dem Vorabend. Im Menü startet
Mitnehmen mit *frisch*, weil es so genutzt wird; ein Tipp schaltet um.

---

## Tests

```bash
cd backend && uv run pytest -m "not live"     # 393 Tests, parallel auf allen Kernen, ~20 s
cd frontend && npm test                        # 38 Tests: Wochen-Arithmetik, Formatierung, Raster
```

Ein Vorschlag kostet den Optimierer ~2 s und 10–15 CPU-Sekunden. Darum planen nur die Tests,
die das Vorschlagen selbst prüfen (`@pytest.mark.optimizer`), mit ihm – mit derselben
Rechenmenge wie die App. Alle anderen brauchen nur *einen* vollen Plan und nehmen den
Greedy-Plan. Einen einzelnen Test im Debugger: `uv run pytest -n0 …`.

| Ebene | Was sie absichert |
|---|---|
| `tests/domain/` | Score, Planer, Reste, Einheiten, Nährwerte – pure Funktionen, Millisekunden |
| Property-Tests | `PortionLedger`-Invarianten (nie überziehen, nie über die Haltbarkeit), Mengen-Aggregation |
| Golden-File | `propose()` auf einer realistischen Bürowoche → Gewichtsänderungen erzeugen einen lesbaren Diff |
| `tests/integration/` | Router + Service + Schema über `TestClient`, plus die echte Alembic-Migration |
| `tests/contract/` | Bring!-Diff gegen einen Fake, Korbunio gegen `respx`-Cassettes |
| Architektur-Test | `domain/` importiert kein I/O – die eine Grenze, die zählt |

Golden-File aktualisieren, wenn Gewichte sich absichtlich ändern:

```bash
cd backend && UPDATE_GOLDEN=1 uv run pytest tests/domain/test_golden_week.py
```

Die `live`-Tests (echtes Bring!-Konto, echter Korbunio) laufen nur manuell:

```bash
cd backend && uv run pytest -m live
```

---

## Wo was liegt

```
backend/src/mealplan/
  domain/          PURE: Score, Planer, Reste, Einheiten, Diagnostik  ← der Wert
  services/        Use-Cases, Transaktionen
  db/              SQLAlchemy + Mapper (ORM ↔ Domäne)
  integrations/    bring | offers | catalog  ← die fragilen Teile, hinter Ports
  api/             Router + Pydantic-DTOs
  cli/             mealplan-Kommandos
  ports.py         Protocols: ShoppingListSync, OfferSource, BringCatalog, LlmPort
frontend/src/
  api/             aus /openapi.json generiert (npm run gen:api)
  features/week/   Board, SlotCard, CandidateSheet, GridEditor
  features/dishes/ Schnellerfassung, Zutatenzeilen, Kategorie-Chips
```

Die eine Trennlinie, die sich lohnt: **`domain/` ist I/O-frei**, abgesichert durch einen
Test, der die Importe prüft. Alles andere ist absichtlich flach – Services sprechen
SQLAlchemy direkt, kein Repository-Interface, kein CQRS.

---

## Offene Punkte

- **Score-Gewichte final kalibrieren.** Die Defaults sind Startwerte; die echte
  Kalibrierung braucht eure echte Gerichteliste. Weg: `mealplan plan` mit verschiedenen
  Gewichten, oder direkt auf der Seite *Einstellungen*.
- **Angebote, Stufe 2 und 3:** Zuordnungen bestätigen/korrigieren, „gibt's dort nicht“
  pro Laden; Bonus im Planer auf „Zutat im Angebot“ statt Ersparnis umstellen (die
  Quellen liefern kaum „statt“-Preise), Hinweise auf der Einkaufsliste.
- **Einkaufsliste in Kaufeinheiten:** „2 Dosen Mais“ statt „570 g Mais“, „1 Avocado“ statt
  „140 g Avocado“ – über das Stückgewicht plus eine Bezeichnung pro Artikel (Stück, Dose,
  Bund). Das Stückgewicht wirkt bisher nur auf den Angebotsvergleich.
- **Einkaufs-Split** (Haupt- vs. Zweitladen) ist als Domänenfunktion vorgesehen, aber
  ohne Angebotsdaten wertlos – kommt mit Phase 2.

## Erfolgskriterium

Nicht die Feature-Liste, sondern: Findet das Montags-Ritual nach drei Wochen noch statt,
und dauert es unter fünf Minuten? Messbar an der Zahl manueller Korrekturen nach dem
Auto-Vorschlag und der Zahl der Einträge, die ihr hinterher doch von Hand in Bring!
getippt habt.
