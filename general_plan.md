# Wochenplan- & Einkaufs-App – High-Level-Planung

## 1. Kontext

Jeden Montag entsteht bei euch derselbe Aufwand: Aus einer Liste bekannter Gerichte einen Wochenplan bauen, der zu Bürotagen, Zeitbudget und Abwechslung passt, daraus eine Einkaufsliste in Bring! tippen und nebenbei prüfen, was gerade im Angebot ist. Die App soll diese drei Schritte in einen Fluss bringen: **Randbedingungen eingeben → Plan (vorgeschlagen oder assistiert) → Einkaufsliste prüfen → nach Bring! pushen → Angebote sehen.**

Ziel dieses Dokuments: Features festlegen und priorisieren, sinnvolle Zusatzfeatures aus vergleichbaren Apps vorschlagen, Stolpersteine benennen und für jeden eine recherchierte Lösung angeben. Keine Systemarchitektur.

## 2. Getroffene Entscheidungen (aus den Rückfragen)

| Thema | Entscheidung |
|---|---|
| Läden | Edeka (Markt „Allfrisch“, Angebote in der Edeka-App), **Aldi Nord**, **Netto Marken-Discount**, Rewe |
| Bring! | Bleibt die Liste im Laden. App erzeugt die Liste und pusht nach Bring!; Abhaken passiert in Bring! |
| Planung | Beides: automatischer Wochenvorschlag **und** assistiertes Befüllen einzelner Slots über eine nach Passgenauigkeit sortierte Gerichteliste |
| Gerichte-Daten | Name, Eigenschaften, Zutaten mit Mengen; optional Zubereitung als einfacher Text |
| Mahlzeiten | Mittag **und** Abend werden als volle Gerichte geplant. Pro Woche wird vorab angegeben, an welchen Tagen Mittag/Abend für wie viele Personen mitgenommen wird. Frühstück nicht |
| Randbedingungen | Manuelles Wochenraster pro Woche (Bürotage, Zeitbudget, auswärts) |
| Vorrat | Keine Vorratsverwaltung. Vor dem Bring!-Sync wird die Liste angezeigt und Vorhandenes abgehakt |
| Angebote | Fließen als Bonus ins Gerichte-Ranking ein und werden auf der Einkaufsliste angezeigt |
| Einkaufen | Meist ein Großeinkauf in einem Laden. Aufteilen nur, wenn etwas nur woanders zu bekommen ist oder es sich deutlich lohnt. Dann muss der erste Einkauf mindestens Montag und Dienstagmittag abdecken |
| Portionen | Gerichte haben 2 oder 3 Portionen. 2er-Gerichte können verdoppelt werden (4 Portionen). Keine anderen Skalierungen |
| Gerät | Wochenplanung am Laptop, Gerichte-Pflege / Listen-Check / Angebote am Handy → responsive Web-App |
| Hosting | Zuhause (Heimserver, NAS oder Raspberry Pi). Angebots-Abrufe laufen über eure Heim-IP |
| Einkaufstag | Fest Montag. Montagmittag ist normal planbar; ein Slot kann explizit als „aus Vorhandenem / Reste“ markiert werden, dann fließen keine Zutaten in die Liste |
| Bestand Gerichteliste | Noch nicht digital → Erfassung direkt in der App, Schnellerfassung ist Pflicht |
| Eigenbau | Bestätigt. Bausteine: `bring-api`, Korbunio, RapidFuzz |
| Stack (Notiz) | Python-Backend, Web-Frontend frei wählbar. Keine Architekturentscheidung in diesem Dokument |

## 3. Fachliches Datenmodell (grob)

