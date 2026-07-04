#!/usr/bin/env python3
"""
03_bets.py — Parser spillernes gæt fra gaet_input.txt og gemmer til predictions.csv.

Format (tab-separeret, kopieret direkte fra Excel):
  16. runde\t\tHOL-SVE\tALM-MAL\t...
  0\tInga Wamsler\t1\t9\t1\t...
  0\tDennis Sveistrup\t1\t9\t1\t...

Holdforkortelserne i headerlinjen IGNORERES.
Kampene matches på POSITION mod weekly_matches.csv (match_no 1, 2, 3...).
Værdier: 1=hjemmehold, 9=uafgjort(X), 2=udehold, 0=intet gæt.
"""
import os, re, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    CURRENT_SEASON, DATA_DIR, MATCHES_CSV, PREDICTIONS_CSV, H2H_CSV,
    _norm_bet, csv_upsert
)

GAET_INPUT = os.path.join(DATA_DIR, 'gaet_input.txt')

if not os.path.exists(GAET_INPUT):
    print(f'❌ {GAET_INPUT} ikke fundet')
    sys.exit(1)

with open(GAET_INPUT, encoding='utf-8') as f:
    raw = f.read()

# Fjern kommentarlinjer og tomme linjer
lines = [l for l in raw.strip().splitlines()
         if l.strip() and not l.strip().startswith('#')]

if not lines:
    print('❌ Ingen data i gaet_input.txt — indsæt gæt-tabellen fra Excel')
    sys.exit(1)

# ── Parse header: find rundenummer ────────────────────────────────────────
header_parts = lines[0].split('\t')
m = re.search(r'(\d+)', header_parts[0])
if not m:
    print(f'❌ Kan ikke finde rundenummer i: {header_parts[0]!r}')
    print('   Forventet format: "16. runde" eller "Runde 16"')
    sys.exit(1)

round_num = int(m.group(1))
print(f'📋 Runde {round_num} detekteret')

# ── Hent kampe fra weekly_matches.csv (sorteret efter match_no) ──────────
df_matches = pd.read_csv(MATCHES_CSV)
df_matches['season'] = df_matches['season'].astype(int)
df_matches['round']  = df_matches['round'].astype(int)

# ── Afdeling-mapping ──────────────────────────────────────────────────────
# En "N. runde" i headeren er afdeling-relativ (1-17). Vi er i afdeling
# ((max_runde-1)//17 + 1). Mapper afd-relativ runde til global runde, HVIS
# der findes kampe der (ellers beholdes tallet — robust mod begge konventioner).
AFD_SIZE = 17
if round_num <= AFD_SIZE:
    _rounds = set(df_matches[df_matches['season'] == CURRENT_SEASON]['round'])
    _max_r  = max(_rounds) if _rounds else 0
    _base   = ((_max_r - 1) // AFD_SIZE) * AFD_SIZE if _max_r else 0
    _global = _base + round_num
    if _global != round_num and _global in _rounds:
        print(f'   → afdeling {(_max_r - 1)//AFD_SIZE + 1}: runde {round_num} = global runde {_global}')
        round_num = _global

df_rnd = df_matches[
    (df_matches['season'] == CURRENT_SEASON) &
    (df_matches['round']  == round_num)
].sort_values('match_no')

if df_rnd.empty:
    print(f'❌ Ingen kampe for S{CURRENT_SEASON}R{round_num} — kør 01_kampe.py først')
    sys.exit(1)

match_codes = df_rnd['match_code'].tolist()
n_matches   = len(match_codes)

print(f'{n_matches} kampe (position → match_code):')
for i, (_, row) in enumerate(df_rnd.iterrows(), 1):
    print(f'  Plads {i}: {row["home_team"]} vs {row["away_team"]} → {row["match_code"]}')

# ── Parse spillerrækker ───────────────────────────────────────────────────
rows = []
players_seen = []

for line in lines[1:]:
    parts = line.split('\t')
    # Forventet: [score/0, spillernavn, gæt1, gæt2, ...]
    if len(parts) < 3:
        continue
    player = parts[1].strip()
    if not player:
        continue

    guesses = parts[2:]
    player_rows = []
    for i in range(n_matches):
        mc  = match_codes[i]
        raw_val = guesses[i].strip() if i < len(guesses) else '0'
        bet = _norm_bet(raw_val)   # 0 → None (intet gæt)
        player_rows.append({
            'season':     CURRENT_SEASON,
            'round':      round_num,
            'match_code': mc,
            'player':     player,
            'bet':        bet,
        })

    rows.extend(player_rows)
    n_valid = sum(1 for r in player_rows if r['bet'] is not None)
    players_seen.append(player)
    print(f'  {player}: {n_valid}/{n_matches} gæt')

if not rows:
    print('❌ Ingen spillerrækker parsede — tjek format')
    sys.exit(1)

# ── Gem til predictions.csv ───────────────────────────────────────────────
df_new = pd.DataFrame(rows)
df_new['season'] = df_new['season'].astype(int)
df_new['round']  = df_new['round'].astype(int)

csv_upsert(
    path=PREDICTIONS_CSV,
    df_new=df_new,
    key_cols=['season', 'round', 'match_code', 'player'],
    overwrite_if_new_data=True,
)

print(f'\n✅ {len(players_seen)} spillere, {len(rows)} gæt gemt → S{CURRENT_SEASON}R{round_num}')

# ── Dan H2H-parringer fra gæt-rækkefølgen ─────────────────────────────────
# Parringerne er fortløbende par i den rækkefølge spillerne står i input:
# spiller 1 vs 2, 3 vs 4, osv. (samme regel som den oprindelige notebook).
# Point/correct beregnes senere af 05_standings.py når resultaterne kendes.
H2H_COLS = ['season', 'round', 'player_a', 'player_b',
            'correct_a', 'correct_b', 'h2h_pts_a', 'h2h_pts_b', 'outcome_a']

new_pairs = [
    {'season': CURRENT_SEASON, 'round': round_num,
     'player_a': players_seen[i], 'player_b': players_seen[i + 1],
     'correct_a': None, 'correct_b': None,
     'h2h_pts_a': None, 'h2h_pts_b': None, 'outcome_a': None}
    for i in range(0, len(players_seen) - 1, 2)
]

if os.path.exists(H2H_CSV):
    df_h2h = pd.read_csv(H2H_CSV)
    df_h2h['season'] = df_h2h['season'].astype(int)
    df_h2h['round']  = df_h2h['round'].astype(int)
else:
    df_h2h = pd.DataFrame(columns=H2H_COLS)

mask_rnd = (df_h2h['season'] == CURRENT_SEASON) & (df_h2h['round'] == round_num)
existing = df_h2h[mask_rnd]

# Er runden allerede scoret? (mindst én parring har h2h-point)
already_scored = (not existing.empty) and existing['h2h_pts_a'].notna().any()

if already_scored:
    print(f'ℹ H2H: runde {round_num} har allerede point — parringer røres ikke')
else:
    # Opret eller genskab parringer (overskriver kun u-scorede parringer)
    df_h2h = df_h2h[~mask_rnd]
    df_h2h = pd.concat([df_h2h, pd.DataFrame(new_pairs)], ignore_index=True)
    df_h2h = df_h2h[H2H_COLS]
    df_h2h.to_csv(H2H_CSV, index=False)
    verb = 'opdateret' if not existing.empty else 'oprettet'
    print(f'✅ H2H: {len(new_pairs)} parringer {verb} for runde {round_num}')
    for p in new_pairs:
        print(f'   {p["player_a"]}  vs  {p["player_b"]}')
