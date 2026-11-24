'''
for each of 159 county, get monthly LAUS data 2006-2025  from BLS API
PULL CENSUS MUST RUN FIRST
'''

import config, csv, json, time, urllib.request

UA = {"User-Agent": "cs7050-deps/1.0"}

# returns 159 ga county fips codes, pulled from latest census data on disk
def get_county_codes():
  vintage = max(config.ELECTION_VINTAGES.values())
  path = config.RAW / f"census_{vintage}.csv"
  with path.open(newline="") as f:
    rows = list(csv.DictReader(f))
  return [r["county"] for r in rows]

def all_series_ids():
  codes = get_county_codes()
  ids = []
  for c in codes:
    for m in config.BLS_MEASURES:
      ids.append(config.bls_series_id(config.STATE_CODE, c, m))
  return ids

def fetch_batch(series_ids):
  body = json.dumps({
    "seriesid": series_ids,
    "startyear": config.BLS_YEAR_START,
    "endyear": config.BLS_YEAR_END,
    "catalog_names": True,
    "registrationkey": config.get_secret("BLS_API_KEY"),
  }).encode("utf-8")
  req = urllib.request.Request(
    config.BLS_API_URL, data=body, headers={**UA, "Content-Type": "application/json", "X-Version-2": "true"},
  )
  with urllib.request.urlopen(req, timeout=120) as resp:
    payload = json.load(resp)
    if payload.get("status") != "REQUEST_SUCCEEDED":
      raise RuntimeError(f"BLS status={payload.get('status')} {payload.get('message')}")
  if "errors" in payload and payload["errors"]: # BLS returns 200 even when some in batch are invalid, list under "errors"
    raise RuntimeError(f"BLS errors: {payload['errors']}")
  result = {}
  for s in payload.get("Results", {}).get("series", []):
    points = []
    for d in s.get("data", []):
      year = d["year"]
      month = d.get("period", "M00").lstrip("M")
      points.append((year, month, d.get("value")))
    result[s["seriesID"]] = points
  return result

def write_rows(path, rows):
  with path.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["series_id", "name", "year", "month", "value"])
    w.writerows(rows)

def main():
  config.RAW.mkdir(parents=True, exist_ok=True)
  ids = all_series_ids()
  print(f"pulling {len(ids)} BLS series in batches of {config.BLS_BATCH_SIZE}")

  rows = []
  names = {}
  batches = [ids[i:i + config.BLS_BATCH_SIZE]
    for i in range(0, len(ids), config.BLS_BATCH_SIZE)]

  for n, batch in enumerate(batches):
    result = fetch_batch(batch)
    for sid, points in result.items():
      for year, month, value in points:
        rows.append([sid, names.get(sid, ""), year, month, value])
    print(f"  batch {n + 1}/{len(batches)}: {len(result)} series, {len(rows)} rows so far")
    time.sleep(2)

  write_rows(config.RAW / "bls_ga.csv", rows)
  print(f"done: {len(rows)} rows -> {config.RAW / 'bls_ga.csv'}")

if __name__ == "__main__":
  main()
