#!/usr/bin/env python3
"""
05_standings.py — Beregner point og stilling fra predictions.csv + weekly_matches.csv.
Skriver til points.csv, h2h.csv og standings.csv.
"""
import os, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    CURRENT_SEASON, MATCHES_CSV, PREDICTIONS_CSV,
    POINTS_CSV, H2H_CSV, STANDINGS_CSV,
    H2H_ORDER_FILE, H2H_WIN, H2H_DRAW, H2H_LOSS,
    _norm_bet, get_current_round
)

CURRENT_ROUND = get_current_round()

# ── Indlæs data ──────────────────────────────────────────────────────────
df_matches = pd.read_csv(MATCHES_CSV)
df_matches['season'] = df_matches['season'].astype(int)
df_matches['round']  = df_matches['round'].astype(int)

df_preds = pd.read_csv(PREDICTIONS_CSV)
df_preds['season'] = df_preds['season'].astype(int)
df_preds['round']  = df_preds['round'].astype(int)
df_preds['bet']    = df_preds['bet'].apply(_norm_bet)

# ── Find færdige runder (alle kampe har resultat) ─────────────────────────
df_s = df_matches[df_matches['season'] == CURRENT_SEASON].copy()
total_per_round    = df_s.groupby('round')['match_code'].count()
completed_per_round = (
    df_s[df_s['result'].notna()]
    .groupby('round')['match_code'].count()
    .reindex(total_per_round.index, fill_value=0)
)
complete_rounds = [
    r for r in total_per_round.index
    if completed_per_round.get(r, 0) >= total_per_round[r]
]

# ── Beregn rigtige gæt (løbende — alle runder med mindst ét resultat) ────
df_res = df_matches[
    (df_matches['season'] == CURRENT_SEASON) &
    df_matches['result'].notna()
].copy()

df_m = df_preds[df_preds['season'] == CURRENT_SEASON].merge(
    df_res[['round', 'match_code', 'result']].rename(columns={'result': 'actual'}),
    on=['round', 'match_code'],
    how='inner'
)
df_m['correct'] = (df_m['bet'].notna() & (df_m['bet'] == df_m['actual'])).astype(int)

# ── Gem points.csv ────────────────────────────────────────────────────────
df_pts_out = df_m[['season', 'round', 'match_code', 'player', 'bet', 'actual', 'correct']].rename(
    columns={'actual': 'result'}
)
if os.path.exists(POINTS_CSV):
    try:
        df_ex = pd.read_csv(POINTS_CSV)
        df_ex['season'] = df_ex['season'].astype(int)
        df_pts_out = pd.concat(
            [df_ex[df_ex['season'] != CURRENT_SEASON], df_pts_out],
            ignore_index=True
        )
    except Exception as e:
        print(f'⚠ Kunne ikke læse points.csv: {e}')
df_pts_out.to_csv(POINTS_CSV, index=False)
print(f'✓ points.csv: {len(df_pts_out)} rækker')

# ── H2H-beregning via h2h_order.txt ──────────────────────────────────────
if not os.path.exists(H2H_ORDER_FILE):
    print(f'⚠ {H2H_ORDER_FILE} ikke fundet — springer H2H over')
    sys.exit(0)

with open(H2H_ORDER_FILE, encoding='utf-8') as f:
    players_ordered = [l.strip() for l in f if l.strip() and not l.startswith('#')]

if len(players_ordered) < 2:
    print('⚠ For få spillere i h2h_order.txt')
    sys.exit(0)

pairs = [
    (players_ordered[i], players_ordered[i + 1])
    for i in range(0, len(players_ordered) - 1, 2)
]

h2h_rows = []
for round_num in sorted(complete_rounds):
    round_preds = df_m[df_m['round'] == round_num]
    player_correct = round_preds.groupby('player')['correct'].sum().to_dict()

    for player_a, player_b in pairs:
        ca = int(player_correct.get(player_a, 0))
        cb = int(player_correct.get(player_b, 0))
        if ca > cb:
            pts_a, pts_b = H2H_WIN, H2H_LOSS
        elif ca < cb:
            pts_a, pts_b = H2H_LOSS, H2H_WIN
        else:
            pts_a, pts_b = H2H_DRAW, H2H_DRAW
        h2h_rows.append({
            'season':    CURRENT_SEASON,
            'round':     round_num,
            'player_a':  player_a,
            'player_b':  player_b,
            'correct_a': ca,
            'correct_b': cb,
            'h2h_pts_a': pts_a,
            'h2h_pts_b': pts_b,
        })

df_h2h_new = pd.DataFrame(h2h_rows)

# Bevar historiske sæsoner i h2h.csv
if os.path.exists(H2H_CSV):
    try:
        df_h2h_ex = pd.read_csv(H2H_CSV)
        df_h2h_ex['season'] = df_h2h_ex['season'].astype(int)
        df_h2h_combined = pd.concat(
            [df_h2h_ex[df_h2h_ex['season'] != CURRENT_SEASON], df_h2h_new],
            ignore_index=True
        )
    except Exception as e:
        print(f'⚠ Kunne ikke læse h2h.csv: {e}')
        df_h2h_combined = df_h2h_new
else:
    df_h2h_combined = df_h2h_new

df_h2h_combined.to_csv(H2H_CSV, index=False)
print(f'✓ h2h.csv: {len(df_h2h_combined)} rækker ({len(h2h_rows)} aktuel sæson)')

# ── Stilling ──────────────────────────────────────────────────────────────
df_h2h_s = df_h2h_combined[df_h2h_combined['season'] == CURRENT_SEASON]
ra = df_h2h_s[['player_a', 'correct_a', 'h2h_pts_a']].rename(
    columns={'player_a': 'player', 'correct_a': 'correct', 'h2h_pts_a': 'h2h_pts'})
rb = df_h2h_s[['player_b', 'correct_b', 'h2h_pts_b']].rename(
    columns={'player_b': 'player', 'correct_b': 'correct', 'h2h_pts_b': 'h2h_pts'})
df_flat = pd.concat([ra, rb])

standings = df_flat.groupby('player').agg(
    rounds_played=('correct', 'count'),
    total_correct=('correct', 'sum'),
    total_h2h_pts=('h2h_pts', 'sum'),
).reset_index()
standings['avg_correct'] = (standings['total_correct'] / standings['rounds_played']).round(2)
standings = standings.sort_values(
    ['total_h2h_pts', 'total_correct'], ascending=False
).reset_index(drop=True)
standings.insert(0, 'pos', standings.index + 1)
standings['season'] = CURRENT_SEASON
standings.to_csv(STANDINGS_CSV, index=False)
print(f'✓ standings.csv: {len(standings)} spillere')

print(f'\n✅ Runde {CURRENT_ROUND} status: '
      f'{completed_per_round.get(CURRENT_ROUND, 0)}/{total_per_round.get(CURRENT_ROUND, 0)} kampe færdige')
if CURRENT_ROUND not in complete_rounds:
    print('ℹ️  H2H point tildeles først når alle kampe er spillet')

print('\nStilling:')
print(standings[['pos', 'player', 'total_h2h_pts', 'total_correct', 'rounds_played']].to_string(index=False))
