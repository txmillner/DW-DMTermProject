import config, numpy as np, pandas as pd, psycopg2
from sklearn.linear_model import Ridge # ridge_model()
from sklearn.ensemble import RandomForestClassifier # rf_model()


TRAIN_YEARS = [2012, 2014, 2016, 2018]
VALIDATE_YEARS = [2020, 2022]
TEST_YEAR = 2024
PREDICT_YEAR = 2026

def get_db():
  conn = psycopg2.connect(host=config.PG_HOST, port=config.PG_PORT, dbname=config.PG_DB, user=config.PG_USER,  password=config.get_secret("PG_PASSWORD"))
  cur = conn.cursor()
  return conn, cur

def ridge_model(X,y):
  ridge = Ridge()
  ridge.fit(X,y)
  return ridge

def rf_model(X,y):
  rf = RandomForestClassifier(n_estimators=100, random_state=42)
  rf.fit(X, y)
  return rf

# load data from warehouse
def load_data(cur):
  years = [2012, 2014, 2016, 2018, 2020, 2022, 2024]
  placeholders = ','.join(['%s'] * len(years))
  q = """SELECT fc.county_id, fc.election_id, fc.contest, fc.party,fc.vote_count,de.year
         FROM fact_county_contest fc
         JOIN dim_election de ON fc.election_id = de.election_id
         WHERE de.year IN (%s)""" % placeholders
  cur.execute(q, years)
  rows = cur.fetchall()
  
  df = pd.DataFrame(rows, columns=["county_id", "election_id", "contest", "party", "vote_count", "year"])
  if df.empty:
    df['margin_pp'] = 0.0
  else:
    # compute margin_pp per county×election×contest (same for DEM/REP)
    margins = {}
    for idx, sub in df.groupby(['county_id','election_id','contest']):
      dem = sub[sub['party']=='DEM']['vote_count'].sum()
      rep = sub[sub['party']=='REP']['vote_count'].sum()
      total = sub['vote_count'].sum()
      m = round(100.0 * (dem - rep) / total, 4) if total > 0 else 0.0
      # Store for BOTH party rows (DEM and REP get same margin_pp)
      for party in ['DEM', 'REP']:
        margins[(idx[0], idx[1], idx[2], party)] = m
    df['margin_pp'] = df.set_index(['county_id','election_id','contest','party']).index.map(
      lambda x: margins.get(x, 0.0))
  df = df.drop_duplicates(subset=['county_id','election_id','contest','party'])
  return df

# for per county predictions
def aggregate_to_county_election(df):
  feature_cols = [c for c in df.columns if c not in ['county_id', 'election_id', 'year', 'margin_pp']]
  agg_dict = {'margin_pp': 'mean'}
  for col in feature_cols:
      agg_dict[col] = 'first'
  return df.groupby(['county_id', 'election_id', 'year']).agg(agg_dict).reset_index()

def load_2026_features(cur):
  cur.execute("""
    SELECT fd.county_id, fd.var_id, fd.value
    FROM fact_demographics fd
    WHERE fd.ref_year = 2024 AND fd.var_id IN %s
  """, (tuple(config.CENSUS_VARS),))
  demo_rows = cur.fetchall()
  
  # pivot demographics , county id x var id
  demo_df = pd.DataFrame(demo_rows, columns=['county_id', 'var_id', 'value'])
  demo_pivot = demo_df.pivot(index='county_id', columns='var_id', values='value').reset_index()

  # 2025 econ/ bls measures
  cur.execute("""
    SELECT fe.county_id, fe.measure, AVG(fe.value) as avg_value
    FROM fact_economy fe
    WHERE fe.year = 2025
    GROUP BY fe.county_id, fe.measure
  """)
  econ_rows = cur.fetchall()
  econ_df = pd.DataFrame(econ_rows, columns=['county_id', 'measure', 'avg_value'])
  econ_pivot = econ_df.pivot(index='county_id', columns='measure',values='avg_value').reset_index()
  # merge
  features = demo_pivot.merge(econ_pivot, on='county_id', how='outer')
  return features

#train
def train_models(train_df):
  margin = train_df["margin_pp"]
  y_reg = margin + margin.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
  y_clf = margin.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
  
  last_train_year = max(TRAIN_YEARS)
  train_last = train_df[train_df["year"] == last_train_year].groupby("county_id")["margin_pp"].mean()
  pred = train_df["county_id"].map(train_last)
  
  from sklearn.linear_model import Ridge
  ridge = Ridge()
  ridge.fit(train_df[["margin_pp"]], margin)
  
  from sklearn.ensemble import RandomForestClassifier
  rf = RandomForestClassifier(n_estimators=100, random_state=42)
  rf.fit(train_df[["margin_pp"]], margin.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)))
  
  return {
    "persistence_mae": abs(pred - margin).mean(),
    "ridge_score": ridge.score(train_df[["margin_pp"]], margin),
    "rf_accuracy": rf.score(train_df[["margin_pp"]], margin.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))),
    "feature_importance": rf.feature_importances_[0] if hasattr(rf, "feature_importances_") else 0.0
  }


