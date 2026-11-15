"""Week 1: load the extracted Parquet files into DuckDB, run SQL quality checks,
and plot each city's lights by day of year to eyeball festival spikes.

Usage:
  python src/load_and_check.py
"""

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt

DB_PATH = "data/nightlights.duckdb"
RAW_GLOB = "data/raw/*.parquet"
FIG_DIR = Path("figures")


def main():
    con = duckdb.connect(DB_PATH)

    # 1. Load raw data into a table
    con.execute(f"""
        CREATE OR REPLACE TABLE nightly AS
        SELECT city_id,
               CAST(date AS DATE)  AS night,
               rad_mean,
               rad_count,
               good_mean           AS good_fraction
        FROM read_parquet('{RAW_GLOB}')
    """)

    # 2. Quality check: coverage per city per year
    print("\nUsable nights per city per year (good_fraction >= 0.5):")
    print(con.execute("""
        SELECT city_id,
               EXTRACT(year FROM night) AS yr,
               COUNT(*)                                        AS nights,
               COUNT(*) FILTER (WHERE good_fraction >= 0.5)    AS usable_nights,
               ROUND(AVG(good_fraction), 2)                    AS avg_good_fraction
        FROM nightly
        GROUP BY city_id, yr
        ORDER BY city_id, yr
    """).df().to_string(index=False))

    # 3. Quality check: longest gap without a usable night, per city
    print("\nLongest run of days without a usable night:")
    print(con.execute("""
        WITH usable AS (
            SELECT city_id, night
            FROM nightly
            WHERE good_fraction >= 0.5 AND rad_mean IS NOT NULL
        ), gaps AS (
            SELECT city_id,
                   night,
                   night - LAG(night) OVER (PARTITION BY city_id ORDER BY night) AS gap_days
            FROM usable
        )
        SELECT city_id, MAX(gap_days) AS longest_gap_days
        FROM gaps
        GROUP BY city_id
        ORDER BY longest_gap_days DESC
    """).df().to_string(index=False))

    # 4. A smoothed series: 7-night rolling median of usable nights (window function)
    con.execute("""
        CREATE OR REPLACE VIEW smoothed AS
        SELECT city_id,
               night,
               EXTRACT(year FROM night)  AS yr,
               EXTRACT(doy FROM night)   AS doy,
               MEDIAN(rad_mean) OVER (
                   PARTITION BY city_id ORDER BY night
                   RANGE BETWEEN INTERVAL 3 DAY PRECEDING AND INTERVAL 3 DAY FOLLOWING
               ) AS rad_smooth
        FROM nightly
        WHERE good_fraction >= 0.5 AND rad_mean IS NOT NULL
    """)

    # 5. Plot: one panel per city, one line per year, x = day of year
    FIG_DIR.mkdir(exist_ok=True)
    cities = [r[0] for r in con.execute("SELECT DISTINCT city_id FROM smoothed ORDER BY 1").fetchall()]
    for city in cities:
        df = con.execute(
            "SELECT yr, doy, rad_smooth FROM smoothed WHERE city_id = ? ORDER BY night", [city]
        ).df()
        fig, ax = plt.subplots(figsize=(11, 4))
        for yr, grp in df.groupby("yr"):
            ax.plot(grp["doy"], grp["rad_smooth"], linewidth=0.8, alpha=0.7, label=str(int(yr)))
        ax.set_title(f"{city}: 7-night rolling median radiance by day of year")
        ax.set_xlabel("Day of year")
        ax.set_ylabel("Radiance (nW/cm²/sr)")
        ax.legend(ncol=8, fontsize=7, loc="upper left")
        fig.tight_layout()
        path = FIG_DIR / f"{city}_by_doy.png"
        fig.savefig(path, dpi=130)
        plt.close(fig)
        print(f"Saved {path}")

    con.close()


if __name__ == "__main__":
    main()
