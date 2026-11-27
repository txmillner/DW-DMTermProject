import config, csv, json, pathlib, urllib.request, urllib.error

UA = {"User-Agent": "cs7050-deps/1.0"}

# connection helper, postgres enforces foreign keys by default
def get_db():
  import psycopg2
  import psycopg2.extras
  conn = psycopg2.connect(
    host=config.PG_HOST,
    port=config.PG_PORT,
    dbname=config.PG_DB,
    user=config.PG_USER,
    password=config.get_secret("PG_PASSWORD")
  )
  conn.autocommit = False
  return conn, psycopg2.extras.RealDictCursor(conn)

# idempotent INSERT OR IGNORE equivalent for Postgres
def upsert_dim(conn, cursor, table, cols, values):
  placeholders = ", ".join(["%s"] * len(cols))
  q = (
    f"INSERT INTO {table}({', '.join(cols)}) "
    f"VALUES({', '.join(['%s'] * len(cols))}) "
    f"ON CONFLICT DO NOTHING"
  )
  cursor.execute(q, values)


# normalize to None
def to_int(v):
  if v is None or v == "" or v == "-":
    return None
  try:
    return int(v)
  except (ValueError, TypeError):
    return None


def to_float(v):
  if v is None or v == "" or v == "-":
    return None
  try:
    return float(v)
  except (ValueError, TypeError):
    return None


# Load the 159 counties into dim_county
def load_dim_county(conn, cursor):
  vintage = max(config.ELECTION_VINTAGES.values())
  path = config.RAW / f"census_{vintage}.csv"
  with path.open(newline="") as f:
    rows = list(csv.DictReader(f))
  for r in rows:
    codes = r["county"]
    name = r["NAME"].split(",")[0].strip()
    region = name.replace(" County", "")  # placeholder: will refine later
    upsert_dim(conn, cursor, "dim_county", ["county_codes", "county_name", "region"], (codes, name, region))
  conn.commit()
  print(f"  dim_county: {len(rows)} rows")
  return len(rows)


# load the 8 november general elections into dim_election.
def load_dim_election(conn, cursor):
  for eid, year, edate in config.GENERAL_ELECTIONS:
    upsert_dim(conn, cursor, "dim_election",
               ["election_id", "election_date", "year", "name"],
               (eid, edate, int(year), f"{year} November General"))
  conn.commit()
  print(f"  dim_election: {len(config.GENERAL_ELECTIONS)} rows")
  return len(config.GENERAL_ELECTIONS)


# load fact_county_contest from the SOS .jsonl files
def load_fact_county_contest(conn, cursor):
  total = 0
  name_to_code = {}
  for csv_file in config.RAW.glob('census_*.csv'):
    with open(csv_file) as f:
      reader = csv.reader(f)
      header = next(reader)
      for row in reader:
        if len(row) < 2: continue
        cname = row[0]                    # ex: 'Appling County, Georgia'
        code = row[-1]                    # ex: '001', '003', etc.
        if code and code.isdigit():
          norm = cname.lower()
          for suffix in [' county, georgia', ' county, ga', ' county']:
            norm = norm.replace(suffix, '')
          name_to_code[norm.strip().replace(' ', '-')] = code
  for eid, year, _ in config.GENERAL_ELECTIONS:
    path = config.RAW / f"sos_{eid}.jsonl"
    if not path.exists():
      continue
    with path.open() as f:
      for line in f:
        obj = json.loads(line)
        county_short = obj["shortName"]
        # translate SOS shortName to 3-digit fips code via census mapping
        #norm_key = county_short.lower().replace("-county-ga", "").replace("-county-georgia", "")
        norm_key = county_short.lower().replace("-county-ga","").replace("-county-georgia", "").replace("-county", "")
        if norm_key not in name_to_code:
          continue
        code = name_to_code[norm_key]
        data = obj["data"]
        # county_id lookup
        cursor.execute("SELECT county_id FROM dim_county WHERE county_codes = %s", (code,))
        row = cursor.fetchone()
        if row is None:
          continue
        county_id = row["county_id"]
        for item in data.get("ballotItems", []):
          contest_name = item.get("name") or []
          if isinstance(contest_name, list) and contest_name:
            contest_name = contest_name[0].get("text", "UNKNOWN")
          elif isinstance(contest_name, str):
            contest_name = contest_name
          else:
            contest_name = "UNKNOWN"
          contest_key = contest_name.upper().replace(" ", "_")[:20]
          for opt in (item.get("summaryResults") or {}).get("ballotOptions", []):
            party = opt.get("party", {}).get("abbreviation", "OTHER")
            if party not in ("DEM", "REP"):
              party = "OTHER"
            vote_count = opt.get("voteCount", 0)
            upsert_dim(conn, cursor, "fact_county_contest",
                       ["county_id", "election_id", "contest", "party", "vote_count"],
                       (county_id, eid, contest_key, party, int(vote_count)))
            total += 1
  conn.commit()
  print(f"  fact_county_contest: {total} rows")
  return total


