# Repo für PM3 Projekt von Gruppe 3

# CaféGap Schweiz (DS.PM3)

**Forschungsfrage:** In welchen Schweizer Gemeinden gibt es im Verhältnis zur potenziellen Nachfrage eher viele oder wenige Cafés?

Webbasierte Client-Server-Lösung: OSM-Cafés in MongoDB, Flask-Server, Gemeindekarte (LeafletJS) und Charts (ChartJS) im Browser.

## Kennzahl "Café-Lücke"

```
D        = Einwohner + 0.5 × Beschäftigte        Potential Demand (Nachfrage-Proxy)
CafeRate = Cafés / D × 10'000                     Cafés pro 10'000 Nachfrage-Einheiten
Median   = Median(CafeRate)                       nur über Gemeinden mit D ≥ 5'000
Gap      = Median − CafeRate                      > 0: weniger Cafés als die typische Gemeinde
```

- Das Gewicht 0.5 ist eine **Modellannahme**, keine gemessene Grösse. Eine Sensitivitätsanalyse (0.25 / 0.5 / 0.75) prüft, ob das Ranking stabil bleibt (steht in `/api/meta` und in der Methodik-Box).
- Gemeinden mit D < 5'000 werden angezeigt, aber auf der Lücken-Karte grau markiert und nicht gerankt. Den Grenzwert (`MIN_DEMAND` in `config.py`) mit den echten Daten prüfen und dokumentieren.
- Der Median wird nur über die ausreichend grossen Gemeinden gebildet, sonst zieht die Masse kleiner Dörfer ohne OSM-Café ihn gegen 0.

## Stack

| Schicht | Technologie |
|---|---|
| Datenbank | MongoDB |
| Webserver | Flask |
| Client | Web-Browser, jQuery |
| Karte | LeafletJS (+ leaflet.heat für die Heatmap) |
| Chart | ChartJS |

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
docker compose up -d               # startet MongoDB auf localhost:27017
```

Ohne Docker: lokales MongoDB installieren oder `MONGO_URI` (z.B. Atlas) als Umgebungsvariable setzen.

## Daten-Pipeline (einmalig, in dieser Reihenfolge)

Dateien nach `data/` legen (siehe `data/README.md`), dann:

```bash
python -m scripts.import_amenities --file data/osm-output.json
python -m scripts.import_boundaries --file data/gemeinden.geojson \
    --where ICC=CH --where OBJEKTART=Gemeindegebiet
python -m scripts.assign_regions
python -m scripts.import_jobs --file data/statent.csv
python -m scripts.compute_analysis
```

Gemeindegrenzen konvertieren (swissBOUNDARIES3D liegt als GDB/Shapefile vor):

```bash
ogr2ogr -f GeoJSON -t_srs EPSG:4326 data/gemeinden.geojson \
    swissBOUNDARIES3D_1_5_LV95_LN02.gdb TLM_HOHEITSGEBIET
