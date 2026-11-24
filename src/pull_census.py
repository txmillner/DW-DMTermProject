'''
fetches all vintages into data/raw
'''

import config, csv, json, time, urllib.parse, urllib.request

API_BASE = "https://api.census.gov/data"
UA = {"User-Agent": "cs7050-deps/1.0"} # API occasionally 400s generic/absent user agents

# return (var id: label) for everything the given vintage offerrs
def catalog(vintage):
  url = f"{API_BASE}/{vintage}/acs/acs5/profile/variables.json?key={config.get_secret('CENSUS_API_KEY')}"
  req = urllib.request.Request(url, headers=UA)
  with urllib.request.urlopen(req, timeout=60) as resp:
    return {vid: meta.get("label", "") for vid, meta in json.load(resp)["variables"].items()}

# if a var ID doesn't exist in that vintage, there's no error, it just silently drops the column + HTTP 200
def check_variables(vintage):
  have = catalog(vintage)
  missing  = [v for v in config.CENSUS_VARS if v not in have]
  return missing

# fetch all GA counties for one vintage; write to file, return num country rows written
def pull_vintage(vintage):
  get = "NAME," + ",".join(config.CENSUS_VARS)
  params = urllib.parse.urlencode({
    "get": get,
    "for": "county:*",
    "in": f"state:{config.STATE_CODE}",
    "key": config.get_secret("CENSUS_API_KEY"),
  })
  url = f"{API_BASE}/{vintage}/acs/acs5/profile?{params}"
  req = urllib.request.Request(url, headers=UA)
  with urllib.request.urlopen(req, timeout=120) as resp:
    raw = resp.read().decode("utf-8")
  # a valid response is always a JSON array starting with '['.
  if not raw.startswith("["):
    raise RuntimeError(f"vintage {vintage}: expected JSON array, got:{raw[:200]!r}") # wrap it in quotes and escape the newlines
  #rows = list(csv.reader(raw.splitlines()))
  rows = json.loads(raw)
  out_path = config.RAW / f"census_{vintage}.csv"
  with out_path.open("w", newline="") as f:
    csv.writer(f).writerows(rows)
  return len(rows) - 1  # minus header

def main():
  config.RAW.mkdir(parents=True, exist_ok=True)
 
  # precheck
  for vintage in config.ELECTION_VINTAGES.values():
    missing = check_variables(vintage)
    if missing:
      raise SystemExit(f"vintage {vintage} is missing {len(missing)} vars: {missing}")
 
  # pull each vintage
  print(f"pulling {len(config.ELECTION_VINTAGES)} vintages > {config.RAW}")
  for i, vintage in enumerate(sorted(config.ELECTION_VINTAGES.values())):
    n = pull_vintage(vintage)
    print(f"  {vintage}: {n} counties")
    if i < len(config.ELECTION_VINTAGES) - 1:
      time.sleep(1)  # delay between requests
  print("done")


if __name__ == "__main__":
  main()
