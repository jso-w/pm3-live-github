# Projektplan – CaféGap Schweiz (DS.PM3)

## 1. Ziel und Umfang

**Forschungsfrage:** In welchen Schweizer Gemeinden gibt es im Verhältnis zur potenziellen Nachfrage eher viele oder wenige Cafés?

OSM-Cafés bilden das erfasste Angebot ab. Einwohner und Beschäftigte bilden einen Nachfrage-Proxy. Die Anwendung vergleicht die Café-Rate einer Gemeinde mit dem Schweizer Median ausreichend grosser Gemeinden.

Kern: MongoDB → Flask → Browser mit jQuery, LeafletJS und ChartJS. K-Means und Regression gehören ausschliesslich zu den Stretch Goals.

## 2. Bestehende Grundlage und geplante Struktur

`src/pm3/build_db.py` lädt swissBOUNDARIES3D und OSM-Daten, ordnet Cafés räumlich Gemeinden zu und schreibt `municipalities`, `amenities` und Importinformationen in `metadata`. `src/pm3/plots_examples_testing.py` erstellt lokale Testplots. Die vorhandene uv-Konfiguration, Docker-Konfiguration und Verzeichnisstruktur bleiben erhalten.

Geplante Ergänzungen unter `src/pm3/`: `app.py` (Flask), `config.py` (Parameter), `db.py` (Verbindung), `scripts/` (Statistikimport und Analyse), `templates/` und `static/` (Browseroberfläche). Diese Dateien und ihre Befehle sind noch nicht implementiert. Keine parallele Anwendung im Repository-Hauptverzeichnis anlegen.

## 3. Kennzahl und Sonderfälle

```text
D_i        = Einwohner_i + 0.5 × Beschäftigte_i
CafeRate_i = Cafés_i / D_i × 10'000
E          = Gemeinden mit gültigen Eingangsdaten und D_i ≥ 5'000
MedianRate = Median der CafeRate_i über E (ungewichtet pro Gemeinde)
Gap_i      = MedianRate − CafeRate_i
gap_rel_i  = Gap_i / MedianRate
```

D bezeichnet **Demand Units**, keine tatsächliche Anzahl Personen oder Kunden. Einwohner und Beschäftigte können sich überschneiden. Das Beschäftigtengewicht 0.5 ist eine Modellannahme.

- Gap > 0: relativ weniger Cafés als die Referenz; Gap < 0: relativ mehr Cafés.
- Gap hat die Einheit Cafés pro 10'000 Demand Units und bezeichnet keine absolute Zahl fehlender Cafés.
- `gap_rel` wird als Anteil gespeichert; 0.25 bedeutet 25 % unter der Referenzrate.
- Beispiel: MedianRate = 8, CafeRate = 6 → Gap = 2, gap_rel = 0.25.
- `MIN_DEMAND = 5000` ist der Ausgangswert. Die Schwelle mit echten Daten prüfen und ihre Begründung dokumentieren.
- Gemeinden unter der Schwelle bleiben sichtbar, sind auf der Lückenkarte grau und werden nicht gerankt. Ihre gültige Anzahl und Rate dürfen weiterhin angezeigt werden.
- Fehlende Einwohner-, Beschäftigten- oder Angebotsdaten sind nicht automatisch null. Ungültige Datensätze werden aus Median und Ranking ausgeschlossen und mit einem Grund gekennzeichnet. Ein bestätigter Café-Zählwert von null ist dagegen gültig.
- Bei D ≤ 0 ist CafeRate `null`. Bei leerer Referenzmenge sind Median, Gap und gap_rel `null`. Bei MedianRate = 0 bleibt Gap berechenbar, gap_rel ist `null`. Keine NaN-/Infinity-Werte in JSON ausgeben.
- Der Kantonfilter verändert die angezeigte Auswahl, aber niemals den Schweizer Referenzmedian.

Sensitivität: Gewichte 0.25, 0.5 und 0.75 vergleichen. Für jedes Gewicht D, Teilnahmeberechtigung, Schweizer Median und Ranking neu berechnen. Top-10-Überschneidung, Rangänderungen und Änderungen der berechtigten Gemeinden ausweisen. Stabilität erst nach Auswertung behaupten. Ergebnisse und Parameter in `/api/meta` und der Methodik-Box dokumentieren.

## 4. Browserfunktionen

