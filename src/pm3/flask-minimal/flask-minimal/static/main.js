// 1. Karte erstellen, zentriert auf die Schweiz
const karte = L.map("karte").setView([46.8, 8.2], 8);

// 2. Hintergrundkarte von OpenStreetMap laden
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap",
}).addTo(karte);

// 3. Cafés von unserer Flask-API holen
fetch("/api/cafes")
  .then(antwort => antwort.json())
  .then(cafes => {
    // Anzahl anzeigen
    document.getElementById("anzahl").textContent = cafes.length + " Cafés gefunden";

    // Jedes Café als Punkt auf die Karte setzen
    cafes.forEach(cafe => {
      const lon = cafe.location.coordinates[0];
      const lat = cafe.location.coordinates[1];

      L.circleMarker([lat, lon], { radius: 4 })
        .bindPopup(cafe.name || "Café ohne Namen")
        .addTo(karte);
    });
  });