- **Gericht**: Name; Portionen (2 oder 3, 2er-Gerichte verdoppelbar); mitnehmbar (ja / nein); Aufwand (schnell < 20 min / normal / aufwendig); geeignet für (Mittag / Abend / beides); Kategorien für Abwechslung (Sättigungsbeilage: Reis, Nudeln, Kartoffeln, Brot …; Protein: Fisch, Hähnchen, Hirtenkäse, Hülsenfrüchte, vegetarisch …; Küche); Zutaten mit Menge und Einheit; optional Zubereitungstext; Notizen; Bewertung; zuletzt gekocht (automatisch aus dem Plan).
- **Artikel** (euer Artikelkorpus, ~100–200 Stück): kanonischer Name, Einheit, Kategorie (für Bring!-Icon), Flag „Grundvorrat“ (Salz, Öl, Gewürze: landet nur auf Wunsch auf der Liste), Flag „Stammartikel“ (Angebots-Watchlist), Bring!-Katalogname, pro Laden: Verfügbarkeit ja/nein und Mapping auf Angebotsnamen/Marken.
- **Woche**: 7 Tage × 2 Slots (Mittag, Abend). Pro Slot: Esser zu Hause (0–2), Mitnehm-Portionen (0–2), Zeitbudget (viel / wenig / keins), Sonderfall „auswärts“ oder „Reste“. Zuweisung: Gericht (einfach oder verdoppelt), Reste-Portionen aus einem früheren Slot, oder Markierung „aus Vorhandenem“. Außerdem pro Woche: Hauptladen und optional Zweitladen (Einkauf ist fest montags).
- **Laden**: Name, Kette (Edeka / Aldi Nord / Netto MD / Rewe), Angebotsquelle und Markt-ID, Flag „Hauptladen“.
- **Einkaufsliste**: aggregierte Zutaten der Woche + manuell ergänzte Stammartikel; Status „prüfen“ → „nach Bring! gesendet“.
- **Angebot**: Laden, Artikelname (Laden), Preis, Aktionspreis, gültig von/bis, Quelle, Zeitstempel; verknüpft mit eurem Artikel über das Mapping.

## 4. Planungslogik (Kern der App)

**Grundidee:** Jeder Slot hat einen Bedarf (Portionen zu Hause + Mitnehm-Portionen, Zeitbudget). Jedes Gericht bekommt pro Slot einen **Passungs-Score**. Daraus entstehen die sortierten Listen für die assistierte Planung, und der Auto-Vorschlag ist nur „Slots nacheinander mit dem besten Kandidaten füllen und danach durch Tauschen verbessern“.

**Harte Kriterien (Gericht scheidet aus):**
- Aufwand passt nicht zum Zeitbudget des Slots.
- Slot braucht Mitnehm-Portionen für den nächsten Tag, aber Gericht ist nicht mitnehmbar.
- Portionen reichen nicht für Esser + Mitnehmen.

**Weiche Kriterien (Score):**
- Abwechslung: gleiche Sättigungsbeilage oder gleiches Protein wie am Vortag/in derselben Woche → Abzug, gestaffelt nach Abstand.
- Rotation: lange nicht gekocht → Bonus; letzte 2 Wochen gekocht → Abzug.
- Bewertung / Favoriten → Bonus.
- Angebote: Zutaten des Gerichts diese Woche im Angebot → Bonus proportional zur Ersparnis.
- Reste-Verwertung: übrig bleibende Portionen, die kein späterer Slot braucht → Abzug (Lebensmittelverschwendung); übrig bleibende Portionen, die genau den Mitnehm-Bedarf am nächsten Tag decken → Bonus.
- Saison (optional, Phase 3).

**Reste-Logik:** Kocht ihr abends ein 3-Portionen-Gericht zu zweit, entsteht eine Reste-Portion mit Haltbarkeit 1–2 Tage. Der Planer deckt damit bevorzugt den Mitnehm-Bedarf des nächsten Tages oder einen Home-Office-Mittagsslot. Ein Slot kann also statt eines neuen Gerichts „Reste von Montag Abend“ enthalten. Ein verdoppeltes 2er-Gericht (4 Portionen) deckt zwei Mitnehm-Portionen oder ein weiteres volles Essen am nächsten Tag.

**Einkaufs-Bezug:** Einkauf ist montags. Jeder Slot (typisch Montagmittag) kann manuell als „aus Vorhandenem“ markiert werden; dann wird dort ein Gericht ohne Einkaufsbedarf geplant oder frei gelassen, und seine Zutaten landen nicht auf der Liste. Wird der Einkauf auf zwei Läden aufgeteilt, müssen alle Gerichte bis einschließlich Dienstagmittag komplett aus dem Hauptladen einkaufbar sein (harte Regel, siehe Abschnitt 7).

**Auto-Vorschlag:** Slots in Reihenfolge der Schwierigkeit füllen (erst die mit Mitnehm-Bedarf und wenig Zeit), jeweils bester Kandidat; danach paarweise Tauschen, solange der Gesamtscore steigt; „Neu würfeln“ pro Slot mit leichtem Zufallsanteil. Ein Constraint-Solver (OR-Tools) ist bei ~100 Gerichten × 14 Slots unnötig, kann später nachgerüstet werden. Jeder Vorschlag zeigt seine Begründung („passt, weil: mitnehmbar, 3 Portionen, seit 5 Wochen nicht gekocht, Lachs bei Rewe im Angebot“).

