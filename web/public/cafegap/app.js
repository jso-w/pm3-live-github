// CaféGap Schweiz – map prototype, ported from the Swiss City Quiz (jsow-site).
// Draws the Swiss municipalities with d3 + svg-pan-zoom. If data-source.js finds the
// snapshot exported from MongoDB, the municipalities are coloured by the selected
// metric; otherwise only the base map is shown (prototype mode).

const W = 800, H = 500;
const BASE = (window.__CAFEGAP_BASE__ || "").replace(/\/$/, "");
const ASSETS = `${BASE}/cafegap`;

const KANTONE = {
  1: ["ZH", "Zürich"], 2: ["BE", "Bern"], 3: ["LU", "Luzern"], 4: ["UR", "Uri"],
  5: ["SZ", "Schwyz"], 6: ["OW", "Obwalden"], 7: ["NW", "Nidwalden"], 8: ["GL", "Glarus"],
  9: ["ZG", "Zug"], 10: ["FR", "Freiburg"], 11: ["SO", "Solothurn"], 12: ["BS", "Basel-Stadt"],
  13: ["BL", "Basel-Landschaft"], 14: ["SH", "Schaffhausen"], 15: ["AR", "Appenzell Ausserrhoden"],
  16: ["AI", "Appenzell Innerrhoden"], 17: ["SG", "St. Gallen"], 18: ["GR", "Graubünden"],
  19: ["AG", "Aargau"], 20: ["TG", "Thurgau"], 21: ["TI", "Tessin"], 22: ["VD", "Waadt"],
  23: ["VS", "Wallis"], 24: ["NE", "Neuenburg"], 25: ["GE", "Genf"], 26: ["JU", "Jura"],
};

const REASONS = {
  population_missing: "Einwohnerzahl fehlt",
  employees_missing: "Beschäftigte fehlen",
  cafes_missing: "Café-Anzahl fehlt",
  below_min_demand: "Nachfrage unter Mindestwert",
};

// Colours. Sequential = one hue (cream -> espresso); diverging = brown / teal around a grey midpoint.
const COLORS = {
  land: "#e9e9e9",
  water: "#a4c8e1",
  noData: "#f7f6f4",
  muniStroke: "#ffffff",
  cantonStroke: "#8a7b6e",
  countryStroke: "#888888",
};
const SEQUENTIAL = d3.interpolateLab("#f3ebe2", "#4a2a17");
const DIVERGING = d3.piecewise(d3.interpolateLab, ["#6b3f1f", "#c39a74", "#e4e1dd", "#7fb3b4", "#1d6a6e"]);

const MODES = {
  base: { label: "Grundkarte" },
  gap: {
    label: "Café-Lücke",
    value: r => (r.eligible ? r.gap : null),
    format: v => signed(v),
  },
  rate: {
    label: "Cafés pro 10'000 Nachfrage",
    value: r => r.rate,
    format: v => num(v, 2),
  },
  count: {
    label: "Anzahl Cafés",
    value: r => r.cafes,
    format: v => num(v, 0),
  },
};

const state = {
  data: { status: "none" },
  mode: "base",
  canton: null,
  selected: null,
  scales: {},
};

let projection, path, panZoom, muniPaths, overlay;

