# CaféGap Web – Karten-Prototyp für GitHub Pages

Statische Gemeindekarte der Schweiz (Astro), portiert von der Swiss-City-Quiz-Seite aus `jsow-site`.
Die Seite wird bei jedem Push auf `main`, der etwas unter `web/` ändert, automatisch auf GitHub Pages veröffentlicht.

Aktuell ist es ein **Prototyp**: Gemeinde- und Kantonsgrenzen, Kantonfilter mit Zoom, Gemeinde-Klick (BFS-Nr.).
Die bestehenden Dateien im Repository werden nicht verändert; es kommen nur `web/` und der Workflow dazu.

## Ordnerstruktur

```
.github/workflows/pages.yml        Build + Deploy auf GitHub Pages (nur bei Änderungen in web/)
web/
├── astro.config.mjs               site/base setzt der Workflow, nichts hartcodiert
├── package.json, package-lock.json
├── tsconfig.json
├── src/pages/index.astro          Seite (Banner, Sidebar, Karte)
└── public/
    ├── favicon.svg
    └── cafegap/
        ├── app.js                 Karte (d3 + svg-pan-zoom), Modi, Filter, Details, Legende
        ├── data-source.js         Datenanbindung: lädt data/gemeinden.json oder meldet "Prototyp"
        ├── styles.css
        ├── geo/ch-2026.topo.json  Gemeinden, Kantone, Seen (Stand 2026)
        └── data/                  leer; später gemeinden.json
```

## Lokal starten

```bash
cd web
npm install
npm run dev        # http://localhost:4321
```

## GitHub Pages einrichten (einmalig)

1. Repository -> **Settings -> Pages -> Build and deployment -> Source: GitHub Actions**.
2. Auf `main` pushen (oder den Workflow unter *Actions* manuell starten).
3. Die Seite liegt danach unter `https://<owner>.github.io/<repo>/`.

Hinweis: Für private Repositories ist GitHub Pages nur mit einem kostenpflichtigen GitHub-Plan verfügbar.

## Daten anbinden (später)

GitHub Pages liefert nur statische Dateien aus und kann die MongoDB nicht abfragen. Die Seite ist deshalb
darauf vorbereitet, einen Export aus der MongoDB als Datei `public/cafegap/data/gemeinden.json` zu lesen.
Sobald die Datei existiert, schaltet die Seite automatisch von "Prototyp" auf "Daten verbunden" und aktiviert
die Kartenmodi Café-Lücke / Cafés pro 10'000 Nachfrage / Anzahl Cafés.

Erwartetes Format (eine Zeile pro Gemeinde, Verknüpfung mit der Karte über die BFS-Nummer):

```json
{
  "meta": {
    "imported_at": "2026-10-28T09:30:00+00:00",
    "exported_at": "2026-10-29T12:00:00+00:00",
    "boundaries_version": "...",
    "employee_weight": 0.5,
    "min_demand": 5000,
    "median_rate": 4.56,
    "n_municipalities": 2113,
    "n_eligible": 600,
    "n_cafes": 3400
  },
  "gemeinden": [
    {
      "bfs": 261, "name": "Zürich", "canton": 1,
      "population": 0, "employees": 0, "cafes": 0,
      "demand": 0, "rate": 0, "gap": 0, "gap_rel": 0,
      "eligible": true, "reason": null
    }
  ]
}
```

Kennzahlen nach `docs/PROJEKTPLAN.md` (Abschnitt 3): `demand` = Einwohner + 0.5 × Beschäftigte,
`rate` = Cafés / demand × 10'000, `gap` = Median − rate (nur für `eligible`, sonst `null`).
`reason` ist einer von `population_missing`, `employees_missing`, `cafes_missing`, `below_min_demand`.
Pflichtfelder prüft `data-source.js`; fehlt eines, zeigt die Seite einen Datenfehler statt falscher Werte.

## Kartengrundlage

`geo/ch-2026.topo.json` stammt aus [swiss-maps](https://github.com/interactivethings/swiss-maps) 4.7.0
(Interactive Things, BSD-3-Clause, siehe `geo/LICENSE-swiss-maps.txt`), Ebene 2026, generalisierte BFS-Grenzen.
Ergänzt wurde pro Gemeinde der Kanton (`properties.kt`, räumlich zugeordnet); die Bezirke wurden entfernt.
Gemeindenamen kommen erst mit den Daten dazu.

## Hinweise

- Die Karte nutzt wie das Quiz d3 und svg-pan-zoom. Der Projektplan nennt LeafletJS für die Flask-Version;
  `data-source.js` ist von der Darstellung unabhängig und kann dort wiederverwendet werden.
- Die Flask-App bleibt die Kursabgabe (MongoDB -> Flask -> Browser); diese Seite ist die öffentliche, statische Ansicht.