**Assistierte Planung:** Slot anklicken → Liste aller zulässigen Gerichte, sortiert nach Score, mit Begründung und Warnhinweisen. Gepinnte Gerichte („Freitag will ich Pizza“) bleiben beim Neu-Vorschlagen fest.

## 5. Features nach Phasen

Leitprinzip aus der Recherche: Meal-Planning-Apps sterben nach drei Wochen an Pflegeaufwand (Vorratsverwaltung, Pflichtfelder, Zutaten-Normalisierung) oder an starren Plänen, die bei der ersten Störung kippen. Das Montags-Ritual muss in unter fünf Minuten durchlaufen: **Raster ausfüllen → Vorschlag → zwei, drei Tauschs → Liste prüfen → Bring!**

### Phase 0 – Daten rein (ein bis zwei Abende)
- Die Gerichteliste existiert noch nicht digital. Darum gehört eine **Schnellerfassung** zum ersten Baustein: ein Freitextfeld pro Gericht („Hirtenkäse-Reispfanne, 3 Portionen, mitnehmbar, schnell: 250 g Basmatireis, 200 g Hirtenkäse, 1 Zucchini, …“), das ein LLM in das Schema überführt und ihr nur noch bestätigt. Alternativ Foto eines Zettels. Kategorien für Abwechslung werden dabei automatisch vorgeschlagen.
- Artikelkorpus entsteht nebenbei aus den Zutaten: Bring!-Katalognamen per Fuzzy-Vorschlag zuordnen, Grundvorrat-Flags setzen, Einheit pro Artikel festlegen.
- Ziel: 30–50 Gerichte am ersten Abend, Rest im Alltag nachziehen.

### Phase 1 – MVP: Planen und nach Bring! pushen
- **Gerichte verwalten**: minimales Formular, Zutaten als Zeilen (Menge, Einheit, Artikel), optionaler Zubereitungstext, Kategorien, Aufwand, Portionen, mitnehmbar. Schnell am Handy editierbar.
- **Wochenraster** pro Person und Tag: zu Hause / Büro (Mitnehmen) / auswärts; Zeitbudget pro Slot. Wochen kopieren („wie letzte Woche“).
- **Assistierte Planung**: Slot anklicken → sortierte Kandidatenliste mit Score, Begründung und Warnungen. Drag & Drop am Laptop, Tippen-und-Tauschen am Handy.
- **Auto-Vorschlag** für die ganze Woche oder für leere Slots, Pins bleiben stehen, „Neu würfeln“ pro Slot.
- **Reste-Logik** automatisch: übrige Portionen erscheinen als eigene Reste-Karte im Folgeslot (Muster „Plan as Leftover“ von Plan to Eat) und können verschoben werden.
- **Warnungen** im Plan: dreimal Reis, Dienstag nichts zum Mitnehmen, Aufwand passt nicht zur Zeit, Portion bleibt übrig.
- **Einkaufsliste**: Zutaten der Woche aggregiert (Einheiten normalisiert), Grundvorrat ausgeblendet, Stammartikel per Klick ergänzbar, Abhaken „haben wir schon“, dann **Push nach Bring!** (eigene Einträge aktualisieren statt duplizieren). Fallback: Liste als Text kopieren / teilen.
- **Historie**: „zuletzt geplant“ automatisch, „gekocht?“ als Ein-Klick-Bestätigung am Folgetag. Vermeidet, dass ausgefallene Gerichte als gekocht zählen.
- **Zwei Nutzer**, ein gemeinsamer Haushalt, Namen für die Mitnehm-Zuordnung. Zugriff von außen per Tailscale/WireGuard oder Cloudflare Tunnel, App als PWA auf dem Homescreen.

### Phase 2 – Angebote
- Angebots-Abruf per Cron (Korbunio-Adapter, marktguru als zweite Meinung), Wochen-Snapshot.
- **Mapping-Pflege**: Alias-Liste pro Artikel, Verfügbarkeit pro Laden, „Unzugeordnet“-Ansicht mit Ein-Klick-Zuordnung, LLM-Vorschlag für Grenzfälle.
- Angebote auf der Einkaufsliste anzeigen (Laden, Preis, Ersparnis, gültig bis) und pro Laden gruppieren.
- **Stammartikel-Watchlist**: Artikel, die ihr regelmäßig braucht, werden bei Angebot vorgeschlagen („Kaffee bei Aldi 4,99 €, mit auf die Liste?“).
- **Angebots-Bonus im Ranking** und eine Ansicht „Gerichte, die diese Woche günstig sind“.
- **Einkaufs-Split-Vorschlag** mit Ersparnis in Euro, Regel „bis Dienstagmittag alles aus dem Hauptladen“, zwei Bring!-Listen oder Abschnitte.
- Aldi-Nord-Vorschau der Folgewoche in die Planung einbeziehen.

