import pandas as pd
# Incumbent swing analysis (presidential elections)
PRESIDENTIAL_INCUMBENTS = {
    '2012NovGen': 'DEM',   # Obama (D) incumbent
    '2016NovGen': 'REP',   # Trump (R) incumbent  
    '2020NovGen': 'REP',   # Trump (R) incumbent
    '2024NovGen': 'DEM',   # Biden (D) incumbent
}

def analyze_incumbent_swing(cur):
    """Compute incumbent vote share swing per county and correlate with economy."""
    from sklearn.linear_model import LinearRegression
    
    # Get presidential election vote shares per county
    cur.execute("""
        SELECT fc.county_id, fc.election_id, de.year, fc.party, fc.vote_count,
               de.name
        FROM fact_county_contest fc
        JOIN dim_election de ON fc.election_id = de.election_id
        WHERE fc.election_id IN %s
          AND fc.contest ILIKE '%%president%%'
        ORDER BY fc.county_id, de.year
    """, (tuple(PRESIDENTIAL_INCUMBENTS.keys()),))
    
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=['county_id', 'election_id', 'year', 'party', 'vote_count', 'election_name'])
    
    # Compute incumbent party vote share per county per election
    rows = []
    for (county_id, election_id), group in df.groupby(['county_id', 'election_id']):
        year = group['year'].iloc[0]
        incumbent_party = PRESIDENTIAL_INCUMBENTS.get(election_id)
        if not incumbent_party:
            continue
        total = group['vote_count'].sum()
        inc_votes = group[group['party'] == incumbent_party]['vote_count'].sum()
        if total > 0:
            inc_share = inc_votes / total
            rows.append({
                'county_id': county_id,
                'election_id': election_id,
                'year': year,
                'incumbent_party': incumbent_party,
                'incumbent_share': inc_share
            })
    
    swing_df = pd.DataFrame(rows)
    
    # Compute swing: share_t - share_{t-1} per county
    swing_df = swing_df.sort_values(['county_id', 'year'])
    swing_df['prev_share'] = swing_df.groupby('county_id')['incumbent_share'].shift(1)
    swing_df['swing'] = swing_df['incumbent_share'] - swing_df['prev_share']
    swing_df = swing_df.dropna(subset=['swing'])
    
    # Join with economy data (unemployment rate at election year)
    # BLS measure 03 = unemployment rate
    cur.execute("""
        SELECT county_id, year, AVG(value) as avg_unemployment
        FROM fact_economy
        WHERE measure = '03'
        GROUP BY county_id, year
    """)
    econ_rows = cur.fetchall()
    econ_df = pd.DataFrame(econ_rows, columns=['county_id', 'year', 'unemployment_rate'])
    
    # Join swing with economy
    swing_econ = swing_df.merge(econ_df, on=['county_id', 'year'], how='left')
    swing_econ['unemployment_change'] = swing_econ.groupby('county_id')['unemployment_rate'].diff()
    
    # Regression: swing ~ unemployment + unemployment_change
    reg_df = swing_econ.dropna(subset=['swing', 'unemployment_rate', 'unemployment_change'])
    if len(reg_df) < 10:
        return {'error': 'Insufficient data for regression'}
    
    X = reg_df[['unemployment_rate', 'unemployment_change']]
    y = reg_df['swing']
    
    model = LinearRegression()
    model.fit(X, y)
    
    return {
        'n_obs': len(reg_df),
        'r2': model.score(X, y),
        'coef_unemployment': model.coef_[0],
        'coef_unemployment_change': model.coef_[1],
        'intercept': model.intercept_,
        'sample_data': reg_df[['county_id', 'year', 'incumbent_party', 'incumbent_share', 'swing', 'unemployment_rate', 'unemployment_change']].to_dict('records')
    }

if __name__ == '__main__':
    import sys
    sys.path.insert(0, 'src')
    import model
    from model import get_db
    conn, cur = get_db()
    result = analyze_incumbent_swing(cur)
    print('Incumbent swing analysis:', result)
    cur.close()