# load fact_demographics from census_ csv files
def load_fact_demographics(conn, cursor):
  total = 0
  for vintage in config.ELECTION_VINTAGES.values():
    path = config.RAW / f"census_{vintage}.csv"
    if not path.exists():
      continue
    with path.open(newline="") as f:
      reader = csv.DictReader(f)
      for row in reader:
        county_codes = row["county"]
        cursor.execute("SELECT county_id FROM dim_county WHERE county_codes = %s", (county_codes,))
        county_row = cursor.fetchone()
        if county_row is None:
          continue
        county_id = county_row["county_id"]
        for var_id in config.CENSUS_VARS:
          val = row.get(var_id)
          if val is None:
            continue
          val = to_float(val)
          if val is None:
            continue
          upsert_dim(conn, cursor, "fact_demographics",
                     ["county_id", "ref_year", "var_id", "value"],
                     (county_id, vintage, var_id, val))
          total += 1
  conn.commit()
  print(f"  fact_demographics: {total} rows")
  return total


# load fact_economy from bls_ga.csv.
def load_fact_economy(conn, cursor):
  path = config.RAW / "bls_ga.csv"
  if not path.exists():
    print("  fact_economy: missing bls_ga.csv, skipping")
    return 0
  total = 0
  with path.open(newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
      sid = row["series_id"]
      state_codes = sid[5:7]
      #county_codes = sid[5:8]   # 3-digit county FIPS
      state_fips = sid[5:7]
      county_codes = sid[7:10]
      measure = sid[-2:]       # last 2 chars = BLS measure code
      if state_codes != config.STATE_CODE:
        continue
      year = to_int(row["year"])
      month = to_int(row["month"])
      value = to_float(row["value"])
      if year is None or month is None:
        continue
      cursor.execute("SELECT county_id FROM dim_county WHERE county_codes = %s", (county_codes,))
      county_row = cursor.fetchone()
      if county_row is None:
        continue
      county_id = county_row["county_id"]
      upsert_dim(conn, cursor, "fact_economy",
                 ["county_id", "measure", "year", "month", "value"],
                 (county_id, measure, year, month, value))
      total += 1
  conn.commit()
  print(f"  fact_economy: {total} rows")
  return total


# data quality report: row counts and sample null checks.
def run_dq_checks(conn, cursor):
  report_path = config.ROOT / "report" / "dq_report.md"
  report_path.parent.mkdir(parents=True, exist_ok=True)
  lines = []
  # table counts
  for table in ("dim_county", "dim_election", "fact_county_contest",
                "fact_demographics", "fact_economy"):
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    cnt = cursor.fetchone()["count"]
    lines.append(f"- {table}: {cnt} rows")
  # null counts for key columns
  for table, col in (("fact_demographics", "value"),
                     ("fact_economy", "value"),
                     ("fact_county_contest", "vote_count")):
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL")
    null_cnt = cursor.fetchone()["count"]
    lines.append(f"- {table}.{col} NULLs: {null_cnt}")
  # distinct parties in fact_county_contest
  cursor.execute("SELECT DISTINCT party FROM fact_county_contest")
  parties = [r["party"] for r in cursor.fetchall()]
  lines.append(f"- fact_county_contest parties: {parties}")
  with report_path.open("w") as f:
    f.write("\n".join(lines) + "\n")
  print(f"  DQ report: {report_path}")


def main():
  config.RAW.mkdir(parents=True, exist_ok=True)
  print("Connecting to warehouse...")
  conn, cursor_factory = get_db()
  #cursor = cursor_factory(conn)
  conn, cursor = get_db()
  print("Running ETL...")
  load_dim_county(conn, cursor)
  load_dim_election(conn, cursor)
  load_fact_county_contest(conn, cursor)
  load_fact_demographics(conn, cursor)
  load_fact_economy(conn, cursor)
  run_dq_checks(conn, cursor)
  conn.close()
  print("ETL complete.")


if __name__ == "__main__":
  main()