### Phase 3 – Komfort (nach Bedarf, aus vergleichbaren Apps übernommen)
- **Bewertung und Notiz nach dem Kochen** („nächstes Mal weniger Salz“, „doppelte Sauce“), direkt an der Plan-Karte.
- **Wochenvorlagen / Rotation**: bewährte Wochen als Vorlage speichern (A/B/C-Wochen), Vorlage als Startpunkt laden.
- **Kalender-Export (iCal)** für den gemeinsamen Handy-Kalender.
- **Gefrierfach-Portionen**: eingefrorene Reste als planbare Slots, ohne allgemeine Vorratsverwaltung.
- **Kosten pro Gericht** aus Angebots- und Normalpreisen, Wochenbudget-Anzeige.
- **Saisonalität** als kleiner Bonus im Score.
- **Umplanen unter der Woche**: Nach dem Einkauf bevorzugt der Planer beim Tauschen Gerichte, deren Zutaten schon gekauft sind.
- **Push-Benachrichtigung** über Bring! („Liste ist aktualisiert“) oder bei Angeboten für Stammartikel.
- **LLM-Helfer**: Rezept-URL oder Foto einer Rezeptseite in ein Gericht umwandeln; freie Wünsche („diese Woche einmal asiatisch“) als Filter für den Vorschlag. Kein LLM als Planer selbst, weil nicht deterministisch und schlecht bei Portions- und Abstandsregeln.
- **Kauf-Historie aus Bring!** (abgehakte Artikel) zur Verfeinerung der Stammartikel-Liste.

### Bewusst nicht geplant
- Echte Vorratsverwaltung mit Beständen (Grocy-Falle, hoher Pflegeaufwand).
- Bidirektionaler Bring!-Sync (fragil, Duplikate). Bring! bleibt beim Einkaufen die Wahrheit.
- Nährwerte und Diät-Funktionen.
- Frühstück.

### Eigenbau vs. bestehendes Tool
Tandoor, Mealie und Grocy decken Rezeptverwaltung, Einkaufsliste und Teilen ab, aber **kein untersuchtes Tool modelliert euren Kern**: Portionen-Reste als Kette („3 Portionen heute → 1 Mitnehm-Portion morgen“), Anwesenheit pro Person und Tag, wöchentlich wechselndes Zeitbudget, globale Abwechslungsregeln, Angebotsabgleich. Mealie hat globale Regeln wie „max. X Fleischgerichte“ als „not planned“ geschlossen, Tandoor braucht für Auto-Planung das Drittprojekt Morsl, Grocy erzwingt Vorratspflege. Eine Bring!-Anbindung fehlt allen dreien nativ. Der Wert liegt also im Datenmodell und in der Planungslogik, beides klein und gut testbar. **Empfehlung: Eigenbau**, aber Bausteine wiederverwenden: `bring-api` für Bring!, Korbunio für Angebote, RapidFuzz für Matching.

## 6. Bring!-Anbindung – Recherche und Vorgehen