| Funktion | Geplantes Verhalten |
|---|---|
| Gemeindekarte | Drei Modi: **Café-Lücke**, **Cafés pro 10'000 Demand Units**, **Anzahl Cafés**; passende Legenden und Kennzeichnung fehlender Daten |
| Gemeinde-Details | Name, Kanton, Einwohner, Beschäftigte, Demand Units, Café-Anzahl, Rate, Schweizer Median, Gap, gap_rel und Ranking-Berechtigung |
| Scatterplot | x = Demand Units, y = Café-Anzahl; jeder Punkt eine Gemeinde; Referenz **y = MedianRate / 10'000 × x** auf linearen Achsen |
| Verknüpfung | Gemeindeklick hebt den zugehörigen Scatterplot-Punkt hervor |
| Top 10 | Berechtigte Gemeinden mit positivem Gap, absteigend sortiert; bei Gleichstand BFS-Nummer aufsteigend; bei weniger Treffern kürzere Liste |
| Kantonfilter | Karte, KPIs, Scatterplot und Top 10 aktualisieren; Option ganze Schweiz; Schweizer Median bleibt konstant |
| Pflicht-Chart | Café-Anzahl pro Kanton mit ChartJS; Schweizer Übersicht, ausgewählten Kanton hervorheben |
| Methodik-Box | Formeln, Schwelle, Annahmen, Datenstand, Sensitivität und Limitationen |

Unterhalb der diagonalen Scatterplot-Linie liegen Gemeinden mit positiver Café-Lücke, oberhalb solche mit negativer Lücke. Kleine Gemeinden werden im Scatterplot gesondert gekennzeichnet. Die Referenz ist keine horizontale Median-Linie und kein Regressionsmodell.

Optionale Darstellung: Café-Marker ab Zoom 13 und Heatmap mit leaflet.heat. Diese Layer sind keine weiteren Kennzahlenmodi.

## 5. Daten-Pipeline

1. Vorhandenen Import über `uv run src/pm3/build_db.py` nutzen: Grenzen herunterladen, Schweizer Gemeinden laden, OSM-Cafés beziehen, räumlich zuordnen und nach MongoDB schreiben.
2. Datenqualität prüfen: Der aktuelle Import entfernt Gemeinden ohne positive Einwohnerzahl. Fehlende Gemeinden und nicht zugeordnete OSM-Objekte protokollieren; für eine vollständige Karte das Verhalten später gezielt erweitern.
3. Einwohnerdaten aus der Grenzdatei auf Bezugsjahr und Vollständigkeit prüfen; bei Bedarf BFS STATPOP ergänzen. Beschäftigte aus BFS STATENT beschaffen und über BFS-Gemeindenummern verbinden. Definition der Beschäftigten und Datenjahre festhalten; Gemeindefusionen berücksichtigen.
4. Analysemodul unter `src/pm3/scripts/` ergänzen: gültige Eingangsdaten, Demand Units, CafeRate, Berechtigung, Schweizer Median, Gap, gap_rel und Sensitivität berechnen. Nicht vorzeitig runden.
5. Analyseergebnisse separat speichern; mit Importversion und Parametern verknüpfen. Nach erneutem Basisimport die Analyse neu erzeugen, damit kein alter Datenstand angezeigt wird.
6. Flask liefert GeoJSON und JSON. Der Browser stellt Karte und Charts dar. Laufzeitbefehle erst nach Implementierung in die README aufnehmen.

Die Zuordnung erfolgt aktuell in LV95 mit ursprünglichen Gemeindegeometrien. Erst für die Speicherung werden Grenzen mit 20 m Toleranz vereinfacht und in WGS84 konvertiert. OSM-Ways und -Relations werden bereits zu repräsentativen Punkten verarbeitet. Rohdaten und Cache bleiben in den vorhandenen ignorierten Datenordnern.

## 6. MongoDB-Modell

Bestehende Collections und Feldnamen weiterverwenden:

| Collection | Vorhanden / geplante Ergänzung |
|---|---|
| `municipalities` | Vorhanden: `_id` = BFS-Nr., `name`, `canton_nr`, `population`, `area_km2`, `amenities.cafe.count`, `amenities.cafe.per_1000`, `geometry` |
| `amenities` | Vorhanden: `osm_id`, `category`, `name`, `municipality_id`, `location`, `tags` |
| `metadata` | Vorhanden: Importzeit, Grenzversion, Kategorien; geplant: Statistikquellen/-jahre und Analyseparameter als eigener Eintrag |
| `analysis` | Geplant: Gemeinde-ID, Beschäftigte, Demand Units, CafeRate, Gap, gap_rel, `ranking_eligible`, Ausschlussgrund und Datenversion |

