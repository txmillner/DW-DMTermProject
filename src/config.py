'''
Shared config file
'''

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent # repo/src/file
RAW = ROOT / "data" / "raw"


PG_HOST = "localhost"
PG_PORT = 5432
PG_DB = "warehouse"
PG_USER = "txmillner"

STATE_CODE = "13" # GA code is 13
ELECTION_VINTAGES = { # vintage is the census' verbage
  2012: 2010,
  2014: 2012,
  2016: 2014,
  2018: 2016,
  2020: 2018,
  2022: 2020,
  2024: 2022,
  2026: 2024,
}

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

CENSUS_VARS = [
  # Employment status
  "DP03_0007PE",  # % not in labor force (16+)
  "DP03_0048PE",  # % government workers
  "DP03_0049PE",  # % self-employed
  # Disability
  "DP02_0076PE",  # % with a disability (18-64)
  "DP02_0078PE",  # % with a disability (65+)
  # Education
  "DP02_0062PE",  # % high school grad (25+)
  # Health insurance
  "DP03_0096PE",  # % with health insurance
  "DP03_0101PE",  # % uninsured (under 19)
  # Income
  "DP03_0052PE",  # % households under $10k
  "DP03_0055PE",  # % households $25k-$49k
  "DP03_0074PE",  # % households on SNAP
  # Housing costs
  "DP04_0091PE",  # % owner-occupied with mortgage
  "DP04_0101PE",  # median monthly housing cost (mortgaged)
  # Place of birth
  "DP02_0094PE",  # % foreign-born
  # Race
  "DP02_0096PE",  # % foreign-born naturalized citizens
  # Sex and age
  "DP05_0021PE",  # % 18 and over
  "DP05_0024PE",  # % 65 and over
  "DP05_0002PE",  # % male
  "DP05_0003PE",  # % female
  # Housing tenure
  "DP04_0046PE",  # % owner-occupied
  "DP04_0014PE",  # % mobile homes
  "DP04_0047PE",  # % renter-occupied

  "DP05_0001E",   # population
  "DP05_0018E",   # median age
  "DP05_0037E",   # white alone
  "DP05_0045E",   # black alone
  "DP05_0061E",   # asian alone
  "DP05_0035E",   # two or more races
  "DP03_0062E",   # median household income
  "DP03_0086E",   # median family income
  "DP04_0089E",   # median home value
  "DP04_0134E",   # median gross rent
  "DP02_0067E",   # HS grad or higher, 25+
  "DP02_0068E",   # bachelor's or higher, 25+
  "DP03_0009PE",  # unemployment rate (ACS)
]

# BLS
BLS_MEASURES = ["03", "04", "05", "06"]
BLS_MEASURE_LABELS = {
  "03": "unemployment rate (%)",
  "04": "unemployed (count)",
  "05": "employed (count)",
  "06": "civilian labor force (count)",
}
BLS_YEAR_START = "2006"
BLS_YEAR_END = "2025"
BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
BLS_BATCH_SIZE = 50  # hard API limit: max 50 series per query

def get_secret(name: str):
  path = ROOT / "secrets.env"
  if not path.exists():
    raise FileNotFoundError(f"{path} missing - copy secrets.env.example and replace with your keys")
  for line in path.read_text().splitlines():
    line = line.strip()
    key, _, value = line.partition("=")
    if key.strip() == name:
      return value.strip()
  raise KeyError(f"{name} is not set in secrets.env")

# returns the 20 char LAUCN format - LAUCN prefix + 2-digit state code (13 for GA) + 3 digit county code + 8 zeroes + 2 digit MEASURE codes
def bls_series_id(state_codes, county_codes, measure):
  if measure not in BLS_MEASURES:
    raise ValueError(f"{measure!r} is not one of {BLS_MEASURES}")
  if len(state_codes) != 2 or len(county_codes) != 3 or measure not in BLS_MEASURES:
    raise ValueError(f"bad LAUCN inputs: {state_codes!r} {county_codes!r} {measure!r}")
  return f"LAUCN{state_codes}{county_codes}{'0' * 8}{measure}"