**Befund:**
- Es gibt **keine offizielle Bring!-API** für Einkaufslisten. Offiziell existiert nur der Rezept-Import-Deeplink (`api.getbring.com/rest/bringrecipes/deeplink?url=…`), der eine öffentlich erreichbare Seite mit schema.org/Recipe-Markup braucht und in einem manuellen Import-Dialog in der App endet. Für stilles Synchronisieren ungeeignet. Quelle: Bring! Import Dev Guide (sites.google.com/getbring.com/bring-import-dev-guide).
- Die **inoffizielle API** ist gut erschlossen: Python-Paket `bring-api` (miaucl, Basis der Home-Assistant-Integration, letzte Version 1.1.2 vom Mai 2026, aktiv gepflegt) und Node-Paket `bring-shopping`. Funktionen: Login per E-Mail/Passwort mit Token-Refresh, Listen laden, Items anlegen/ändern/abhaken/entfernen, Batch-Updates, Vorlagen anlegen, Push-Benachrichtigung an Mitnutzer.
- **Stabilität:** 1–2 Brüche pro Jahr durch Backend-Änderungen bei Bring! (03/2024 Locale-Datei, 10/2025 Login-Feld, 04/2026 neues Angebots-Attribut), jeweils innerhalb von Tagen bis Wochen im Paket gefixt. Keine Berichte über Rate-Limits oder Account-Sperrungen. AGB enthalten keine API-/Bot-Klausel, aber Bring! darf Nutzer jederzeit ausschließen.
- **Artikelnamen:** Icon und Kategorie gibt es nur, wenn der Name exakt einem Eintrag im frei abrufbaren Katalog (`web.getbring.com/locale/catalog.de-DE.json`, ~380 Artikel, plus `articles.de-DE.json` mit ~500 Synonymen) entspricht. Mengen sind kein strukturiertes Feld, sondern der Freitext „Spezifikation“ („500 g“).
- Bring! hat seit 2024/2026 eigene Prospekt-Angebote (Kaufland, Penny, Netto u. a.) mit Übernahme auf die Liste. Diese Daten sind über die API nicht sinnvoll abrufbar und ersetzen euren Angebotsabgleich nicht (Edeka, Aldi Nord, Rewe fehlen).

**Vorgehen:**
1. `bring-api` (Python) als Sync-Adapter, isoliert in einem eigenen dünnen Modul, sodass ein Bruch nur den Sync betrifft und die App weiterläuft.
2. **Eigenes Bring!-Konto für die App** anlegen (z. B. `name+app@…`) und zur gemeinsamen Liste einladen. Vorteile: Sperr-Risiko trifft nur den Bot-Account, Push-Nachrichten an euch funktionieren, eure Passwörter bleiben aus der App heraus.
3. Eventgetrieben schreiben (ein Batch-Update pro „Liste senden“), nicht pollen. Eigene UUIDs pro Item speichern, damit nur eigene Einträge geändert werden und manuell in Bring! Ergänztes unangetastet bleibt.
4. Zutaten-Namen beim Anlegen eines Artikels einmalig auf den Bring!-Katalog mappen (Vorschlag per Fuzzy-Match, Bestätigung durch euch). Mengen in der App aggregieren und formatiert in die Spezifikation schreiben.
5. Rücklesen: „recently“ in Bring! = gekauft. Damit kann die App später Kauf-Historie ableiten (z. B. wie oft Hirtenkäse gekauft wird), ist aber kein MVP-Feature.
6. Frühwarnsystem: Home-Assistant-Issues mit Label `integration: bring` und `bring-api`-Releases beobachten. Plan B ohne Reverse-Engineering: Todoist (offizielle API, geteilte Projekte) oder die App-eigene Liste. Der Adapter macht den Wechsel billig.

## 7. Angebotsdaten – Recherche und Strategie

**Wichtigster Befund:** Es gibt ein aktiv gepflegtes Open-Source-Projekt, das genau dieses Problem schon löst: **Korbunio** (github.com/lesecuritae/Korbunio, Python/FastAPI, Docker, BSD-Lizenz, letzter Commit September 2026). Es hat funktionierende Adapter für Edeka (marktgenau), Aldi Nord, Netto Marken-Discount (filialgenau), Rewe (marktgenau) sowie marktguru und kaufDA als Aggregatoren, cached Angebote bis zum Wochenwechsel und bietet einen REST-Endpunkt `POST /api/v1/compare` mit PLZ und Suchbegriffen. Die Release-Notes zeigen auch die realistische Wartungslast: Aldi- und Rewe-Adapter mussten mehrfach nachgebessert werden.

**Regionaler Kontext:** „Allfrisch“ ist ein Marktname der Edeka-Kaufleute Cord & Kutsche (Regionalgesellschaft Edeka Minden-Hannover). Edeka-Angebote sind tatsächlich pro Markt unterschiedlich, darum braucht ihr eine markt-genaue Quelle, nicht nur „Edeka-Angebote in der Region“.

**Datenquellen pro Kette (Stand September 2026):**