Die bestehende Kennzahl `per_1000` bezieht sich auf Einwohner und ist nicht CafeRate. Sie bleibt für bestehende Testplots erhalten. Kantonskennzahlen aus Gemeinden aggregieren; Kantonskürzel für API und Anzeige eindeutig auf `canton_nr` abbilden. Bestehende 2dsphere-Indizes für Geometrien/Punkte verwenden und zusätzliche Analyseindizes bei Bedarf ergänzen.

## 7. API-Plan

Alle folgenden Endpoints sind geplant, noch nicht vorhanden.

| Endpoint | Zweck |
|---|---|
| `GET /api/kantone` | Kantons-GeoJSON und aggregierte Café-Anzahlen für den Pflicht-Chart |
| `GET /api/gemeinden?kanton=ZH` | Gemeinde-GeoJSON mit Analysefeldern; ohne Filter ganze Schweiz; Grundlage für Karte, Scatterplot und KPIs |
| `GET /api/top-luecken?kanton=ZH&limit=10` | Berechtigte Gemeinden mit positivem Gap und festgelegter Sortierung |
| `GET /api/cafes?bbox=w,s,e,n` | Café-Punkte im Kartenausschnitt mit `$geoWithin` |
| `GET /api/meta` | Datenstände, Definitionen, Gewicht, Mindestnachfrage, Schweizer Median, Ausschlüsse und Sensitivität |
| `GET /api/cafes/heat?kanton=ZH` | Optional: Punkte für leaflet.heat |
| `GET /api/nearby?lat=&lon=&radius=` | Stretch: Umkreissuche mit `$geoNear` |
| `GET /api/amenity-types` | Stretch: weitere Amenity-Typen und Anzahlen |

Kantonsfilter, Koordinaten, Bounding Box und Limit validieren. Ungültige Eingaben mit HTTP 400 und verständlichem JSON-Fehler beantworten. Fehlende Analyse klar melden; leere Trefferlisten sind gültige Ergebnisse. GeoJSON-Grösse und Antwortzeit messen; gzip und begrenzte Punktabfragen vorsehen.

## 8. Rollen und Arbeitspakete

Vorgeschlagene Zuordnung aus dem Teamplan:

| Person | Verantwortung |
|---|---|
| Aisosa Omokaro (Aiso) | Projektmanagement, Frontend, Karte/Charts, Dokumentation und Präsentation |
| Nico Verano | Datenimport, Statistikdaten, Gemeindezuordnung, Kennzahl und Sensitivität |
| John Wiese | Flask-API, MongoDB-Abfragen, Qualitätssicherung und Setup-Anleitung |

| Paket | Aufgaben und Abhängigkeiten | Zuständig |
|---|---|---|
| WP0 – Basis | Bestehendes Repository lokal starten; Branch-/Review-Regel, Board und Jour Fix vereinbaren | alle, Koordination Aiso |
| WP1 – Daten | Import prüfen, STATPOP/STATENT ergänzen, Jahre/BFS-IDs und Zuordnungen validieren | Nico; Review John |
| WP2 – Pflichtsystem | Flask mit bestehenden MongoDB-Daten verbinden; Browser mit jQuery, Leaflet und ChartJS-Kantonschart | John und Aiso |
| WP3 – Analyse | Nach WP1 Formeln, Schwelle, Sonderfälle, Sensitivität und Metadaten implementieren | Nico |
| WP4 – Interaktion | Nach WP2/3 drei Kartenmodi, Details, Filter, Top 10, diagonale Scatterplot-Referenz und Methodik | Aiso und John |
| WP5 – Abschluss | Dokumentiertes Setup auf frischem Rechner, Abnahme, Präsentation, Demo-Backup und Abgabe | alle |

## 9. Meilensteine und Abnahme

Relative Planung ab abgestimmtem Projektstart; konkrete Termine und Kursdeadline im Team eintragen.

