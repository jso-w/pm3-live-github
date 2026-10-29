
# This script downloads the swissBOUNDARIES3D shapefile and OSM amenities data from their respective APIs 
# and loads them into a MongoDB database. It uses geopandas for spatial data handling, osmnx for OSM data retrieval, and pymongo for database operations.
# This script requires Docker Desktop running, and a MongoDB container started with `docker compose up -d` in the project root.

# Authors: PM3 Gruppe 3
# TO-DOs: 

# All Imports 
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd
import requests
from osmnx._errors import ResponseStatusCodeError
from pymongo import GEOSPHERE, IndexModel, MongoClient
from pymongo.database import Database
from pymongo.errors import ServerSelectionTimeoutError
from shapely.geometry import mapping

# Local configuration and setup of paths, database connection and amenity categories
ROOT = Path(__file__).resolve().parents[2]
BOUNDARIES_DIR = ROOT / "data" / "raw" / "swissboundaries3d"
OSM_CACHE_DIR = ROOT / "data" / "raw" / "osm"

#For connecting to database
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "pm3")

# Dict for amenity categories to import; category name : OSM tag filter.
# This way the code can be upgraded with more amenities without changes to the database schema.
AMENITIES = {
    "cafe": {"amenity": "cafe"},                 ##cafe is the name for our category an the other thing is the query
    # "restaurant": {"amenity": "restaurant"},
    # "supermarket": {"shop": "supermarket"},
}

# URL to STAC API for swissBOUNDARIES3D
STAC_ITEMS_URL = "https://data.geo.admin.ch/api/stac/v1/collections/ch.swisstopo.swissboundaries3d/items"
SHAPEFILE_MEDIA_TYPE = "application/x.shapefile+zip"  # art of data
MUNICIPALITY_LAYER = "TLM_HOHEITSGEBIET"   #gemindelayer

# Shapefile attribute names.
MUNICIPALITY_COLUMNS = {
    "BFS_NUMMER": "bfs_nr",
    "NAME": "name",
    "KANTONSNUM": "canton_nr",
    "EINWOHNERZ": "population",
}

# Tried in order if a server fails
OVERPASS_URLS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
]

EMPLOYEES_URL = "https://www.pxweb.bfs.admin.ch/sq/a782d51e-41fc-41e7-9635-1907f6ea7c0f"

OVERNIGHT_STAYS_URL = "https://www.pxweb.bfs.admin.ch/api/v1/de/px-x-1003020000_101/px-x-1003020000_101.px"
OVERNIGHT_STAYS_QUERY = {
    "query": [
        {"code": "Jahr",          "selection": {"filter": "item", "values": ["2025"]}},
        {"code": "Monat",         "selection": {"filter": "item", "values": ["YYYY"]}},   # Jahrestotal
        {"code": "Herkunftsland", "selection": {"filter": "item", "values": ["0"]}},      # Total
        {"code": "Indikator",     "selection": {"filter": "item", "values": ["2"]}},      # Logiernächte
    ],
    "response": {"format": "json-stat"},
}

STATIONS_URL = "https://data.sbb.ch/api/explore/v2.1/catalog/datasets/passagierfrequenz/exports/json?refine=jahr_annee_anno%3A%222025%22"

LV95 = "EPSG:2056"   # Swiss projected CRS in metres, used for all geometric operations
WGS84 = "EPSG:4326"  # required by MongoDB 2dsphere indexes and web maps

SIMPLIFY_TOLERANCE_M = 20  # applied to municipality geometries stored in MongoDB


# Imports zipped swissBOUNDARIES3D shapefile and return the path to the zip file

def download_boundaries() -> tuple[Path, str]:
    response = requests.get(STAC_ITEMS_URL, params={"limit": 100}, timeout=30)
    response.raise_for_status()
    item = max(response.json()["features"], key=lambda f: f["properties"]["datetime"])  # newest 
    asset_name, asset = next(
        (name, a) for name, a in item["assets"].items() if a["type"] == SHAPEFILE_MEDIA_TYPE
    )

    path = BOUNDARIES_DIR / asset_name
    if path.exists():
        print(f"Using cached boundaries {path.name}")
        return path, item["id"]

    print(f"Downloading {asset['href']} ...")
    BOUNDARIES_DIR.mkdir(parents=True, exist_ok=True)
    # Download to a temporary name so an interrupted transfer is never used as cache
    partial = path.with_name(path.name + ".part")
    with requests.get(asset["href"], stream=True, timeout=60) as download:
        download.raise_for_status()
        with partial.open("wb") as f:
            for chunk in download.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    partial.replace(path)
    return path, item["id"]

