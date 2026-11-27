"""
Generate charts for the GA election prediction project.
Outputs PNG files to report/charts/
"""
import config, pandas as pd, psycopg2
import matplotlib.pyplot as plt

from pathlib import Path

def get_db():
    import psycopg2, psycopg2.extras
    conn = psycopg2.connect(
        host=config.PG_HOST, port=config.PG_PORT,
        dbname=config.PG_DB, user=config.PG_USER,
        password=config.get_secret("PG_PASSWORD")
    )
    return conn, psycopg2.extras.RealDictCursor(conn)

def chart_state_trend_by_office():
    """State-wide trend by office over time."""
    conn, cur = get_db()
    cur.execute("""
        SELECT de.year, fc.contest,
               ROUND(100.0 * SUM(CASE WHEN fc.party='DEM' THEN fc.vote_count ELSE 0 END)
                     / NULLIF(SUM(CASE WHEN fc.party IN ('DEM','REP') THEN fc.vote_count ELSE 0 END), 0), 2) AS dem_margin
        FROM fact_county_contest fc
        JOIN dim_election de ON fc.election_id = de.election_id
        WHERE de.year IN (2012,2014,2016,2018,2020,2022,2024)
          AND fc.contest ILIKE '%president%'  -- or filter to specific offices
        GROUP BY de.year, fc.contest
        ORDER BY de.year, fc.contest
    """)
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=['year', 'contest', 'dem_margin'])
    cur.close()
    
    if df.empty:
        return
    
    # Handle None values in dem_margin
    df['dem_margin'] = pd.to_numeric(df['dem_margin'], errors='coerce')
    df = df.dropna(subset=['dem_margin'])
    
    if df.empty:
        return
    
    plt.figure(figsize=(10, 6))
    for contest in df['contest'].unique():
        sub = df[df['contest'] == contest]
        plt.plot(sub['year'], sub['dem_margin'], marker='o', label=contest.replace('_', ' '))
    
    plt.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    plt.xlabel('Election Year')
    plt.ylabel('Democratic Margin (pp)')
    plt.title('GA Statewide Trend by Office')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    plt.savefig(config.ROOT / 'report' / 'charts' / 'state_trend_by_office.png', dpi=150)
    plt.close()

def chart_region_lean():
    """Regional lean (urban/suburban/rural) by year."""
    conn, cur = get_db()
    cur.execute("""
        SELECT dc.region, de.year,
               ROUND(100.0 * SUM(CASE WHEN fc.party='DEM' THEN fc.vote_count ELSE 0 END)
                     / NULLIF(SUM(CASE WHEN fc.party IN ('DEM','REP') THEN fc.vote_count ELSE 0 END), 0), 2) AS dem_margin
        FROM fact_county_contest fc
        JOIN dim_county dc ON fc.county_id = dc.county_id
        JOIN dim_election de ON fc.election_id = de.election_id
        WHERE de.year IN (2012,2014,2016,2018,2020,2022,2024)
        GROUP BY dc.region, de.year
        ORDER BY dc.region, de.year
    """)
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=['region', 'year', 'dem_margin'])
    cur.close()
    
    if df.empty:
        return
    
    plt.figure(figsize=(10, 6))
    for region in sorted(df['region'].unique()):
        sub = df[df['region'] == region]
        plt.plot(sub['year'], sub['dem_margin'], marker='o', label=region)
    
    plt.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    plt.xlabel('Election Year')
    plt.ylabel('Democratic Margin (pp)')
    plt.title('Regional Lean by Year')
    plt.legend()
    plt.tight_layout()
    plt.savefig(config.ROOT / 'report' / 'charts' / 'region_lean.png', dpi=150)
    plt.close()