const numberFormats = {};
function num(v, digits = 0) {
  if (v == null) return "–";
  numberFormats[digits] ??= new Intl.NumberFormat("de-CH", { maximumFractionDigits: digits, minimumFractionDigits: digits });
  return numberFormats[digits].format(v);
}
function signed(v) {
  if (v == null) return "–";
  return (v > 0 ? "+" : "") + num(v, 2);
}
function pct(v) {
  return v == null ? "–" : (v > 0 ? "+" : "") + num(v * 100, 0) + " %";
}
function date(iso) {
  return iso ? new Date(iso).toLocaleDateString("de-CH", { day: "2-digit", month: "2-digit", year: "numeric" }) : "–";
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

// d3 expects clockwise exterior rings; reverse any ring set that would cover the whole globe instead.
function fixWinding(feature) {
  if (d3.geoArea(feature) <= 2 * Math.PI) return feature;
  const g = feature.geometry;
  if (g.type === "Polygon") g.coordinates.forEach(ring => ring.reverse());
  if (g.type === "MultiPolygon") g.coordinates.forEach(poly => poly.forEach(ring => ring.reverse()));
  return feature;
}

function cantonOf(f) {
  const row = f.properties.row;
  return (row && row.canton) || f.properties.kt;
}

async function init() {
  const [topo, data] = await Promise.all([
    fetchJSON(`${ASSETS}/geo/ch-2026.topo.json`),
    window.CafeGapData.load(ASSETS),
  ]);
  state.data = data;

  const feature = name => topojson.feature(topo, topo.objects[name]).features.map(fixWinding);
  const municipalities = feature("municipalities");
  const cantons = feature("cantons");
  const lakes = feature("lakes");
  const country = feature("country");
  const cantonBorders = topojson.mesh(topo, topo.objects.cantons, (a, b) => a !== b);

  // Join the snapshot rows to the map by BFS number
  let matched = 0;
  for (const f of municipalities) {
    const row = data.status === "snapshot" ? data.byBfs.get(Number(f.id)) : undefined;
    f.properties.row = row;
    if (row) matched++;
  }
  state.matched = matched;
  state.unmatchedRows = data.status === "snapshot" ? data.rows.length - matched : 0;
  state.cantons = new Map(cantons.map(c => [Number(c.id), c]));

  projection = d3.geoMercator().fitSize([W, H], { type: "FeatureCollection", features: country });
  path = d3.geoPath(projection);

  const svg = d3.select("#map").attr("viewBox", `0 0 ${W} ${H}`);
  const mapGroup = svg.append("g");

  muniPaths = mapGroup.append("g").attr("class", "municipalities")
    .selectAll("path")
    .data(municipalities)
    .enter()
    .append("path")
    .attr("d", path)
    .attr("stroke", COLORS.muniStroke)
    .attr("stroke-width", 0.3)
    .attr("vector-effect", "non-scaling-stroke");

  // Canton borders below the lakes, so they don't cross the water
  mapGroup.append("path")
    .attr("class", "canton-borders")
    .attr("d", path(cantonBorders))
    .attr("fill", "none")
    .attr("stroke", COLORS.cantonStroke)
    .attr("stroke-width", 0.9)
    .attr("vector-effect", "non-scaling-stroke");

  mapGroup.append("g").attr("class", "lakes")
    .selectAll("path")
    .data(lakes)
    .enter()
    .append("path")
    .attr("d", path)
    .attr("fill", COLORS.water)
    .attr("stroke", COLORS.water)
    .attr("vector-effect", "non-scaling-stroke");

  mapGroup.append("g").attr("class", "country")
    .selectAll("path")
    .data(country)
    .enter()
    .append("path")
    .attr("d", path)
    .attr("fill", "none")
    .attr("stroke", COLORS.countryStroke)
    .attr("stroke-width", 1)
    .attr("vector-effect", "non-scaling-stroke");

  // Hover / selection / canton outlines live on top and never catch the mouse
  overlay = {
    canton: mapGroup.append("path").attr("class", "outline outline--canton"),
    selected: mapGroup.append("path").attr("class", "outline outline--selected"),
    hover: mapGroup.append("path").attr("class", "outline outline--hover"),
  };
  mapGroup.selectAll(".outline, .lakes path, .canton-borders, .country path")
    .attr("pointer-events", "none")
    .attr("vector-effect", "non-scaling-stroke");

  panZoom = svgPanZoom("#map", {
    controlIconsEnabled: true,
    fit: true,
    center: true,
    minZoom: 0.5,
    maxZoom: 40,
  });
  window.addEventListener("resize", () => {
    panZoom.resize();
    panZoom.fit();
    panZoom.center();
  });

  bindMapEvents();
  setupSidebar(municipalities);
  if (data.status === "snapshot") {
    for (const mode of ["gap", "rate", "count"]) state.scales[mode] = buildScale(mode, data.rows);
    setMode("gap");
  } else {
    setMode("base");
  }
}

// ---------- colouring ----------

function buildScale(mode, rows) {
  const values = rows.map(MODES[mode].value).filter(v => v != null).sort(d3.ascending);
  if (mode === "gap") {
    const m = d3.quantile(values.map(Math.abs).sort(d3.ascending), 0.95) || 1;
    return { color: d3.scaleDiverging([-m, 0, m], DIVERGING).clamp(true), min: -m, max: m };
  }
  if (mode === "rate") {
    const hi = d3.quantile(values, 0.95) || 1;
    return { color: d3.scaleSequential([0, hi], SEQUENTIAL).clamp(true), min: 0, max: hi };
  }
  const hi = d3.max(values) || 1; // count: symlog, because most municipalities have 0–3 cafés
  return { color: d3.scaleSequentialSymlog([0, hi], SEQUENTIAL), min: 0, max: hi };
}

function fillFor(f) {
  if (state.mode === "base") return COLORS.land;
  const row = f.properties.row;
  if (!row) return COLORS.noData;
  if (state.mode === "gap" && !row.eligible) return "url(#not-rated)";
  const v = MODES[state.mode].value(row);
  return v == null ? COLORS.noData : state.scales[state.mode].color(v);
}

function setMode(mode) {
  state.mode = mode;
  document.querySelector(`#modes input[value="${mode}"]`).checked = true;
  muniPaths.attr("fill", fillFor);
  renderLegend();
  updateFeedback();
}

function applyCantonFilter() {
  const kt = state.canton;
  muniPaths.attr("fill-opacity", f => (kt && cantonOf(f) !== kt ? 0.25 : 1));
  overlay.canton.attr("d", kt ? path(state.cantons.get(kt)) : null);
  if (kt) zoomToFeature(state.cantons.get(kt));
  else panZoom.reset();
  updateFeedback();
}

// Fits a feature into the visible map area (coordinates of svg-pan-zoom: screen = map * zoom + pan)
function zoomToFeature(feature) {
  const [[x0, y0], [x1, y1]] = path.bounds(feature);
  panZoom.reset();
  const sizes = panZoom.getSizes();
  const target = Math.min(sizes.width / (x1 - x0), sizes.height / (y1 - y0)) * 0.85;
  panZoom.zoom(target / sizes.realZoom);
  const zoom = panZoom.getSizes().realZoom;
  panZoom.pan({
    x: sizes.width / 2 - ((x0 + x1) / 2) * zoom,
    y: sizes.height / 2 - ((y0 + y1) / 2) * zoom,
  });
}

// ---------- interaction ----------

function bindMapEvents() {
  const tooltip = d3.select("#tooltip");
  let downAt = null;

  muniPaths
    .on("mouseover", function (event, f) {
      overlay.hover.attr("d", path(f));
      tooltip.style("opacity", 1).html(tooltipHtml(f));
    })
    .on("mousemove", function (event) {
      tooltip.style("left", (event.pageX + 15) + "px").style("top", (event.pageY - 25) + "px");
    })
    .on("mouseout", function () {
      overlay.hover.attr("d", null);
      tooltip.style("opacity", 0);
    })
    .on("pointerdown", event => { downAt = [event.clientX, event.clientY]; })
    .on("click", function (event, f) {
      // svg-pan-zoom also fires a click after dragging the map; only treat a still click as a selection
      if (downAt && Math.hypot(event.clientX - downAt[0], event.clientY - downAt[1]) > 4) return;
      select(f);
    });
}

function tooltipHtml(f) {
  const row = f.properties.row;
  const [abbr] = KANTONE[cantonOf(f)] || ["?"];
  const name = row && row.name ? escapeHtml(row.name) : `Gemeinde ${f.id}`;
  let html = `<strong>${name}</strong> · ${abbr}`;
  if (state.mode !== "base") {
    const mode = MODES[state.mode];
    let value = "keine Daten";
    if (row && state.mode === "gap" && !row.eligible) value = "nicht bewertet";
    else if (row) value = mode.format(mode.value(row));
    html += `<br>${mode.label}: ${value}`;
  }
  return html;
}

function select(f) {
  state.selected = f;
  overlay.selected.attr("d", path(f));
  renderDetails(f);
}

function setupSidebar(municipalities) {
  const cantonSelect = document.getElementById("canton");
  Object.entries(KANTONE)
    .sort((a, b) => a[1][1].localeCompare(b[1][1], "de"))
    .forEach(([nr, [abbr, name]]) => cantonSelect.add(new Option(`${name} (${abbr})`, nr)));
  cantonSelect.addEventListener("change", () => {
    state.canton = cantonSelect.value ? Number(cantonSelect.value) : null;
    applyCantonFilter();
  });

  const hasData = state.data.status === "snapshot";
  document.querySelectorAll("#modes input").forEach(input => {
    if (input.value !== "base") input.disabled = !hasData;
    input.addEventListener("change", () => setMode(input.value));
  });
  document.getElementById("mode-hint").textContent = hasData
    ? ""
    : "Die Datenmodi werden aktiv, sobald ein Daten-Snapshot vorhanden ist.";

  renderSource(municipalities.length);
}

// ---------- sidebar rendering ----------

function renderSource(nMap) {
  const data = state.data;
  const pill = document.getElementById("status-pill");
  const el = document.getElementById("source");
  pill.dataset.status = data.status;

  if (data.status === "snapshot") {
    const m = data.meta;
    pill.textContent = "Daten verbunden";
    el.innerHTML = `
      <p class="status"><span class="dot dot--ok"></span>Verbunden · MongoDB-Snapshot</p>
      <dl>
        <dt>Import</dt><dd>${date(m.imported_at)}</dd>
        <dt>Export</dt><dd>${date(m.exported_at)}</dd>
        <dt>Grenzen</dt><dd>${escapeHtml(m.boundaries_version || "–")}</dd>
        <dt>Gemeinden</dt><dd>${num(m.n_municipalities)}</dd>
        <dt>Cafés (OSM)</dt><dd>${num(m.n_cafes)}</dd>
        <dt>Bewertet</dt><dd>${num(m.n_eligible)} <span class="muted">(D ≥ ${num(m.min_demand)})</span></dd>
        <dt>Median</dt><dd>${num(m.median_rate, 2)} <span class="muted">pro 10'000 D</span></dd>
      </dl>
      ${state.unmatchedRows ? `<p class="hint">Ohne Fläche auf der Karte: ${num(state.unmatchedRows)} (Kartenstand 2026, z. B. wegen Gemeindefusionen).</p>` : ""}`;
  } else if (data.status === "error") {
    pill.textContent = "Datenfehler";
    el.innerHTML = `
      <p class="status"><span class="dot dot--error"></span>Snapshot nicht lesbar</p>
      <p class="hint">${escapeHtml(data.error)}</p>
      <p class="hint">Datei: <code>${escapeHtml(data.url)}</code></p>`;
  } else {
    pill.textContent = "Prototyp";
    el.innerHTML = `
      <p class="status"><span class="dot"></span>Nicht verbunden</p>
      <p class="hint">Noch keine Café-Daten angebunden. Die Karte zeigt nur die ${num(nMap)} Gemeindegrenzen.</p>`;
  }
}

function renderDetails(f) {
  const row = f.properties.row;
  const kt = cantonOf(f);
  const [abbr, cantonName] = KANTONE[kt] || ["?", "unbekannt"];
  const title = row && row.name ? escapeHtml(row.name) : `Gemeinde ${f.id}`;
  let html = `<h3>${title}</h3><p class="sub">BFS-Nr. ${f.id} · ${cantonName} (${abbr})</p>`;

  if (!row) {
    html += `<p class="hint">${state.data.status === "snapshot"
      ? "Für diese Gemeinde enthält der Snapshot keine Daten."
      : "Noch keine Daten verbunden."}</p>`;
  } else {
    const m = state.data.meta;
    const rating = row.eligible
      ? `<span class="badge badge--ok">bewertet</span>`
      : `<span class="badge">nicht bewertet</span> <span class="muted">${escapeHtml(REASONS[row.reason] || row.reason || "")}</span>`;
    html += `
      <dl>
        <dt>Einwohner</dt><dd>${num(row.population)}</dd>
        <dt>Beschäftigte</dt><dd>${num(row.employees)}</dd>
        <dt>Nachfrage D</dt><dd>${num(row.demand)}</dd>
        <dt>Cafés</dt><dd>${num(row.cafes)}</dd>
        <dt>pro 10'000 D</dt><dd>${num(row.rate, 2)}</dd>
        <dt>CH-Median</dt><dd>${num(m.median_rate, 2)}</dd>
        <dt>Café-Lücke</dt><dd>${row.gap == null ? "–" : `${signed(row.gap)} <span class="muted">(${pct(row.gap_rel)})</span>`}</dd>
      </dl>
      <p>${rating}</p>`;
  }
  document.getElementById("details").innerHTML = html;
}

function renderLegend() {
  const el = document.getElementById("legend");
  if (state.mode === "base") {
    el.hidden = true;
    return;
  }
  const { color, min, max } = state.scales[state.mode];
  // All scales map their domain onto the interpolator's 0..1, so the bar samples it evenly
  const stops = d3.range(0, 1.0001, 0.1).map(t => `${color.interpolator()(t)} ${Math.round(t * 100)}%`);
  const countMid = d3.scaleSymlog().domain([0, max]).range([0, 1]).invert(0.5);
  const labels = {
    gap: [`≤ ${signed(min)}`, "0", `≥ ${signed(max)}`],
    rate: ["0", num(max / 2, 1), `≥ ${num(max, 1)}`],
    count: ["0", num(countMid), num(max)],
  }[state.mode];
  const subtitle = {
    gap: "Cafés pro 10'000 Nachfrage-Einheiten, relativ zum Schweizer Median",
    rate: "Cafés / (Einwohner + 0.5 × Beschäftigte) × 10'000",
    count: "OSM-Cafés pro Gemeinde (logarithmische Skala)",
  }[state.mode];

  el.innerHTML = `
    <div class="legend-title">${MODES[state.mode].label}</div>
    <div class="legend-sub">${subtitle}</div>
    <div class="legend-bar" style="background: linear-gradient(to right, ${stops.join(", ")})"></div>
    <div class="legend-labels"><span>${labels[0]}</span><span>${labels[1]}</span><span>${labels[2]}</span></div>
    ${state.mode === "gap" ? `<div class="legend-labels legend-labels--words"><span>mehr Cafés</span><span>Median</span><span>weniger Cafés</span></div>` : ""}
    <div class="legend-keys">
      ${state.mode === "gap" ? `<span><i class="swatch swatch--not-rated"></i>nicht bewertet</span>` : ""}
      <span><i class="swatch" style="background:${COLORS.noData}"></i>keine Daten</span>
    </div>`;
  el.hidden = false;
}

function updateFeedback() {
  const fb = document.getElementById("feedback");
  const kt = state.canton ? KANTONE[state.canton][1] : null;
  const where = kt ? `im Kanton ${kt}` : "in der Schweiz";
  const visible = muniPaths.data().filter(f => !state.canton || cantonOf(f) === state.canton);
  if (state.data.status !== "snapshot") {
    fb.innerHTML = `Grundkarte mit <span class="highlight-stat">${num(visible.length)}</span> Gemeinden ${where}. Café-Daten sind noch nicht verbunden.`;
    return;
  }
  const rows = visible.map(f => f.properties.row).filter(Boolean);
  const cafes = d3.sum(rows, r => r.cafes || 0);
  const withGap = rows.filter(r => r.eligible && r.gap > 0).length;
  fb.innerHTML = `<span class="highlight-stat">${num(cafes)}</span> Cafés in <span class="highlight-stat">${num(rows.length)}</span> Gemeinden ${where}. `
    + `<span class="highlight-stat">${num(withGap)}</span> bewertete Gemeinden liegen unter dem Schweizer Median von ${num(state.data.meta.median_rate, 2)} Cafés pro 10'000 Nachfrage-Einheiten.`;
}

// ---------- start ----------

function addPatterns() {
  const defs = d3.select("#map").append("defs");
  const p = defs.append("pattern")
    .attr("id", "not-rated")
    .attr("patternUnits", "userSpaceOnUse")
    .attr("width", 3)
    .attr("height", 3)
    .attr("patternTransform", "rotate(45)");
  p.append("rect").attr("width", 3).attr("height", 3).attr("fill", "#e4e1dd");
  p.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 3).attr("stroke", "#c9c3bc").attr("stroke-width", 1.2);
}

addPatterns();
init().catch(err => {
  console.error(err);
  document.getElementById("feedback").textContent = `Karte konnte nicht geladen werden: ${err.message}`;
  const pill = document.getElementById("status-pill");
  pill.dataset.status = "error";
  pill.textContent = "Fehler";
});
