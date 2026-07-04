#!/usr/bin/env python3
"""
05_standings.py — Beregner point og stilling fra predictions.csv + weekly_matches.csv.

VIGTIG REGEL: Skriptet GENERERER ALDRIG nye H2H-parringer.
h2h.csv er kilden til sandhed for hvem der møder hvem.
Skriptet opdaterer kun correct_a/b og h2h_pts_a/b for allerede-eksisterende parringer.

Nye runders parringer tilføjes manuelt i data/h2h.csv på GitHub.
"""
import os, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    CURRENT_SEASON, MATCHES_CSV, PREDICTIONS_CSV,
    POINTS_CSV, H2H_CSV, STANDINGS_CSV,
    H2H_WIN, H2H_DRAW, H2H_LOSS,
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
total_per_round = df_s.groupby('round')['match_code'].count()
completed_per_round = (
    df_s[df_s['result'].notna()]
    .groupby('round')['match_code'].count()
    .reindex(total_per_round.index, fill_value=0)
)
complete_rounds = set(
    r for r in total_per_round.index
    if completed_per_round.get(r, 0) >= total_per_round[r]
)

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

# ── H2H: læs eksisterende parringer og opdater kun point ─────────────────
# VIGTIGT: h2h.csv er kilden til parringer — vi overskriver dem ALDRIG.
# Parringer for nye runder tilføjes manuelt på GitHub.
if not os.path.exists(H2H_CSV):
    print('⚠ h2h.csv ikke fundet — spring H2H over (tilføj manuelt på GitHub)')
    sys.exit(0)

df_h2h = pd.read_csv(H2H_CSV)
df_h2h['season'] = df_h2h['season'].astype(int)
df_h2h['round']  = df_h2h['round'].astype(int)

# Opdater kun complete runder i aktuel sæson
df_h2h_s = df_h2h[df_h2h['season'] == CURRENT_SEASON]
rounds_with_pairings = set(df_h2h_s['round'].unique())
rounds_to_update = complete_rounds & rounds_with_pairings
rounds_no_pairings = complete_rounds - rounds_with_pairings

if rounds_no_pairings:
    print(f'⚠ Færdige runder uden parringer i h2h.csv: {sorted(rounds_no_pairings)}')
    print('  → Tilføj parringsrækker til data/h2h.csv på GitHub for disse runder')

updated_rounds = 0
for round_num in sorted(rounds_to_update):
    round_preds = df_m[df_m['round'] == round_num]
    player_correct = round_preds.groupby('player')['correct'].sum().to_dict()

    mask = (df_h2h['season'] == CURRENT_SEASON) & (df_h2h['round'] == round_num)
    for idx in df_h2h[mask].index:
        pa = df_h2h.at[idx, 'player_a']
        pb = df_h2h.at[idx, 'player_b']
        ca = int(player_correct.get(pa, 0))
        cb = int(player_correct.get(pb, 0))
        pts_a = H2H_WIN if ca > cb else (H2H_DRAW if ca == cb else H2H_LOSS)
        pts_b = H2H_WIN if cb > ca else (H2H_DRAW if ca == cb else H2H_LOSS)
        df_h2h.at[idx, 'correct_a']  = ca
        df_h2h.at[idx, 'correct_b']  = cb
        df_h2h.at[idx, 'h2h_pts_a'] = pts_a
        df_h2h.at[idx, 'h2h_pts_b'] = pts_b
    updated_rounds += 1

df_h2h.to_csv(H2H_CSV, index=False)
print(f'✓ h2h.csv: {updated_rounds} runder opdateret, {len(rounds_no_pairings)} mangler parringer')

# ── Stilling ──────────────────────────────────────────────────────────────
# Afdeling-nulstilling: en afdeling = 17 runder (fuld round-robin blandt 18
# spillere). Efter runde 17 nulstiller stillingen til afdeling 2 (runde 18-34),
# efter runde 34 til afdeling 3 osv. Selve h2h.csv/points.csv bevarer ALLE
# runder som historik — kun den viste stilling (standings.csv) filtreres.
AFD_SIZE = 17
_max_r  = int(df_matches[df_matches['season'] == CURRENT_SEASON]['round'].max())
CUR_AFD = (_max_r - 1) // AFD_SIZE + 1
_afd_lo = (CUR_AFD - 1) * AFD_SIZE + 1
_afd_hi = CUR_AFD * AFD_SIZE
print(f'ℹ Afdeling {CUR_AFD} (runde {_afd_lo}-{_afd_hi}) — stillingen nulstillet hertil')

df_h2h_s_updated = df_h2h[
    (df_h2h['season'] == CURRENT_SEASON) &
    (df_h2h['round'] >= _afd_lo) & (df_h2h['round'] <= _afd_hi)
]

# Nullstil point KUN for runder der hverken er færdige ELLER har eksisterende point fra Colab.
# Runder med udfyldte h2h_pts (fra Colab) bevares selvom weekly_matches ikke er komplet.
df_h2h_s_updated = df_h2h_s_updated.copy()
mask_incomplete = ~df_h2h_s_updated['round'].isin(complete_rounds)
mask_no_pts     = df_h2h_s_updated['h2h_pts_a'].isna()
df_h2h_s_updated.loc[mask_incomplete & mask_no_pts, ['h2h_pts_a', 'h2h_pts_b']] = 0

ra = df_h2h_s_updated[['player_a', 'correct_a', 'h2h_pts_a']].rename(
    columns={'player_a': 'player', 'correct_a': 'correct', 'h2h_pts_a': 'h2h_pts'})
rb = df_h2h_s_updated[['player_b', 'correct_b', 'h2h_pts_b']].rename(
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

print(f'\n✅ Runde {CURRENT_ROUND}: '
      f'{completed_per_round.get(CURRENT_ROUND, 0)}/{total_per_round.get(CURRENT_ROUND, 0)} kampe færdige')
if CURRENT_ROUND not in complete_rounds:
    print('ℹ️  H2H point tildeles først når alle kampe i runden er spillet')

print('\nStilling:')
print(standings[['pos', 'player', 'total_h2h_pts', 'total_correct', 'rounds_played']].to_string(index=False))
