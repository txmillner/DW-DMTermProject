-- DIMENSIONS
-- ga counties, 159 rows
CREATE TABLE dim_county (
  county_id    BIGSERIAL PRIMARY KEY,
  county_codes  TEXT NOT NULL UNIQUE,
  county_name  TEXT NOT NULL,
  state_code   TEXT NOT NULL DEFAULT '13',
  region       TEXT
);

-- the 8 nov general elections from 2012 to 2026
CREATE TABLE dim_election (
  election_id    TEXT PRIMARY KEY,
  election_date  DATE NOT NULL,
  year           INTEGER NOT NULL,
  name           TEXT NOT NULL,
  election_type  TEXT NOT NULL DEFAULT 'General',
  is_official    INTEGER NOT NULL DEFAULT 1  -- 1 = certified
);

-- FACT TABLES
-- vote totals
CREATE TABLE fact_county_contest (
  county_id   INTEGER NOT NULL,
  election_id TEXT NOT NULL,
  contest     TEXT NOT NULL,
  party       TEXT NOT NULL,
  vote_count  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (county_id, election_id, contest, party),
  FOREIGN KEY (county_id)  REFERENCES dim_county(county_id),
  FOREIGN KEY (election_id) REFERENCES dim_election(election_id)
);

-- demo per county and vintage
CREATE TABLE fact_demographics (
  county_id INTEGER NOT NULL,
  ref_year  INTEGER NOT NULL,
  var_id    TEXT NOT NULL,
  value     REAL,
  PRIMARY KEY (county_id, ref_year, var_id),
  FOREIGN KEY (county_id) REFERENCES dim_county(county_id)
);

-- bls monthly by county
CREATE TABLE fact_economy (
  county_id INTEGER NOT NULL,
  measure   TEXT NOT NULL,
  year      INTEGER NOT NULL,
  month     INTEGER NOT NULL,
  value     REAL,
  PRIMARY KEY (county_id, measure, year, month),
  FOREIGN KEY (county_id) REFERENCES dim_county(county_id)
);

-- OLAP VIEWS
-- region lean (D/R) view by year and office
CREATE VIEW v_lean AS
SELECT
  fc.county_id,
  fc.election_id,
  fc.contest,
  SUM(CASE WHEN fc.party = 'DEM' THEN fc.vote_count ELSE 0 END) AS dem_votes,
  SUM(CASE WHEN fc.party = 'REP' THEN fc.vote_count ELSE 0 END) AS rep_votes,
  ROUND(100.0 * (
    SUM(CASE WHEN fc.party = 'DEM' THEN fc.vote_count ELSE 0 END)
    - SUM(CASE WHEN fc.party = 'REP' THEN fc.vote_count ELSE 0 END)
  ) / NULLIF(SUM(CASE WHEN fc.party IN ('DEM', 'REP') THEN fc.vote_count ELSE 0
END), 0), 4) AS margin_pp
FROM fact_county_contest fc
JOIN dim_county dc ON fc.county_id = dc.county_id
JOIN dim_election de ON fc.election_id = de.election_id
GROUP BY dc.region, de.year, fc.county_id, fc.contest, fc.election_id;

-- model input view with anti-leakage joins
CREATE VIEW v_model AS
SELECT
  fc.county_id,
  fc.election_id,
  fc.contest,
  (SUM(CASE WHEN fc.party = 'DEM' THEN fc.vote_count ELSE 0 END)
   - SUM(CASE WHEN fc.party = 'REP' THEN fc.vote_count ELSE 0 END)) AS margin_pp,
  fd.var_id,
  fd.value       AS demog_value,
  fe.measure,
  fe.value       AS econ_value
FROM fact_county_contest fc
JOIN dim_election de ON fc.election_id = de.election_id
LEFT JOIN fact_demographics fd ON fd.county_id = fc.county_id AND fd.ref_year = de.year - 2
LEFT JOIN fact_economy fe ON fe.county_id = fc.county_id AND fe.year = de.year - 1
GROUP BY fc.county_id, fc.election_id, fc.contest, fd.var_id, fd.value, fe.measure, fe.value;

-- county trend view
CREATE VIEW v_county_trend AS
SELECT
  v.county_id,
  v.contest,
  de.year,
  v.margin_pp
FROM v_lean v JOIN dim_election de ON v.election_id = de.election_id;