| Kette | Erste Wahl | Filialgenau | Zuverlässigkeit | Fallback |
|---|---|---|---|---|
| Edeka (Allfrisch) | Inoffizielle Website-API `edeka.de/eh/service/eh/offers?marketId=…` (Markt-ID einmalig über `edeka.de/api/marketsearch/markets?searchstring=…`). Felder: Titel, Preis, Beschreibung, Grundpreis, Warengruppe, gültig von/bis, Bild. Braucht Browser-TLS-Fingerprint (`curl_cffi`), sonst HTTP 403 | Ja | Mittel bis hoch | Offizielle App-API `b2c-gw.api.edeka` (saubere Felder, aber Token aus dem App-Login, der auch Zahlungen autorisieren kann → nur mit separatem Edeka-Konto); marktguru; Markt-Prospekt + LLM-Vision |
| Aldi Nord | `aldi-nord.de/angebote.html` liefert eingebettetes JSON (`__NEXT_DATA__`) mit Preis, Grundpreis, Pfand, Bild, gültig von/bis. Kein Browser nötig. Vorschau nächste Woche unter `/angebote-vorschau.html` | Nein, bundesweit | Hoch | marktguru |
| Netto Marken-Discount | Store-Finder-Endpunkt für die Filial-ID, dann Angebotsseite auf `netto-online.de` mit `curl_cffi` | Ja | Mittel (aggressiver Bot-Schutz) | marktguru mit Händlerfilter; Prospektbilder + Vision |
| Rewe | Marktsuche auf rewe.de, dann Angebotskarten über `rewe.de/api/frontend-includes` mit `curl_cffi`, Chromium nur als Fallback | Ja | Mittel | Mobile-API mit Client-Zertifikat aus der App (Projekte `rewerse-engineering`, `ha-rewe`; funktioniert Stand August 2026, Zertifikat rotiert mit App-Versionen); marktguru |
| Alle | marktguru inoffizielle API (`api.marktguru.de/api/v1/offers/search?q=…&zipCode=…`, Schlüssel aus dem Frontend, seit 2022 stabil). Strukturierte Daten inkl. Marke, Preis, Altpreis, Gültigkeit | Nein, PLZ-basiert; Edeka-Kaufleute liefern nicht immer Prospekte ein | Mittel | kaufDA (eingebettetes JSON pro Stadt und Händler) |

Keine der Quellen liefert EAN/GTIN. Keine der vier Ketten hat eine offizielle Angebots-API für Privatpersonen. Bring!s eigene Prospekt-Funktion (Kaufland, Penny, Netto) ist über die API nicht abrufbar und deckt Edeka, Aldi Nord und Rewe nicht ab.

**Angebotszyklen:** Aldi Nord Food ab Montag, Non-Food ab Donnerstag; Rewe und Netto Mo–Sa; Edeka regional, teils Sonntag-Start. Aldi Nord veröffentlicht die Vorschau der Folgewoche, was für die Planung am Montag nützlich ist.

**Strategie (in dieser Reihenfolge):**
1. **Korbunio als Docker-Container** neben der App starten und mit eurer PLZ und Beispielartikeln testen. Deckt es die vier Läden zuverlässig ab, ist das Beschaffungsproblem gelöst und ihr schreibt keinen eigenen Scraper. Der eigene Code beschränkt sich auf einen Adapter, der Korbunio-Ergebnisse in euer Angebots-Schema überführt.
2. Falls Korbunio nicht passt oder stirbt: eigene Minimal-Pipeline nach dem Muster der Korbunio-Adapter (Python, `curl_cffi` mit Chrome-Impersonation, kein Browser). Ihr habt einen Heimserver, also eine normale Wohnungs-IP, was den Bot-Schutz deutlich entschärft.
3. **marktguru als zweite Meinung** für alle Ketten: erkennt Ausfälle der Primärquelle (0 Treffer) und füllt Lücken.
4. **LLM-Vision auf Prospektbildern nur als Notschalter**, am ehesten für Edeka (Markt-Prospekt unter `edeka.de/markt-id/<id>/prospekt.jsp`). Erfahrungswerte liegen bei ~90 % Genauigkeit, Kosten im Cent-Bereich pro Woche. Fehlerquellen: „versch. Sorten“, Grundpreis, „ab Donnerstag“.
5. Abruf per Cron **Montag und Donnerstag früh**, Ergebnis als Wochen-Snapshot speichern, letzter guter Snapshot bleibt bei Fehlern erhalten, Bilder lokal spiegeln.

