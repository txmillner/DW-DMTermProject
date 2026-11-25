import config, csv, json, time, urllib.request, urllib.error

API_BASE = "https://results.sos.ga.gov/results/public/api"
UA = {"User-Agent": "cs7050-deps/1.0"}


def get_jurisdictions():
  url = f"{API_BASE}/jurisdictions/Georgia"
  req = urllib.request.Request(url, headers=UA)
  with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.load(resp)
  (config.RAW / "sos_jurisdictions.json").write_text(json.dumps(data, indent=1))
  return data


def general_elections(data):
  GENERAL_ELECTIONS = [
    ("2012NovGen", "2012", "2012-11-06"),
    ("2014NovGen", "2014", "2014-11-04"),
    ("2016NovGen", "2016", "2016-11-08"),
    ("2018NovGen", "2018", "2018-11-06"),
    ("2020NovGen", "2020", "2020-11-03"),
    ("2022NovGen", "2022", "2022-11-08"),
    ("2024NovGen", "2024", "2024-11-05"),
    ("11032026GeneralAndSpecialElection", "2026", "2026-11-03"),
  ]
  return {year: eid for eid, year, _ in GENERAL_ELECTIONS}


def fetch_payload(eid, county_shortname=None):
  if county_shortname is None:
      url = f"{API_BASE}/elections/Georgia/{eid}/data"
  else:
      url = f"{API_BASE}/elections/{county_shortname}/{eid}/data"
  req = urllib.request.Request(url, headers=UA)
  try:
      with urllib.request.urlopen(req, timeout=60) as resp:
          if resp.status == 200:
              return resp.status, json.load(resp)
          else:
              return resp.status, None
  except urllib.error.HTTPError as e:
      return e.code, None  # 204/404 are "no data for this county/election"


def load_manifest():
  path = config.RAW / "sos_manifest.csv"
  if not path.exists():
      return {}
  with path.open(newline="") as f:
      return {(r["election_id"], r["county_shortname"]): r["status"]
              for r in csv.DictReader(f) if r["status"] == "ok"}


def main():
  config.RAW.mkdir(parents=True, exist_ok=True)
  print("fetching jurisdictions...")
  data = get_jurisdictions()
  elections = general_elections(data)
  print(f"found {len(elections)} general elections: {sorted(elections)}")

  counties = [c["shortName"] for c in data["childLocalities"]]
  done = set(load_manifest())

  manifest = config.RAW / "sos_manifest.csv"
  new = not manifest.exists()
  mfile = manifest.open("a", newline="")
  mw = csv.writer(mfile)
  if new:
      mw.writerow(["election_id", "year", "election_date", "county_shortname",
                   "county_name", "status", "http_code", "ballot_item_count"])

  for year, eid in sorted(elections.items()):
    date = next(e["electionDate"] for e in data["elections"]
                if e["publicElectionId"] == eid)

    # statewide payload, one per election
    key = (eid, "state")
    if key not in done:
        code, payload = fetch_payload(eid)
        if payload:
            (config.RAW / f"sos_{eid}_state.json").write_text(
                json.dumps(payload, indent=1))
        mw.writerow([eid, year, date, "state", "Georgia",
                     "ok" if payload else "empty", code,
                     len(payload.get("ballotItems", [])) if payload else 0])
        done.add(key)
        time.sleep(1)

    # 159 county payloads, one .jsonl per election
    jpath = config.RAW / f"sos_{eid}.jsonl"
    jfile = jpath.open("a")
    for c in counties:
        key = (eid, c)
        if key in done:
            continue
        code, payload = fetch_payload(eid, c)
        if payload:
            line = json.dumps({"shortName": c, "name": c, "data": payload})
            jfile.write(line + "\n")
        mw.writerow([eid, year, date, c, c,
                     "ok" if payload else "empty", code,
                     len(payload.get("ballotItems", [])) if payload else 0])
        done.add(key)
        time.sleep(0.5)
    jfile.close()
    print(f"  {year} {eid}: done")

  mfile.close()
  print(f"done. {len(done)} payloads cached.")


if __name__ == "__main__":
  main()
