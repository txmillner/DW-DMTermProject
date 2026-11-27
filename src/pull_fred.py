"""
Pull CPI inflation data from FRED API.
Adds annual CPI (Consumer Price Index) to fact_economy as measure 'cpi'.
Requires FRED_API_KEY in secrets.env (get from https://fred.stlouisfed.org/docs/api/api_key.html)
"""
import config, csv, urllib.request, json

CPI_SERIES_ID = "CPIAUCSL"  # Consumer Price Index for All Urban Consumers: All Items
START_YEAR = 2006
END_YEAR = 2025

def fetch_cpi():
    """Fetch annual CPI data from FRED."""
    api_key = config.get_secret("FRED_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise ValueError("FRED_API_KEY not set in secrets.env. Get one from https://fred.stlouisfed.org/docs/api/api_key.html")
    
    url = f"https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key={api_key}&file_type=json&observation_start=2006-01-01&observation_end=2025-12-31&frequency=a&aggregation_method=avg"
    req = urllib.request.Request(url, headers={"User-Agent": "cs7050-deps/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    return data["observations"]

def main():
    config.RAW.mkdir(parents=True, exist_ok=True)
    print("Fetching CPI data from FRED...")
    obs = fetch_cpi()
    
    rows = []
    for o in obs:
        if o["value"] == ".":
            continue
        year = int(o["date"][:4])
        value = float(o["value"])
        rows.append((year, value))
    
    out_path = config.RAW / "cpi_annual.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["year", "cpi"])
        w.writerows(rows)
    print(f"Saved {len(rows)} annual CPI observations to {out_path}")

if __name__ == "__main__":
    main()