**Produkt-Matching (euer Artikel → Angebot):**
- Pro Artikel eine Alias-Liste pflegen („Hirtenkäse“ → Hirtenkäse, Schafskäse, Feta, Weichkäse in Salzlake) plus Eigenmarken-Namen (Gut & Günstig bei Edeka und Netto MD, ja! bei Rewe, Milsani/Milfina bei Aldi). Bei 100–200 Artikeln ist das in ein bis zwei Stunden erledigt und war ohnehin euer Plan.
- Normalisierung (Kleinschreibung, Umlaute, Mengen-Regex, Warengruppe als Filter) und Fuzzy-Matching mit RapidFuzz (`token_set_ratio`, Schwelle ~85) gegen die Alias-Liste.
- LLM als Schiedsrichter nur für Grenzfälle („Ist Angebot X mein Artikel Y?“). Bestätigte Treffer werden gespeichert, damit dieselben Angebote in Folgewochen ohne LLM matchen.
- Pro Artikel und Laden: „nicht verfügbar“ setzen, dann wird dort gar nicht gesucht.
- Nicht-Treffer landen in einer „Unzugeordnet“-Ansicht, in der ihr mit einem Klick ein Mapping anlegt. So wächst die Tabelle im Alltag.

**Aufteilen des Einkaufs:** Die App berechnet pro Woche „Hauptladen komplett“ vs. „Hauptladen + Zweitladen“, zeigt die Ersparnis in Euro und schlägt den Split nur vor, wenn (a) ein Artikel im Hauptladen nicht verfügbar ist oder (b) die Ersparnis eine von euch gesetzte Schwelle (z. B. 5 €) übersteigt. Harte Regel: Alle Zutaten für Gerichte bis Dienstagmittag müssen aus dem Hauptladen kommen. Bei Split entstehen zwei Bring!-Listen oder zwei Abschnitte in einer Liste.

**Rechtslage (privat, nicht kommerziell, zwei Abrufe pro Woche):** Nach BGH-Rechtsprechung (Automobil-Onlinebörse 2011, Flugvermittlung 2014) verletzt das Abrufen unwesentlicher Datenmengen kein Datenbankrecht, AGB-Verstöße sind keine Umgehung technischer Schutzmaßnahmen, und das Wettbewerbsrecht greift nur bei geschäftlichem Handeln. Grauzone bleibt das Umgehen technischer Hürden (TLS-Impersonation, Client-Zertifikat aus der Rewe-App). Realistische Konsequenz im schlimmsten Fall: IP-Sperre. Hygiene: niedrige Frequenz, keine Weitergabe der Daten, marktguru ohne Account nutzen (deren AGB verbieten automatisiertes Auslesen, binden aber nur mit Account), Rewe-Web-Pfad statt Zertifikat bevorzugen, Bilder lokal cachen statt hotlinken.

## 8. Stolpersteine und Lösungen (konsolidiert)

| # | Stolperstein | Lösung |
|---|---|---|
| 1 | **Bring!-API ist inoffiziell** und bricht 1–2× pro Jahr | Dünner Adapter, eigenes Bot-Konto, `bring-api` aktuell halten, Fehler nur loggen, Text-Export als Fallback, Todoist als Plan B |
| 2 | **Angebotsseiten haben Bot-Schutz** (Edeka, Netto, Rewe liefern 403 ohne Browser-Fingerprint) und ändern Endpunkte still | Korbunio oder `curl_cffi` mit Chrome-Impersonation von der Heim-IP; Schema-Prüfung pro Quelle; Alarm bei null Treffern; letzten guten Snapshot behalten; marktguru als zweite Meinung; Vision auf Prospekt als Notschalter |
| 3 | **Edeka-Angebote sind marktgenau**, Aggregatoren nur PLZ-genau | Markt-ID des Allfrisch-Marktes einmalig ermitteln und als Wahrheit nutzen, marktguru nur ergänzend |
| 4 | **Kein EAN in Angebotsdaten**, Matching ist textbasiert und unsicher | Alias-Tabelle pro Artikel, Eigenmarken-Namen, RapidFuzz, LLM nur für Grenzfälle, bestätigte Treffer speichern, „Unzugeordnet“-Ansicht |
| 5 | **Pflegeaufwand tötet die Nutzung** (häufigster Abbruchgrund) | Minimale Pflichtfelder, Zutaten als Zeilen, Import der bestehenden Liste per LLM, kein Vorratsbestand, Wochenraster in 30 Sekunden, „wie letzte Woche“ |
| 6 | **Starrer Plan kippt** bei spätem Meeting oder Kochunlust | Pin & Neu-würfeln pro Slot, Tausch zweier Tage, Reste-/Flex-Karten, Umplanen bevorzugt schon gekaufte Zutaten |
| 7 | **Auto-Vorschläge wirken willkürlich** (Erfahrung Eat This Much) | Score mit Begründung anzeigen, zwei bis drei Alternativen pro Slot, Vielfalts- und Rotationsregeln, Warnung bei zu kleinem Pool |
| 8 | **Bring!-Sync erzeugt Duplikate** | Nur Push Plan → Bring!, eigene UUIDs speichern, Items aktualisieren statt neu anlegen, Fremdeinträge nie anfassen |
| 9 | **Bring!-Icons fehlen** bei nicht-katalogkonformen Namen | Katalog (`catalog.de-DE.json`) laden, Zuordnung beim Anlegen eines Artikels bestätigen, Mengen als Spezifikation |
| 10 | **Mengen-Aggregation** über Gerichte („2 Zwiebeln“ + „150 g Zwiebeln“) | Einheiten pro Artikel festlegen (Stück, g, ml), Zutaten in dieser Einheit erfassen, Rest als „nach Bedarf“ ohne Menge |
| 11 | **„Zuletzt gekocht“ stimmt nicht**, wenn Gerichte ausfallen | „Zuletzt geplant“ automatisch plus Ein-Klick-Bestätigung „gekocht“ |
| 12 | **Rechtliche Grauzone** beim Scraping | Zwei Abrufe pro Woche, keine Weitergabe, marktguru ohne Account, Rewe-Web-Pfad statt App-Zertifikat, Edeka-App-API nur mit separatem Konto ohne Zahlungsmittel |
| 13 | **Heimserver von außen erreichen** | Tailscale/WireGuard oder Cloudflare Tunnel, PWA auf dem Homescreen; Bring! braucht keinen externen Zugriff auf euren Server |
| 14 | **Partner steigt aus**, wenn nur eine Person das Tool versteht | Montags-Ritual zu zweit am Laptop, Handy-Ansichten auf Lesen und kleine Änderungen beschränkt, keine Admin-Bereiche im Alltagsfluss |

