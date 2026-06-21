#!/usr/bin/env python3
"""
Standalone dashboard generator — kører celle 08 fra notebooken.
Bruges af GitHub Actions workflow og kan også køres lokalt.

Krav: pip install pandas numpy requests
"""

import os, json, sys

# ── Repo-stier ────────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(REPO_ROOT, 'data')

# ── Sæson-config ──────────────────────────────────────────────────────────
CURRENT_SEASON = 4

# ── CSV-stier (spejler celle c0005 i notebooken) ─────────────────────────
MATCHES_CSV     = os.path.join(DATA_DIR, 'weekly_matches.csv')
PREDICTIONS_CSV = os.path.join(DATA_DIR, 'predictions.csv')
ODDS_CSV        = os.path.join(DATA_DIR, 'odds.csv')
POINTS_CSV      = os.path.join(DATA_DIR, 'points.csv')
H2H_CSV         = os.path.join(DATA_DIR, 'h2h.csv')
STANDINGS_CSV   = os.path.join(DATA_DIR, 'standings.csv')
ELO_CSV         = os.path.join(DATA_DIR, 'elo_history.csv')
HIST_MATCHES    = os.path.join(DATA_DIR, 'hist_matches.csv')
HIST_ODDS       = os.path.join(DATA_DIR, 'hist_odds.csv')
HIST_PREDS      = os.path.join(DATA_DIR, 'hist_predictions.csv')
PLAYER_STATS    = os.path.join(DATA_DIR, 'player_stats.csv')
SOFASCORE_CSV   = os.path.join(DATA_DIR, 'sofascore_data.csv')

H2H_WIN  = 3
H2H_DRAW = 1
H2H_LOSS = 0

def _norm_bet(v):
    if v is None: return None
    try:
        s = str(v).strip()
        if s.lower() in ('nan', 'none', ''): return None
        if s in ('1', '1.0'): return '1'
        if s in ('9', '9.0', 'X', 'x'): return 'X'
        if s in ('2', '2.0'): return '2'
        vi = int(float(s))
        return {1: '1', 9: 'X', 2: '2'}.get(vi)
    except:
        return None

# ── Auto-detect CURRENT_ROUND fra weekly_matches.csv ─────────────────────
import pandas as _pd_setup
try:
    _df_setup = _pd_setup.read_csv(MATCHES_CSV)
    _df_setup['season'] = _df_setup['season'].astype(int)
    _df_setup['round']  = _df_setup['round'].astype(int)
    CURRENT_ROUND = int(_df_setup[_df_setup['season'] == CURRENT_SEASON]['round'].max())
    print(f'Auto-detect: Sæson {CURRENT_SEASON}, Runde {CURRENT_ROUND}')
except Exception as _e:
    print(f'❌ Kunne ikke læse {MATCHES_CSV}: {_e}')
    sys.exit(1)

# ── Hent cell 08 fra notebooken og kør den ───────────────────────────────
NB_PATH = os.path.join(REPO_ROOT, 'fodboldquiz_komplet_fixed_2_3_6_bozzoiro.ipynb')
if not os.path.exists(NB_PATH):
    print(f'❌ Notebook ikke fundet: {NB_PATH}')
    sys.exit(1)

with open(NB_PATH, encoding='utf-8') as _f:
    _nb = json.load(_f)

_cell_src = None
for _cell in _nb['cells']:
    if _cell.get('id') == 'C7N5rowEhBzw':
        _cell_src = ''.join(_cell['source'])
        break

if not _cell_src:
    print('❌ Celle 08 ikke fundet i notebook (id: C7N5rowEhBzw)')
    sys.exit(1)

# Kør kun frem til (men ikke med) GitHub API-push og git-push blokke
_cutoff = '\nif not GITHUB_TOKEN:'
_cell_to_run = _cell_src.split(_cutoff)[0]

# Kør i et namespace der har adgang til alle globale variabler
_ns = {k: v for k, v in globals().items()}
exec(_cell_to_run, _ns)  # html-variablen sættes her

# ── Skriv index.html til repo-roden ──────────────────────────────────────
_html = _ns.get('html')
if not _html:
    print('❌ html-variablen ikke sat efter exec — tjek celle 08')
    sys.exit(1)

OUTPUT_PATH = os.path.join(REPO_ROOT, 'index.html')
with open(OUTPUT_PATH, 'w', encoding='utf-8') as _f_out:
    _f_out.write(_html)

print(f'✅ index.html gemt ({len(_html)//1024} KB) → {OUTPUT_PATH}')
