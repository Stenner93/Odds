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

# Pre-beregn h2h.csv korrekte gæt til supplement (Colab-data er mere komplet end weekly_matches)
_h2h_correct: dict = {}       # {season: {player: total_correct}}
_h2h_round_correct: dict = {} # {season: {round: {player: correct}}}
import pandas as _pd_supp
_H2H_CSV_PATH = os.path.join(DATA_DIR, 'h2h.csv')
if os.path.exists(_H2H_CSV_PATH):
    try:
        _df_supp = _pd_supp.read_csv(_H2H_CSV_PATH)
        _df_supp['season'] = _df_supp['season'].astype(int)
        _df_supp['round']  = _df_supp['round'].astype(int)
        for _, _hr in _df_supp.iterrows():
            _s = int(_hr['season'])
            _r = int(_hr['round'])
            _h2h_correct.setdefault(_s, {})
            _h2h_round_correct.setdefault(_s, {}).setdefault(_r, {})
            if _pd_supp.notna(_hr.get('correct_a')):
                _pa = _hr['player_a']
                _ca = int(_hr['correct_a'])
                _h2h_correct[_s][_pa] = _h2h_correct[_s].get(_pa, 0) + _ca
                _h2h_round_correct[_s][_r][_pa] = _ca
            if _pd_supp.notna(_hr.get('correct_b')):
                _pb = _hr['player_b']
                _cb = int(_hr['correct_b'])
                _h2h_correct[_s][_pb] = _h2h_correct[_s].get(_pb, 0) + _cb
                _h2h_round_correct[_s][_r][_pb] = _cb
        print(f'✓ h2h supplement: {sum(len(v) for v in _h2h_correct.values())} spillere på tværs af sæsoner')
    except Exception as _e:
        print(f'⚠ h2h supplement fejl: {_e}')

# Supplement-kode indsættes i notebook-cellen ved de rette markører.
# Bruger max(h2h, predictions) per runde → sikrer at heatmap, pts_per_round
# og standings alle er konsistente og inkluderer Colab-data for R1-14.

_SUPP_COMBINED = """
# Supplement pts_per_round + standings_by_season:
# brug max(h2h.csv, predictions) per runde — Colab-data dækker R1-14, predictions R9-16.
if '_h2h_round_correct' in dir():
    for _szn in list(pts_per_round.keys()):
        _s_int = int(str(_szn))
        _rnd_map = _h2h_round_correct.get(_s_int, {})
        if not _rnd_map:
            continue
        _rounds_list = pts_per_round[_szn]['rounds']
        for _p in list(pts_per_round[_szn]['data'].keys()):
            _old = pts_per_round[_szn]['data'][_p]
            _new = []
            _running = 0
            _prev = 0
            for _i, _r in enumerate(_rounds_list):
                _h = _rnd_map.get(_r, {}).get(_p)
                _old_incr = _old[_i] - _prev
                _running += max(_h, _old_incr) if _h is not None else _old_incr
                _new.append(int(_running))
                _prev = _old[_i]
            pts_per_round[_szn]['data'][_p] = _new
    # standings_by_season total = slutsum fra pts_per_round (garanterer konsistens)
    for _szn in list(standings_by_season.keys()):
        for _rec in standings_by_season[_szn]:
            _p = _rec['player']
            _series = pts_per_round[_szn]['data'].get(_p)
            if _series:
                _total = _series[-1]
                if _total > _rec.get('points', 0):
                    _rec['points'] = _total
"""

_SUPP_HEATMAP = """
# Supplement heatmap_s4: brug max(h2h.csv, predictions) per runde
if '_h2h_round_correct' in dir():
    _h2h_s4_rnd = _h2h_round_correct.get(CURRENT_SEASON, {})
    for _p in list(heatmap_s4.keys()):
        for _r, _rmap in _h2h_s4_rnd.items():
            if _p in _rmap:
                _r_str = str(int(_r))
                if _r_str in heatmap_s4[_p]:
                    if _rmap[_p] > heatmap_s4[_p][_r_str].get('pts', 0):
                        heatmap_s4[_p][_r_str]['pts'] = _rmap[_p]
"""

_SUPP_HIST_COMPARE = """
# Supplement hist_compare: brug pts_per_round slutsum per spiller per sæson
if '_h2h_round_correct' in dir():
    for _szn in list(pts_per_round.keys()):
        _s_str = str(_szn)
        for _p, _series in pts_per_round[_szn]['data'].items():
            if _series and _p in hist_compare:
                _total = _series[-1]
                if _total > int(hist_compare[_p].get(_s_str, 0)):
                    hist_compare[_p][_s_str] = _total
"""

# Fix: pandas >= 2.0 tillader ikke at sætte int i bool-kolonne — konvertér til int
_cell_to_run = _cell_to_run.replace(
    "all_merged.loc[_all_mask & all_merged['bet'].notna(), 'correct'] = 1\n",
    "all_merged['correct'] = all_merged['correct'].astype(int)\n"
    "all_merged.loc[_all_mask & all_merged['bet'].notna(), 'correct'] = 1\n"
).replace(
    "all_merged.loc[_all_mask & all_merged['bet'].isna(),  'correct'] = 0",
    "all_merged.loc[_all_mask & all_merged['bet'].isna(),  'correct'] = 0"
)

# Indsæt supplement-kode ved de rigtige markører
_MARKERS = [
    ('# ── Active players',          _SUPP_COMBINED),
    ('# ── Historisk sammenligning', _SUPP_HEATMAP),
    ('# ── Player stats',            _SUPP_HIST_COMPARE),
]
for _marker, _code in _MARKERS:
    if _marker in _cell_to_run:
        _cell_to_run = _cell_to_run.replace(_marker, _code + '\n' + _marker, 1)

# Kør i et namespace der har adgang til alle globale variabler
_ns = {k: v for k, v in globals().items()}
_ns['_h2h_correct']       = _h2h_correct
_ns['_h2h_round_correct'] = _h2h_round_correct
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