| Meilenstein | Ziel | Vorgesehener Zeitpunkt |
|---|---|---|
| M1 | MongoDB → Flask → Leaflet-Karte und ChartJS-Kantonschart laufen | Ende Woche 3 |
| M2 | Validierte Gemeindedaten, Café-Lücke und Choropleth | Ende Woche 5 |
| M3 | Details, Kantonfilter, Top 10, Scatterplot und Methodik fertig | Ende Woche 6 |
| M4 | Feature-Freeze und Test auf frischem Rechner | Ende Woche 7 |
| M5 | Generalprobe und Abgabe | Woche 8, mindestens drei Tage vor bestätigter Deadline |

Falls diese Planung nicht vor die Kursdeadline passt, Zeitplan verkürzen und Extras streichen. Wenn M1 gefährdet ist, hat das Pflichtsystem Vorrang.

- [ ] MongoDB, Flask, Browser/jQuery, LeafletJS und ChartJS sind verbunden.
- [ ] Formeln stimmen bei einem Handrechenbeispiel und bei Grenzfällen (D = 5000, fehlende Werte, Median = 0, leere Referenzmenge).
- [ ] Kantonfilter verändert den nationalen Median nicht.
- [ ] Karte, Ranking, Details und Scatterplot verwenden dieselben Werte und Datenstände.
- [ ] Top 10 enthält nur berechtigte Gemeinden mit positivem Gap; Gleichstände sind deterministisch.
- [ ] Datenquellen, Lizenzhinweise, Datenjahre und Sensitivität sind dokumentiert.
- [ ] Setup-Anleitung wurde auf frischem Rechner geprüft; Präsentation und Demo-Backup sind vorbereitet.

## 10. Jour Fix

Wöchentlich 30 Minuten; Protokoll in `docs/jourfix/YYYY-MM-DD.md`:

```text
Datum:
Anwesend:
Review: Erreichtes, Probleme und Ursachen
Status: Meilensteine, Risiken, offene Aufgaben
Ausblick: Wer erledigt was bis wann?
Entscheidungen: Änderungen an Umfang, Parametern oder Zeitplan
```

## 11. Limitationen und Risiken

- OSM-Abdeckung ist regional unterschiedlich; fehlende Einträge sind nicht automatisch fehlende Betriebe. Mehrfacherfassung eines Betriebs als Node und Fläche prüfen.
- Repräsentative Punkte und Grenzfälle können räumliche Zuordnungen beeinflussen. Der aktuelle innere Spatial Join lässt nicht zugeordnete Punkte weg; ihren Anteil prüfen.
- Fehlende oder zeitlich unpassende Statistikdaten sowie Gemeindefusionen können Vergleiche verzerren. Datenstände und Verknüpfungsquote dokumentieren.
- Nachfragegewicht und Schwelle sind Modellannahmen. Tourismus, Pendlerströme, Kaufkraft, Öffnungszeiten und Café-Kapazität werden nicht vollständig abgebildet.
- Gap ist ein relativer Vergleich, keine kausale Erklärung, Rentabilitätsprognose oder Anzahl zusätzlich tragfähiger Cafés.
- Die Grenze im Browser ist vereinfacht; die räumliche Zuordnung erfolgt derzeit vor der Vereinfachung.
- Grosse GeoJSON-Antworten und schweizweite Overpass-Abfragen können langsam sein. Cache, Antwortgrössen und Filter früh prüfen.
- Kleine Pull Requests, gegenseitige Reviews und aktuelle Dokumentation begrenzen Merge-Konflikte und Ausfallrisiken.

## 12. Stretch Goals

Erst nach stabiler Kernanwendung: optionale Heatmap/Marker, K-Means als explorative Ergänzung, Regression zur zusätzlichen Validierung, Amenity-Dropdown und Radiussuche. Dafür sind noch keine fertigen Bonus-Skripte oder Endpoints vorhanden. Weitere Amenity-Typen benötigen eine eigene methodische Begründung. Die Hauptkennzahl bleibt unverändert.

## 13. Präsentation

Forschungsfrage → Daten und Architektur → absolute Café-Anzahl → Rate pro Demand Units → Café-Lücke zum Schweizer Median → Gemeindeklick, Kantonfilter, Top 10 und Scatterplot → Erkenntnisse, Sensitivität und Grenzen. Präsentationsdauer an die bestätigte Kursvorgabe anpassen und eine aufgezeichnete Demo bereithalten.