# Reads the zipped shapefile and returns a GeoDataFrame with one row per municipality
def load_municipalities(zip_path: Path) -> gpd.GeoDataFrame:
    with zipfile.ZipFile(zip_path) as archive:
        shp = next(
            (n for n in archive.namelist() if n.upper().endswith(f"{MUNICIPALITY_LAYER}.SHP")),
            None,
        )
    if shp is None:
        raise FileNotFoundError(f"No *{MUNICIPALITY_LAYER}.shp found in {zip_path.name}")
    mun = gpd.read_file(f"/vsizip/{zip_path.as_posix()}/{shp}")

    missing = set(MUNICIPALITY_COLUMNS) - set(mun.columns)
    if missing:
        raise KeyError(f"Columns {missing} not found. Available: {list(mun.columns)}")

    if mun.crs is None:
        mun = mun.set_crs(LV95)
    mun = mun.to_crs(LV95)
    mun = mun.set_geometry(mun.geometry.force_2d())

    # Filters swiss municipalities only and removes row with 0 pop
    if "ICC" in mun.columns:
        mun = mun[mun["ICC"] == "CH"]
    mun = mun[mun["EINWOHNERZ"].fillna(0) > 0]


    mun = mun[[*MUNICIPALITY_COLUMNS, "geometry"]].rename(columns=MUNICIPALITY_COLUMNS)

    # Merge exclaves into one row per municipality
    mun = mun.dissolve(
        by="bfs_nr", aggfunc={"name": "first", "canton_nr": "first", "population": "max"}
    ).reset_index()
    mun = mun.astype({"bfs_nr": int, "canton_nr": int, "population": int})
    mun["area_km2"] = (mun.area / 1e6).round(2)
    return mun


# Downloads OSM amenities data from their Overpass API and saves as GeoDataFrame. 

def download_amenities(category: str, tags: dict, bbox: tuple) -> gpd.GeoDataFrame:
    for url in OVERPASS_URLS:
        ox.settings.overpass_url = url
        try:
            print(f"Fetching '{category}' from {url} ...")
            raw = ox.features_from_bbox(bbox, tags=tags)
            break
        except (requests.RequestException, ResponseStatusCodeError) as err:
            print(f"  failed: {err}")
    else:
        raise RuntimeError("All Overpass endpoints failed. Try again later or on another network.")

    # osmnx returns a table with all features as columns. To work with mongoDB we extract the tags into
    # a dictionary with the key being the tag and the value being the tag value. 
    raw = raw.reset_index()
    tag_columns = [c for c in raw.columns if c not in ("element", "id", "geometry")]
    tags_per_feature = [
        {k: v for k, v in row.items() if pd.notna(v)}
        for row in raw[tag_columns].to_dict("records")
    ]
    # Using the dictionary of tags we create a new GeoDataFrame with the tags_per_feature as a column. 
    # the CRS is set to LV95 to match the municipalities GeoDataFrame.
    features = gpd.GeoDataFrame(
        {
            "osm_id": raw["element"] + "/" + raw["id"].astype(str),
            "category": category,
            "name": [t.get("name") for t in tags_per_feature],
            "tags": tags_per_feature,
        },
        geometry=raw.geometry.values,
        crs=raw.crs,
    ).to_crs(LV95)

    # Ways and relations become a single point inside the feature polygon, so that the amenity 
    # can be assigned to a municipality.
    
    features["geometry"] = features.geometry.representative_point()
    print(f"  {len(features)} features")
    return features


