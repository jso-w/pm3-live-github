# Shows which data is available in MongoDB for the analysis.
# Only municipalities with at least MIN_POPULATION inhabitants are counted.
# Run:  uv run src/pm3/data_overview.py

import os

import pandas as pd
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "pm3")
MIN_POPULATION = 4000

FIELDS = ["population", "area_km2", "cafes", "employees", "overnight_stays", "station_frequency"]


def load_municipalities() -> pd.DataFrame:
    db = MongoClient(MONGO_URI)[MONGO_DB]
    rows = []
    for d in db.municipalities.find({}, {"geometry": 0}):        # without the big boundaries
        rows.append({
            "bfs_nr": d["_id"],
            "name": d["name"],
            "canton_nr": d["canton_nr"],
            "population": d.get("population"),
            "area_km2": d.get("area_km2"),
            "cafes": d.get("amenities", {}).get("cafe", {}).get("count"),
            "employees": d.get("employees"),
            "overnight_stays": d.get("overnight_stays"),
            "station_frequency": d.get("station_frequency"),
        })
    return pd.DataFrame(rows)


def main():
    df = load_municipalities()
    big = df[df["population"] >= MIN_POPULATION]

    print("=" * 70)
    print("MUNICIPALITIES")
    print("=" * 70)
    print(f"  in database:                   {len(df)}")
    print(f"  with >= {MIN_POPULATION} inhabitants:      {len(big)}")
    print(f"  share of Swiss population:     {big['population'].sum() / df['population'].sum():.0%}")
    print(f"  cafés in these municipalities: {int(big['cafes'].sum())} of {int(df['cafes'].sum())}")

    print()
    print("=" * 70)
    print(f"DATA PER FIELD (only municipalities with >= {MIN_POPULATION} inhabitants)")
    print("=" * 70)
    print(f"  {'field':<20}{'with value':>12}{'null':>8}{'= 0':>8}{'min':>12}{'median':>12}{'max':>12}")
    for field in FIELDS:
        values = big[field]
        with_value = values.notna().sum()
        null = values.isna().sum()
        zero = (values == 0).sum()
        print(f"  {field:<20}{with_value:>12}{null:>8}{zero:>8}"
              f"{values.min():>12,.0f}{values.median():>12,.0f}{values.max():>12,.0f}")

    complete = big.dropna(subset=["employees"])
    print()
    print(f"  → usable for the model (employees not null): {len(complete)} municipalities")

    print()
    print("=" * 70)
    print("MUNICIPALITIES WITHOUT EMPLOYEES")
    print("=" * 70)
    for r in big[big["employees"].isna()].itertuples():
        print(f"  {r.bfs_nr:>5}  {r.name}  ({r.population} inhabitants)")

    print()
    print("=" * 70)
    print("TOP 10 BY CAFÉS")
    print("=" * 70)
    top = big.nlargest(10, "cafes")[["name", "population", "cafes", "employees", "overnight_stays", "station_frequency"]]
    print(top.astype({"employees": "Int64", "overnight_stays": "Int64"}))


if __name__ == "__main__":
    main()
