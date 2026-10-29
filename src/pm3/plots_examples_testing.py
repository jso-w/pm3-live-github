# Generates some plots to test the functioning of the mongoDB database
# Authors: PM3 Gruppe 3

import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from pymongo import MongoClient
from shapely.geometry import shape

from pm3.build_db import LV95, MONGO_DB, MONGO_URI, WGS84

# Amenity category to plot
CATEGORY = "cafe"

HEX_SIZE_M = 5000

# Color scheme
BROWN = LinearSegmentedColormap.from_list(
    "browns", ["#f8f4e9", "#e0d6b8", "#c2a87d", "#9b7a4d", "#6d4f2c"]
)



# Loading the data from mongoDB

def load_municipalities(db, category: str) -> gpd.GeoDataFrame:
    docs = list(db.municipalities.find(
        {}, {"name": 1, "population": 1, "geometry": 1, f"amenities.{category}": 1}
    ))
    return gpd.GeoDataFrame(
        {
            "name": [d["name"] for d in docs],
            "population": [d["population"] for d in docs],
            "count": [d["amenities"][category]["count"] for d in docs],
            "per_1000": [d["amenities"][category]["per_1000"] for d in docs],
        },
        geometry=[shape(d["geometry"]) for d in docs],
        crs=WGS84,
    ).to_crs(LV95)


def load_amenity_points(db, category: str) -> gpd.GeoDataFrame:
    docs = db.amenities.find({"category": category}, {"_id": 0, "location.coordinates": 1})
    lon, lat = zip(*(d["location"]["coordinates"] for d in docs), strict=True)
    return gpd.GeoDataFrame(geometry=gpd.points_from_xy(lon, lat), crs=WGS84).to_crs(LV95)


# Some plots to show the data for testing

def plot_per_capita_heatmap(mun: gpd.GeoDataFrame, category: str) -> plt.Figure:
    vmax = mun["per_1000"].quantile(0.95)

    fig, ax = plt.subplots(figsize=(12, 8))
    mun.plot(
        column="per_1000",
        cmap="YlOrRd",
        vmin=0,
        vmax=vmax,
        linewidth=0.1,
        edgecolor="grey",
        legend=True,
        legend_kwds={"label": f"{category} per 1,000 residents (capped at {vmax:.1f})", "shrink": 0.6},
        ax=ax,
    )
    ax.set_title(f"Availability per 1,000 residents: {category} (OSM)")
    ax.set_axis_off()
    fig.tight_layout()
    return fig


def plot_point_density(mun: gpd.GeoDataFrame, points: gpd.GeoDataFrame, category: str) -> plt.Figure:
    xmin, ymin, xmax, ymax = mun.total_bounds
    gridsize = int((xmax - xmin) / HEX_SIZE_M)

    fig, ax = plt.subplots(figsize=(12, 8))
    mun.plot(ax=ax, color="#f0efec", edgecolor="white", linewidth=0.2)
    hexes = ax.hexbin(
        points.geometry.x,
        points.geometry.y,
        gridsize=gridsize,
        extent=(xmin, xmax, ymin, ymax),
        bins="log",
        mincnt=1,
        cmap=BROWN,
        linewidths=0,
    )
    fig.colorbar(hexes, ax=ax, shrink=0.6, format="%d",
                 label=f"{category} per {HEX_SIZE_M // 1000} km hexagon (log scale)")
    ax.set_title(f"Location density: {category} (OSM, n = {len(points):,})")
    ax.set_aspect("equal")
    ax.set_axis_off()
    fig.tight_layout()
    return fig


# Main method

def main():
    db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)[MONGO_DB]
    meta = db.metadata.find_one({"_id": "import"})
    if meta is None:
        raise SystemExit("Database is empty. Run: uv run src/pm3/build_db.py")
    if CATEGORY not in meta["amenity_categories"]:
        raise SystemExit(f"Unknown category '{CATEGORY}'. Available: {meta['amenity_categories']}")

    mun = load_municipalities(db, CATEGORY)
    points = load_amenity_points(db, CATEGORY)

    plot_per_capita_heatmap(mun, CATEGORY)
    plot_point_density(mun, points, CATEGORY)
    plt.show()


if __name__ == "__main__":
    main()
