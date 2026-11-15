# Cultural calendars from space

Discovering hidden rhythms in cities' night-time lights from satellite data, without being told the holiday dates, and inferring which calendar system (solar, lunar or lunisolar) drives each one.

## Week 1 goal
Nightly light time series for 10 test cities, stored in DuckDB, with festival spikes visible in plots.

## Setup
1. **Register an Earth Engine Cloud project** (noncommercial) at https://console.cloud.google.com/earth-engine and complete the noncommercial questionnaire. Note your project ID.
2. **Create an environment and install:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. **Authenticate once:**
   ```bash
   earthengine authenticate
   earthengine set_project YOUR_PROJECT_ID
   ```

## Run
```bash
# Smoke test: one city, one year
python src/extract_test_cities.py --project YOUR_PROJECT_ID --cities auckland --years 2023

# All 10 test cities, 2012 onwards (a few minutes per city)
python src/extract_test_cities.py --project YOUR_PROJECT_ID

# Load into DuckDB, run SQL quality checks, save plots to figures/
python src/load_and_check.py
```

## What to look for in the plots
- **New York / London / Auckland:** a rise through December (Christmas lights).
- **Cairo / Riyadh / Jakarta:** a brighter period that moves about 11 days earlier each year (Ramadan).
- **Delhi / Mumbai:** a short spike in Oct–Nov that moves between years (Diwali).
- **Beijing / Ho Chi Minh City:** a change around late Jan–Feb (Lunar New Year / Tet). Watch whether it's a rise or a dip.
- **Data quirks to note:** gaps from monsoon cloud (Mumbai, Jakarta), missing summer nights at high latitude (London), and long-term trends from switching to LEDs.

## Layout
```
src/extract_test_cities.py   Earth Engine -> per-city Parquet (data/raw/)
src/load_and_check.py        Parquet -> DuckDB, SQL quality checks, plots (figures/)
data/                        raw Parquet + nightlights.duckdb (not committed)
figures/                     plots
```

## Notes
- Radiance band: `DNB_BRDF_Corrected_NTL` (not gap-filled, to avoid synthetic values).
- Quality filter: `Mandatory_Quality_Flag` ≤ 1 and `Snow_Flag` = 0.
- Analysis area: a 15 km radius around each city centre for now. Replace with proper urban boundaries in week 2.