# Spatial join of amenities and municipalities. 
# Assigns the BFS (Gemeinde) number of the municipality to each amenity in the column 'bfs_nr'.
def assign_municipality(amenities: gpd.GeoDataFrame, mun: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    joined = gpd.sjoin(amenities, mun[["bfs_nr", "geometry"]], how="inner", predicate="within")
    return joined.drop(columns="index_right").reset_index(drop=True)

# Add an amenity count column and a per-1000-inhabitants column for each category to the municipalities GeoDataFrame.
def add_amenity_counts(mun: gpd.GeoDataFrame, amenities: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    mun = mun.copy()
    for category in AMENITIES:
        counts = amenities.loc[amenities["category"] == category, "bfs_nr"].value_counts()
        mun[f"{category}_count"] = mun["bfs_nr"].map(counts).fillna(0).astype(int)
        mun[f"{category}_per_1000"] = (mun[f"{category}_count"] / mun["population"] * 1000).round(2)
    return mun


# MongoDB build and helper functions
# Converts a GeoSeries to a list of GeoJSON dicts in WGS84 coordinates.
def to_geojson(geometries: gpd.GeoSeries) -> list[dict]:
    return [mapping(g) for g in geometries.to_crs(WGS84).set_precision(1e-6)]

def to_int(value):
    return None if pd.isna(value) else int(value)

# Creates a list of documents for the municipalities collection, one document per municipality.
def municipality_documents(mun: gpd.GeoDataFrame) -> list[dict]:
    geometries = to_geojson(mun.geometry.simplify(SIMPLIFY_TOLERANCE_M))
    records = mun.drop(columns="geometry").to_dict("records")
    return [
        {
            "_id": r["bfs_nr"],
            "name": r["name"],
            "canton_nr": r["canton_nr"],
            "population": r["population"],
            "area_km2": r["area_km2"],
            "employees": to_int(r["employees"]),
            "overnight_stays": to_int(r["overnight_stays"]),
            "station_frequency": r["station_frequency"],
            "amenities": {
                c: {"count": r[f"{c}_count"], "per_1000": r[f"{c}_per_1000"]} for c in AMENITIES
            },
            "geometry": geometry,
        }
        for r, geometry in zip(records, geometries, strict=True)
    ]

# Creates a list of documents for the amenities collection, one document per amenity.
def amenity_documents(amenities: gpd.GeoDataFrame) -> list[dict]:
    locations = to_geojson(amenities.geometry)
    records = amenities.drop(columns="geometry").to_dict("records")
    return [
        {
            "osm_id": r["osm_id"],
            "category": r["category"],
            "name": r["tags"].get("name"),
            "municipality_id": r["bfs_nr"],
            "location": location,
            "tags": r["tags"],
        }
        for r, location in zip(records, locations, strict=True)
    ]

# This creates or replaces a collection in the database. First a staging collection is created,
# the database index is built, and then the staging collection is renamed to the live collection name
def replace_collection(db: Database, name: str, documents: list[dict], indexes: list[IndexModel]):

    staging = db[f"{name}_staging"]
    staging.drop()
    staging.insert_many(documents)
    staging.create_indexes(indexes)
    staging.rename(name, dropTarget=True)

def check_names(mun: gpd.GeoDataFrame, other: pd.DataFrame, show_missing: bool = True):
    names_bfs = other.set_index("bfs_nr")["name"]
    same, different, missing = 0, 0, 0
    for r in mun.itertuples():
        if r.bfs_nr not in names_bfs.index:
            missing += 1
            if show_missing:
                print(f"    not found: {r.bfs_nr} {r.name}")
            continue
        if r.name != names_bfs[r.bfs_nr]:
            different += 1
            print(f"    different name: {r.bfs_nr}  BFS: {names_bfs[r.bfs_nr]}  <->  swisstopo: {r.name}")
        else:
            same += 1
    print(f"  names: {same} same, {different} different, {missing} not found")

# This adds all Employees per 
'''def add_employees(db: Database):
    data = requests.get(EMPLOYEES_URL, timeout=120).json()["dataset"]
    positions = data["dimension"]["Gemeinde"]["category"]["index"]
    labels = data["dimension"]["Gemeinde"]["category"]["label"]
    values = data["value"]

    same, different, missing = 0, 0, 0
    for bfs_nr, pos in positions.items():
        if bfs_nr == "99999":                        
            continue

        name_bfs = labels[bfs_nr].split(" ", 1)[1]
        municipality = db.municipalities.find_one({"_id": int(bfs_nr)})

        if municipality is None:
            missing += 1
            print(f"FEHLT in MongoDB: {labels[bfs_nr]}")
            continue
        if municipality["name"] != name_bfs:
            different += 1
            print(f"ANDERER NAME: {bfs_nr}  BFS: {name_bfs}  ↔  MongoDB: {municipality['name']}")
        else:
            same += 1

        employees = values[pos * 4]                  # 4 Sectors the fist value is the total that is why 4* pos
        db.municipalities.update_one(
            {"_id": int(bfs_nr)},
            {"$set": {"employees": employees}},
        )

    print(f"Beschäftigte: Gleich {same}   Anderer Name {different}   Fehlt {missing}")
'''

'''
# Adds the overnight stays (hotels) per municipality from the BFS (HESTA)
def add_overnight_stays(db: Database):
    data = requests.post(OVERNIGHT_STAYS_URL, json=OVERNIGHT_STAYS_QUERY, timeout=120).json()["dataset"]
    positions = data["dimension"]["Gemeinde"]["category"]["index"]
    labels = data["dimension"]["Gemeinde"]["category"]["label"]
    values = data["value"]

    same, different, missing = 0, 0, 0
    for bfs_nr, pos in positions.items():
        name_bfs = labels[bfs_nr]                    # hier ohne Nummer, z.B. "Kloten"
        municipality = db.municipalities.find_one({"_id": int(bfs_nr)})

        if municipality is None:
            missing += 1
            print(f"FEHLT in MongoDB: {bfs_nr} {name_bfs}")
            continue
        if municipality["name"] != name_bfs:
            different += 1
            print(f"ANDERER NAME: {bfs_nr}  BFS: {name_bfs}  ↔  MongoDB: {municipality['name']}")
        else:
            same += 1

        overnight_stays = values[pos]                # nur 1 Wert pro Gemeinde
        db.municipalities.update_one(
            {"_id": int(bfs_nr)},
            {"$set": {"overnight_stays": overnight_stays}},
        )

    print(f"Logiernächte: Gleich {same}   Anderer Name {different}   Fehlt {missing}")
'''

# Main method block for the full database setup and build process.
# Adds the daily train passengers per municipality from the SBB

'''
def add_station_frequency(db: Database):
    stations = requests.get(STATIONS_URL, timeout=120).json()

    # zuerst alle Gemeinden auf 0 (Gemeinden ohne Bahnhof)
    db.municipalities.update_many({}, {"$set": {"station_frequency": 0}})

    found, missing = 0, 0
    for s in stations:
        if s["geopos"] is None:                          # Bahnhof ohne Koordinaten überspringen
            continue

        point = {"type": "Point", "coordinates": [s["geopos"]["lon"], s["geopos"]["lat"]]}
        result = db.municipalities.update_one(
            {"geometry": {"$geoIntersects": {"$geometry": point}}},   # Gemeinde, in der der Punkt liegt
            {"$inc": {"station_frequency": s["dtv_tjm_tgm"]}},        # Passagiere dazuzählen
        )

        if result.matched_count == 0:
            missing += 1
            print(f"KEINE GEMEINDE: {s['bahnhof_gare_stazione']}")
        else:
            found += 1

    print(f"Bahnhöfe: Zugeordnet {found}   Ohne Gemeinde {missing}")

'''
# Downloads the employees per municipality from the BFS (STATENT).
def download_employees() -> pd.DataFrame:
    print(f"Downloading employees from {EMPLOYEES_URL} ...")
    data = requests.get(EMPLOYEES_URL, timeout=120).json()["dataset"]
    positions = data["dimension"]["Gemeinde"]["category"]["index"]
    labels = data["dimension"]["Gemeinde"]["category"]["label"]
    values = data["value"]

    rows = []
    for bfs_nr, pos in positions.items():
        if bfs_nr == "99999":                              # skip "Schweiz"
            continue
        rows.append({
            "bfs_nr": int(bfs_nr),
            "name": labels[bfs_nr].split(" ", 1)[1],        # "261 Zürich" -> "Zürich"
            "employees": values[pos * 4],                   # 4 sectors per municipality, first = total
        })
    print(f"  {len(rows)} municipalities downloaded")
    return pd.DataFrame(rows)


# Downloads the hotel overnight stays per municipality from the BFS (HESTA).
def download_overnight_stays() -> pd.DataFrame:
    print(f"Downloading overnight stays from {OVERNIGHT_STAYS_URL} ...")
    data = requests.post(OVERNIGHT_STAYS_URL, json=OVERNIGHT_STAYS_QUERY, timeout=120).json()["dataset"]
    positions = data["dimension"]["Gemeinde"]["category"]["index"]
    labels = data["dimension"]["Gemeinde"]["category"]["label"]
    values = data["value"]

    rows = []
    for bfs_nr, pos in positions.items():
        rows.append({
            "bfs_nr": int(bfs_nr),
            "name": labels[bfs_nr],                         # here without number, e.g. "Kloten"
            "overnight_stays": values[pos],                 # only 1 value per municipality
        })
    print(f"  {len(rows)} municipalities downloaded")
    return pd.DataFrame(rows)


# Downloads the train stations with their daily passengers from the SBB.
def download_stations() -> gpd.GeoDataFrame:
    print(f"Downloading train stations from {STATIONS_URL} ...")
    stations = requests.get(STATIONS_URL, timeout=120).json()

    rows = []
    for s in stations:
        if s["geopos"] is None:                             # skip stations without coordinates
            continue
        rows.append({
            "name": s["bahnhof_gare_stazione"],
            "frequency": s["dtv_tjm_tgm"],
            "lon": s["geopos"]["lon"],
            "lat": s["geopos"]["lat"],
        })
    df = pd.DataFrame(rows)
    points = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=WGS84)
    print(f"  {len(points)} stations downloaded ({len(stations) - len(points)} without coordinates)")
    return points.to_crs(LV95)



# Adds the employees column to the municipalities.
def add_employees(mun: gpd.GeoDataFrame, employees: pd.DataFrame) -> gpd.GeoDataFrame:
    print("Adding employees ...")
    mun = mun.copy()
    check_names(mun, employees)
    mun["employees"] = mun["bfs_nr"].map(employees.set_index("bfs_nr")["employees"])

    added = mun["employees"].notna().sum()
    print(f"  {added} municipalities with value, {len(mun) - added} without")
    return mun


# Adds the overnight stays column to the municipalities (only ~186 municipalities have a value).
def add_overnight_stays(mun: gpd.GeoDataFrame, stays: pd.DataFrame) -> gpd.GeoDataFrame:
    print("Adding overnight stays ...")
    mun = mun.copy()
    check_names(mun, stays,show_missing=False)
    mun["overnight_stays"] = mun["bfs_nr"].map(stays.set_index("bfs_nr")["overnight_stays"])

    added = mun["overnight_stays"].notna().sum()
    print(f"  {added} municipalities with value, {len(mun) - added} without")
    return mun

# Assigns every station to its municipality (spatial join) and sums the passengers per municipality.
def add_station_frequency(mun: gpd.GeoDataFrame, stations: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    print("Adding station frequency ...")
    mun = mun.copy()
    joined = gpd.sjoin(stations, mun[["bfs_nr", "geometry"]], how="inner", predicate="within")
    print(f"  stations: {len(joined)} assigned, {len(stations) - len(joined)} outside Switzerland")

    frequency = joined.groupby("bfs_nr")["frequency"].sum()
    mun["station_frequency"] = mun["bfs_nr"].map(frequency).fillna(0).astype(int)   # no station = 0

    added = (mun["station_frequency"] > 0).sum()
    print(f"  {added} municipalities with station, {len(mun) - added} without")
    return mun


def main():
    # Check the database connection before downloading
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000, tz_aware=True)
    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError:
        raise SystemExit(f"MongoDB not reachable at {MONGO_URI}. Start it with: docker compose up -d") from None
    db = client[MONGO_DB]

    ox.settings.cache_folder = OSM_CACHE_DIR
    ox.settings.requests_timeout = 600       # seconds, also sent as the Overpass query timeout
    ox.settings.max_query_area_size = 1e12   # m², one request for the whole country instead of ~20 tiles

    # Extract
    boundaries_zip, boundaries_version = download_boundaries()
    municipalities = load_municipalities(boundaries_zip)
    bbox = tuple(municipalities.to_crs(WGS84).total_bounds)  # (west, south, east, north)
    amenities = pd.concat(
        [download_amenities(category, tags, bbox) for category, tags in AMENITIES.items()],
        ignore_index=True,
    )
    employees = download_employees()
    overnight_stays = download_overnight_stays()
    stations = download_stations()

    # Transform
    amenities = assign_municipality(amenities, municipalities)
    municipalities = add_amenity_counts(municipalities, amenities)
    municipalities = add_employees(municipalities, employees)
    municipalities = add_overnight_stays(municipalities, overnight_stays)
    municipalities = add_station_frequency(municipalities, stations)

    # Load
    replace_collection(
        db, "municipalities", municipality_documents(municipalities),
        [IndexModel([("geometry", GEOSPHERE)]), IndexModel("name")],
    )
    replace_collection(
        db, "amenities", amenity_documents(amenities),
        [
            IndexModel([("location", GEOSPHERE)]),
            IndexModel([("category", 1), ("osm_id", 1)], unique=True),
            IndexModel([("municipality_id", 1), ("category", 1)]),
        ],
    )
    db.metadata.replace_one(
        {"_id": "import"},
        {
            "imported_at": datetime.now(timezone.utc),
            "boundaries_version": boundaries_version,
            "amenity_categories": list(AMENITIES),
        },
        upsert=True,
    )


if __name__ == "__main__":
    main()

