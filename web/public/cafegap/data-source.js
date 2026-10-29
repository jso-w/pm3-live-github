// Data connection for the CaféGap map.
//
// GitHub Pages only serves static files, so the page cannot query MongoDB directly.
// Later, a snapshot exported from MongoDB can be placed at
// web/public/cafegap/data/gemeinden.json (format: see web/README.md) and is deployed with the site.
// As long as that file does not exist, the map runs in prototype mode (boundaries only).
//
// Result of CafeGapData.load():
//   { status: "snapshot", url, meta, rows, byBfs }   snapshot found and valid
//   { status: "none", url }                          no snapshot yet -> prototype
//   { status: "error", url, error }                  file exists but could not be used

(function () {
  const REQUIRED_FIELDS = ["bfs", "name", "canton", "cafes", "demand", "rate", "gap", "eligible"];

  async function load(assetBase) {
    const url = `${assetBase}/data/gemeinden.json`;
    let response;
    try {
      response = await fetch(url, { cache: "no-cache" });
    } catch (err) {
      return { status: "error", url, error: `Netzwerkfehler: ${err.message}` };
    }
    if (response.status === 404) return { status: "none", url };
    if (!response.ok) return { status: "error", url, error: `HTTP ${response.status}` };

    try {
      const json = await response.json();
      validate(json);
      const byBfs = new Map(json.gemeinden.map(row => [Number(row.bfs), row]));
      return { status: "snapshot", url, meta: json.meta, rows: json.gemeinden, byBfs };
    } catch (err) {
      return { status: "error", url, error: err.message };
    }
  }

  function validate(json) {
    if (!json || typeof json.meta !== "object" || !Array.isArray(json.gemeinden)) {
      throw new Error("Unerwartetes Format: 'meta' oder 'gemeinden' fehlt.");
    }
    if (json.gemeinden.length === 0) throw new Error("Der Snapshot enthält keine Gemeinden.");
    const missing = REQUIRED_FIELDS.filter(key => !(key in json.gemeinden[0]));
    if (missing.length) throw new Error(`Felder fehlen im Snapshot: ${missing.join(", ")}`);
  }

  window.CafeGapData = { load };
})();