```

> Feldnamen (`BFS_NUMMER`, `NAME`, `KANTONSNUM`, `EINWOHNERZAHL`) und Filterwerte bitte mit der echten Datei prüfen. Sie sind per Argument anpassbar (`--help`). Fehlt die Einwohnerzahl, `--pop-csv data/statpop.csv` verwenden.

## Starten

```bash
python app.py        # http://localhost:5000
```

## Funktionen

- Gemeindekarte der ganzen Schweiz, umschaltbar: **Café-Lücke** | Cafés pro 10'000 Nachfrage-Einheiten | Anzahl Cafés
- Klick auf eine Gemeinde: Einwohner, Beschäftigte, Cafés, Rate, Median, Lücke
- Kanton-Filter (Karte, KPIs, Scatterplot und Top-10 aktualisieren sich)
- Top-10-Chart der grössten Café-Lücken
- Scatterplot Nachfrage vs. Angebot mit Median-Linie
- Pflicht-Chart: Cafés pro Kanton
- Optionale Layer: Café-Heatmap, Café-Marker (ab Zoom 13)

## Projektstruktur

```
cafe-demand/
├── app.py                  Flask-Server + API
├── config.py               Konstanten (Gewicht, Mindestnachfrage, Kantone)
├── db.py                   MongoDB-Verbindung
├── scripts/                Daten-Pipeline (Import, Zuordnung, Analyse, optional Bonus)
├── templates/index.html    Seite
├── static/js/main.js       Karte, Charts, Interaktion
├── static/css/style.css
├── data/                   Rohdaten (nicht im Git)
└── docs/PROJEKTPLAN.md     Rollen, Tasks, Meilensteine, Jour-Fix-Vorlage
```

## Datenmodell (MongoDB)

| Collection | Wichtige Felder |
|---|---|
| `kantone` | `_id` (ZH), `name`, `geometrie`, `stats` (Kennzahlen) |
| `gemeinden` | `_id` (BFS-Nr.), `name`, `kanton`, `einwohner`, `beschaeftigte`, `geometrie` |
| `amenities` | `_id` (OSM-ID), `amenity`, `name`, `lat`, `lon`, `location` (2dsphere), `kanton`, `gemeinde`, `tags` |
| `analyse` | `_id`/`gemeinde`, `kanton`, `einwohner`, `beschaeftigte`, `nachfrage_einheiten`, `anzahl_cafes`, `cafes_pro_10k_nachfrage`, `gap`, `gap_rel`, `ranking_eligible` |
| `meta` | Gewicht, Median, Mindestnachfrage, Sensitivitätsanalyse |

## API

| Endpoint | Zweck |
|---|---|
| `GET /api/kantone` | Kantone als GeoJSON inkl. Kennzahlen |
| `GET /api/gemeinden[?kanton=ZH]` | Gemeinden als GeoJSON inkl. Kennzahlen (gzip) |
| `GET /api/top-luecken?kanton=ZH&limit=10` | Gemeinden mit der grössten Café-Lücke (nur bewertete) |
| `GET /api/cafes?bbox=w,s,e,n` | Café-Punkte im Kartenausschnitt (`$geoWithin`) |
| `GET /api/cafes/heat?kanton=ZH` | Punktliste für die Heatmap |
| `GET /api/meta` | Parameter, Median, Sensitivität |
| `GET /api/nearby?lat=&lon=&radius=` | *Stretch:* Umkreissuche (`$geoNear`) |
| `GET /api/amenity-types` | *Stretch:* Amenity-Typen mit Anzahl |

## Bekannte Limitationen

- OSM-Abdeckung ist regional unterschiedlich vollständig.
- Nur Nodes, keine Ways/Relations (Cafés als Gebäudeflächen fehlen evtl.).
- Das Beschäftigten-Gewicht und `MIN_DEMAND` sind Annahmen; die Sensitivitätsanalyse zeigt, wie stabil das Ranking ist.
- Die Lücke ist eine *relative* Grösse zum Schweizer Median, keine Aussage "hier fehlen genau X Cafés". Sie ist auch keine Aussage über Rentabilität.
- Touristische Gemeinden (viele Cafés, wenig Einwohner) und Pendlergemeinden (viele Einwohner, wenig Arbeitsplätze) sind Sonderfälle.
- Gemeindegrenzen sind für die Web-Darstellung vereinfacht (~100 m); Punkte nahe der Grenze können der Nachbargemeinde zugeordnet werden.
- Stretch/Bonus (nicht Teil der Hauptanalyse): `scripts/bonus_kmeans.py`, Regression, Amenity-Dropdown, Radiussuche.


## ORDNERSTRUKTUR

```
├── src/pm3/
│   ├── build_db.py                 # Lädt die Daten herunter und baut die MongoDB auf
│   └── plots_examples_testing.py   # Test-Plots aus der Datenbank
├── data/raw/                       # Heruntergeladene Rohdaten
├── docker-compose.yml              # Lokale MongoDB
├── pyproject.toml                  # Python-Abhängigkeiten
└── README.md
```

## DATENBANK AUFSETZEN

Voraussetzungen: Docker und uv

```bash
uv sync                                     # Python-Umgebung installieren
docker compose up -d                        # MongoDB starten
uv run src/pm3/build_db.py                  # Daten herunterladen und DB aufbauen
uv run src/pm3/plots_examples_testing.py    # Test Plots aus der DB anzeigen
