"""Week 1: extract nightly night-light time series for 10 test cities.

For each city and year, this script computes, per night:
  - rad_mean   : mean radiance (nW/cm^2/sr) over good-quality, snow-free pixels
  - rad_count  : number of good pixels used
  - good_mean  : fraction of pixels in the city area that passed the quality filter
and saves one Parquet file per city in data/raw/.

Usage:
  python src/extract_test_cities.py --project YOUR_GCP_PROJECT_ID
  python src/extract_test_cities.py --project YOUR_GCP_PROJECT_ID --cities auckland --years 2023
"""

import argparse
import time
from pathlib import Path

import ee
import pandas as pd

COLLECTION = "NASA/VIIRS/002/VNP46A2"
RADIANCE_BAND = "DNB_BRDF_Corrected_NTL"  # not the gap-filled band: we don't want synthetic values
SCALE_M = 500
FIRST_YEAR, LAST_YEAR = 2012, 2026  # the dataset starts 2012-01-19 and lags the present by months

# Test cities chosen to span calendar systems (solar, lunar, lunisolar) and climates.
# Centre coordinates are approximate; radius is the analysis area around the centre.
CITIES = [
    {"id": "new_york",    "lat": 40.7128,  "lon": -74.0060, "radius_m": 15000},  # Christmas (solar)
    {"id": "london",      "lat": 51.5074,  "lon": -0.1278,  "radius_m": 15000},  # Christmas, high latitude
    {"id": "cairo",       "lat": 30.0444,  "lon": 31.2357,  "radius_m": 15000},  # Ramadan (lunar)
    {"id": "riyadh",      "lat": 24.7136,  "lon": 46.6753,  "radius_m": 15000},  # Ramadan, clear skies
    {"id": "jakarta",     "lat": -6.2088,  "lon": 106.8456, "radius_m": 15000},  # Ramadan, cloudy tropics
    {"id": "delhi",       "lat": 28.6139,  "lon": 77.2090,  "radius_m": 15000},  # Diwali (lunisolar)
    {"id": "mumbai",      "lat": 19.0760,  "lon": 72.8777,  "radius_m": 15000},  # Diwali, monsoon clouds
    {"id": "beijing",     "lat": 39.9042,  "lon": 116.4074, "radius_m": 15000},  # Lunar New Year (lunisolar)
    {"id": "ho_chi_minh", "lat": 10.8231,  "lon": 106.6297, "radius_m": 15000},  # Tet (lunisolar)
    {"id": "auckland",    "lat": -36.8485, "lon": 174.7633, "radius_m": 15000},  # Southern Hemisphere, Christmas in summer
]


def prepare(img: ee.Image) -> ee.Image:
    """Mask out poor-quality and snow pixels; keep a 'good' band to measure coverage."""
    qf = img.select("Mandatory_Quality_Flag")
    snow = img.select("Snow_Flag")
    good = qf.lte(1).And(snow.eq(0))  # 0/1 = high quality; anything else = poor or fill
    rad = img.select(RADIANCE_BAND).updateMask(good).rename("rad")
    return rad.addBands(good.rename("good"))


def city_year_features(city: dict, year: int) -> list[dict]:
    geom = ee.Geometry.Point([city["lon"], city["lat"]]).buffer(city["radius_m"])
    coll = (
        ee.ImageCollection(COLLECTION)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .filterBounds(geom)
    )
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)

    def per_image(img):
        stats = prepare(img).reduceRegion(
            reducer=reducer, geometry=geom, scale=SCALE_M, maxPixels=1e8
        )
        return ee.Feature(None, stats).set("date", img.date().format("YYYY-MM-dd"))

    info = coll.map(per_image).getInfo()
    return [f["properties"] for f in info["features"]]


def fetch_with_retry(city: dict, year: int, attempts: int = 3) -> list[dict]:
    for i in range(attempts):
        try:
            return city_year_features(city, year)
        except ee.EEException as err:  # quota or timeout errors are usually temporary
            wait = 10 * (i + 1)
            print(f"  {city['id']} {year}: {err} -> retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed after {attempts} attempts: {city['id']} {year}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="Earth Engine-registered Google Cloud project ID")
    parser.add_argument("--cities", nargs="*", help="Subset of city ids (default: all)")
    parser.add_argument("--years", nargs="*", type=int, help="Subset of years (default: all)")
    parser.add_argument("--out", default="data/raw", help="Output folder")
    args = parser.parse_args()

    ee.Initialize(project=args.project)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cities = [c for c in CITIES if not args.cities or c["id"] in args.cities]
    years = args.years or list(range(FIRST_YEAR, LAST_YEAR + 1))

    for city in cities:
        rows = []
        for year in years:
            t0 = time.time()
            feats = fetch_with_retry(city, year)
            rows.extend(feats)
            print(f"{city['id']} {year}: {len(feats)} nights ({time.time() - t0:.1f}s)")
        df = pd.DataFrame(rows)
        if df.empty:
            print(f"{city['id']}: no data returned")
            continue
        df["city_id"] = city["id"]
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").drop_duplicates(["city_id", "date"])
        path = out / f"{city['id']}.parquet"
        df.to_parquet(path, index=False)
        print(f"Saved {len(df)} rows -> {path}")


if __name__ == "__main__":
    main()
