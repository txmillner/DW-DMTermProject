"""
Load CPI data from raw/cpi_annual.csv into fact_economy (measure 'cpi').
Run after pull_fred.py has created raw/cpi_annual.csv.
"""
import config, csv
import psycopg2, psycopg2.extras

def main():
    config.RAW.mkdir(parents=True, exist_ok=True)
    path = config.RAW / "cpi_annual.csv"
    if not path.exists():
        print(f"Missing {path}. Run pull_fred.py first (requires FRED_API_KEY).")
        return
    
    conn = psycopg2.connect(
        host=config.PG_HOST, port=config.PG_PORT,
        dbname=config.PG_DB, user=config.PG_USER,
        password=config.get_secret("PG_PASSWORD")
    )
    cur = conn.cursor()
    
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            year = int(row["year"])
            cpi = float(row["cpi"])
            cur.execute("""
                INSERT INTO fact_economy (county_id, year, measure, value)
                SELECT county_id, %s, 'cpi', %s
                FROM dim_county
                ON CONFLICT (county_id, year, measure) DO UPDATE SET value = EXCLUDED.value
            """, (year, row["cpi"]))
    
    conn.commit()
    print(f"Loaded CPI data into fact_economy (measure='cpi')")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