def predict_2026(cur, model_bundle):
  features_2026 = load_2026_features(cur)
  sql = """
    WITH vote_agg AS (
      SELECT fc.county_id,fc.election_id,de.year,
      SUM(CASE WHEN fc.party = 'DEM' THEN fc.vote_count ELSE 0 END) AS dem_votes,
      SUM(CASE WHEN fc.party = 'REP' THEN fc.vote_count ELSE 0 END) AS rep_votes,
      SUM(CASE WHEN fc.party IN ('DEM', 'REP') THEN fc.vote_count ELSE 0 END) AS total_votes
      FROM fact_county_contest fc
      JOIN dim_election de ON fc.election_id = de.election_id
      WHERE de.year IN %s
      GROUP BY fc.county_id, fc.election_id, de.year
    )
    SELECT county_id, election_id, year,
    ROUND(100.0 * (dem_votes - rep_votes) / NULLIF(total_votes, 0), 4) AS margin_pp FROM vote_agg
  """
  cur.execute(sql, (tuple(TRAIN_YEARS + VALIDATE_YEARS),))

  hist = pd.DataFrame(cur.fetchall(), columns=['county_id', 'election_id', 'year', 'margin_pp'])
  train_df = aggregate_to_county_election(hist.merge(load_2026_features(cur), on='county_id'))
  feature_cols = [c for c in train_df.columns if c not in ['county_id', 'election_id', 'year', 'margin_pp']]
  ridge = Ridge().fit(train_df[feature_cols], train_df['margin_pp'])
  y_clf = train_df['margin_pp'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
  rf = RandomForestClassifier(n_estimators=100, random_state=42)
  rf.fit(train_df[feature_cols], y_clf)
  features_2026 = load_2026_features(cur)
  X_2026 = features_2026[feature_cols].copy()
  for col in feature_cols:
    if col not in X_2026.columns:
      X_2026[col] = 0.0
  ridge = Ridge().fit(train_df[feature_cols], train_df['margin_pp'])
  rf = RandomForestClassifier(n_estimators=100, random_state=42)
  rf.fit(train_df[feature_cols], train_df['margin_pp'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)))
  pred_margin = ridge.predict(features_2026[feature_cols])
  #pred_sign = rf.predict(features_2026[feature_cols])
  pred_sign = np.sign(pred_margin)
  return pd.DataFrame({
    'county_id': features_2026['county_id'],
    'predicted_margin_2026': pred_margin,
    'predicted_sign_2026': pred_sign
  })


# metrics
def compute_regression_metrics(y_true, y_pred):
  return {'mae': abs(y_true - y_pred).mean()}
def compute_classification_metrics(y_true, y_pred):
  acc = (y_true == y_pred).mean()
  metrics = {'accuracy': acc}
  for cls in [-1, 0, 1]:
    tp = ((y_true == cls) & (y_pred == cls)).sum()
    fp = ((y_true != cls) & (y_pred == cls)).sum()
    fn = ((y_true == cls) & (y_pred != cls)).sum()
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    metrics[f'precision_{cls}'] = prec
    metrics[f'recall_{cls}'] = rec
  return {'accuracy': acc, **{k: v for k, v in locals().items() if k.startswith('precision_') or k.startswith('recall_')}}


def correlate_exploratory(train_df, expl_df):
  merged = train_df.merge(expl_df, on='county_id', how='left')
  num_cols = [c for c in merged.columns if merged[c].dtype in ['float64', 'int64']  and c not in ['margin_pp', 'year', 'county_id']]
  if not num_cols:
    return {}
  corrs = merged['margin_pp'].corr(merged[num_cols])
  return dict(corrs)


def main():
  # run the full model pipeline, load data > train > evaluate > correlate
  conn, cur = get_db()
  df = load_data(cur)

  # split data
  train_years = TRAIN_YEARS + VALIDATE_YEARS  # 2012-2022
  train_df = df[df['year'].isin(train_years)]
  test_df = df[df['year'] == TEST_YEAR]
  # train 
  results = train_models(train_df)
  print('results:', results)
  
  # eval
  last_train_year = max(TRAIN_YEARS)
  train_last = train_df[train_df['year'] == max(TRAIN_YEARS)].groupby('county_id')['margin_pp'].mean()
  test_persistence = test_df['county_id'].map(train_last).fillna(test_df['margin_pp'].mean())
  
  # predictions
  ridge = Ridge()
  ridge.fit(train_df[['margin_pp']], train_df['margin_pp'])
  test_ridge = ridge.predict(test_df[['margin_pp']])
  rf = RandomForestClassifier(n_estimators=100, random_state=42)
  y_train_sign = train_df['margin_pp'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
  rf.fit(train_df[['margin_pp']], train_df['margin_pp'].apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)))
  test_rf_sign = rf.predict(test_df[['margin_pp']])

  # test
  y_test_reg = test_df['margin_pp']
  y_test_clf = test_df['margin_pp'].apply(lambda x: 1 if x > 0 else (-1 if x
< 0 else 0))
 
  #eval
  print('Persistence (reg):', compute_regression_metrics(y_test_reg,
test_df['county_id'].map( train_df[train_df['year'] ==
max(TRAIN_YEARS)].groupby('county_id')['margin_pp'].mean()  ).fillna(test_df['margin_pp'].mean())))
  print('Ridge (reg):', compute_regression_metrics(test_df['margin_pp'],
ridge.predict(test_df[['margin_pp']])))
  print('RF Sign (clf):', compute_classification_metrics(  y_test_clf, rf.predict(test_df[['margin_pp']])))

  print('generating 2026 predictions...')
  preds = predict_2026(cur, {'ridge': ridge, 'rf': rf})
  print('2026 Predictions (first 10):')
  print(preds.head(10).to_string())
  preds.to_csv(config.ROOT / 'report' / 'predictions_2026.csv', index=False)
  print('saved to report/predictions_2026.csv')

  preds = pd.read_csv('report/predictions_2026.csv')
  cur.execute('SELECT county_id, county_name FROM dim_county')
  county_map = {r[0]: r[1] for r in cur.fetchall()}
  preds['county_name'] = preds['county_id'].map(county_map)
  print(preds.to_string())

  cur.close()
  conn.close()
  print("DONE")

if __name__ == '__main__':
  main()