## 9. Empfohlene Reihenfolge und Validierungs-Spikes

Vor dem eigentlichen Bau vier kurze Experimente, jeweils ein bis zwei Stunden, um die riskanten Annahmen zu prüfen:

1. **Spike Bring!**: Bot-Konto anlegen, zur gemeinsamen Liste einladen, mit `bring-api` eine Test-Liste beschreiben, Item mit Spezifikation anlegen, abhaken, wieder lesen. Prüfen, ob Icons bei Katalognamen erscheinen.
2. **Spike Korbunio**: Container mit eurer PLZ starten, prüfen, ob der Allfrisch-Markt als Edeka-Markt wählbar ist, zehn typische Artikel (Hirtenkäse, Basmatireis, Lachs, Hähnchenbrust, Kaffee …) über alle vier Ketten abfragen. Trefferqualität und Laufzeit notieren.
3. **Spike Edeka direkt** (nur falls Korbunio den Markt nicht abdeckt): Markt-ID über die Marktsuche holen, Angebots-Endpunkt mit `curl_cffi` abrufen, Felder ansehen.
4. **Spike Planungslogik auf Papier**: Eure echte Gerichteliste ins Schema bringen (Phase 0), eine reale Woche mit Bürotagen durchrechnen und prüfen, ob der Score sinnvolle Reihenfolgen liefert. Das entscheidet über die Gewichtungen, bevor UI gebaut wird.

Danach Bau in der Phasenreihenfolge aus Abschnitt 5. Phase 1 ist allein schon ein spürbarer Gewinn (kein Tippen in Bring! mehr, keine vergessenen Mitnehm-Portionen). Phase 2 erst, wenn ihr Phase 1 drei Wochen im Alltag durchgehalten habt.

**Verifikation im Alltag:** Erfolgskriterium ist, dass das Montags-Ritual nach drei Wochen noch stattfindet und unter fünf Minuten dauert. Messbar: Anzahl geplanter Wochen, Anzahl manueller Korrekturen nach dem Auto-Vorschlag, Anzahl Bring!-Einträge, die ihr nachträglich von Hand anlegen musstet.

## 10. Offene Punkte (für die Umsetzungsplanung, nicht für dieses Dokument)

- Konkrete Gewichtungen im Score (ergeben sich aus Spike 4).
- Frontend-Wahl und Datenbank (Architektur-Schritt nach Freigabe dieses Plans).
- PLZ / Adresse des Allfrisch-Marktes für die Edeka-Markt-ID (wird in Spike 2/3 einmalig ermittelt, gehört in eine lokale Konfiguration, nicht ins Repo).
- Ob Korbunio als Container reicht oder eigene Adapter nötig werden (Ergebnis von Spike 2).