def chart_county_drilldown(county_name):
    # Ensure county name has " County" suffix
    if not county_name.endswith(" County"):
        county_name = county_name + " County"
    """County drill-down: margin over time for a specific county."""
    conn, cur = get_db()
    cur.execute("""
        SELECT de.year, fc.contest,
               ROUND(100.0 * (SUM(CASE WHEN fc.party='DEM' THEN fc.vote_count ELSE 0 END)
                            - SUM(CASE WHEN fc.party='REP' THEN fc.vote_count ELSE 0 END))
                     / NULLIF(SUM(CASE WHEN fc.party IN ('DEM','REP') THEN fc.vote_count ELSE 0 END), 0), 2) AS dem_margin
        FROM fact_county_contest fc
        JOIN dim_election de ON fc.election_id = de.election_id
        JOIN dim_county dc ON fc.county_id = dc.county_id
        WHERE dc.county_name = %s
          AND de.year IN (2012,2014,2016,2018,2020,2022,2024)
        GROUP BY de.year, fc.contest
        ORDER BY de.year, fc.contest
    """, (county_name,))
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=['year', 'contest', 'dem_margin'])
    cur.close()
    
    if df.empty:
        return
    
    # Handle None values in dem_margin
    df['dem_margin'] = pd.to_numeric(df['dem_margin'], errors='coerce')
    df = df.dropna(subset=['dem_margin'])
    
    if df.empty:
        return
    
    plt.figure(figsize=(10, 6))
    for contest in df['contest'].unique():
        sub = df[df['contest'] == contest]
        plt.plot(sub['year'], sub['dem_margin'], marker='o', label=contest.replace('_', ' '))
    
    plt.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
    plt.xlabel('Election Year')
    plt.ylabel('Democratic Margin (pp)')
    plt.title(f'{county_name} County - Margin by Office')
    plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    plt.tight_layout()
    safe_name = county_name.lower().replace(' ', '_')
    plt.savefig(config.ROOT / 'report' / 'charts' / f'county_{safe_name}.png', dpi=150)
    plt.close()

def chart_2026_predictions():
    """Visualize 2026 predictions by county."""
    path = config.ROOT / 'report' / 'predictions_2026.csv'
    if not path.exists():
        return
    df = pd.read_csv(path)
    # Join with county names
    conn, cur = get_db()
    cur.execute('SELECT county_id, county_name FROM dim_county')
    names = dict(cur.fetchall())
    cur.close()
    df['county_name'] = df['county_id'].map(names)
    
    # Scatter: margin vs sign
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    colors = df['predicted_sign_2026'].map({1: 'blue', -1: 'red', 0: 'gray'})
    ax1.scatter(df['county_id'], df['predicted_margin_2026'], c=colors, alpha=0.6)
    ax1.axhline(y=0, color='gray', linestyle='--')
    ax1.set_xlabel('County ID')
    ax1.set_ylabel('Predicted Margin (pp)')
    ax1.set_title('2026 Predicted Margin by County')
    
    # Bar chart of predicted signs
    sign_counts = df['predicted_sign_2026'].value_counts().sort_index()
    labels = {-1: 'Republican', 0: 'Tie', 1: 'Democratic'}
    ax2.bar([labels.get(k, str(k)) for k in sign_counts.index], sign_counts.values,
            color=['red', 'gray', 'blue'])
    ax2.set_ylabel('Number of Counties')
    ax2.set_title('2026 Predicted Winners')
    
    plt.tight_layout()
    plt.savefig(config.ROOT / 'report' / 'charts' / 'predictions_2026.png', dpi=150)
    plt.close()

def main():
    config.ROOT.mkdir(parents=True, exist_ok=True)
    (config.ROOT / 'report' / 'charts').mkdir(parents=True, exist_ok=True)
    
    print("Generating state trend chart...")
    chart_state_trend_by_office()
    
    print("Generating region lean chart...")
    chart_region_lean()
    
    print("Generating 2026 predictions chart...")
    chart_2026_predictions()
    
    # County drill-downs for a few key counties
    key_counties = ['Fulton', 'Gwinnett', 'Cobb', 'DeKalb', 'Chatham']
    for county in key_counties:
        print(f"Generating {county} county drill-down...")
        try:
            chart_county_drilldown(county)
        except Exception as e:
            print(f"  Skipped {county}: {e}")
    
    print("All charts saved to report/charts/")

if __name__ == "__main__":
    main()
