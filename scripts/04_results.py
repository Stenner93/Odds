#!/usr/bin/env python3
"""
04_results.py — Henter kampresultater fra TheSportsDB og skriver til weekly_matches.csv.
Kilde: thesportsdb.com (gratis API-nøgle '123')
"""
import os, sys, time, json
import pandas as pd
import requests
from unidecode import unidecode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    CURRENT_SEASON, MATCHES_CSV, SPORTSDB_API_KEY, DATA_DIR,
    get_current_round
)

CURRENT_ROUND   = get_current_round()
SPORTSDB_BASE   = f'https://www.thesportsdb.com/api/v1/json/{SPORTSDB_API_KEY}'

# Byg dansk→engelsk navneopslag fra hold_mapping.json
_HOLD_MAP_PATH = os.path.join(DATA_DIR, 'hold_mapping.json')
_DAN_TO_ENG: dict = {}
if os.path.exists(_HOLD_MAP_PATH):
    try:
        with open(_HOLD_MAP_PATH, encoding='utf-8') as _f:
            for _e in json.load(_f):
                n, en = _e.get('name',''), _e.get('elo_name','')
                if n and en and n not in _DAN_TO_ENG:
                    _DAN_TO_ENG[n] = en
    except Exception:
        pass

def _to_english(name: str) -> str:
    if name in _DAN_TO_ENG:
        return _DAN_TO_ENG[name]
    # Prøv uden accenter (f.eks. "Almería" → "Almeria")
    plain = unidecode(name)
    return _DAN_TO_ENG.get(plain, name)

def _sdb_fetch(endpoint):
    url = f'{SPORTSDB_BASE}/{endpoint}'
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f'  ⚠ SportsDB fejl: {e}')
        return None

def _score_to_1x2(home_score, away_score):
    try:
        h, a = int(home_score), int(away_score)
        if h > a:  return '1'
        if h == a: return 'X'
        return '2'
    except (TypeError, ValueError):
        return None

def _sportsdb_result(home, away, date_str):
    home_en, away_en = _to_english(home), _to_english(away)
    # Prøv med engelske navne (for landshold), derefter originale navne (for klubhold)
    name_pairs = [(home_en, away_en, False), (away_en, home_en, True)]
    if (home_en, away_en) != (home, away):
        name_pairs += [(home, away, False), (away, home, True)]
    seen = set()
    for h, a, swapped in name_pairs:
        key = (h, a)
        if key in seen:
            continue
        seen.add(key)
        event_title = f"{h.replace(' ','_')}_vs_{a.replace(' ','_')}"
        endpoint    = f'searchevents.php?e={event_title}&d={date_str}'
        data = _sdb_fetch(endpoint)
        time.sleep(0.3)
        if not data or not data.get('event'):
            continue
        for ev in data['event']:
            _st = str(ev.get('strStatus') or '').strip().lower()
            if _st and _st not in ('match finished', 'ft', 'finished', 'aet', 'pens', 'ap'):
                continue
            result = _score_to_1x2(ev.get('intHomeScore'), ev.get('intAwayScore'))
            if result:
                if swapped:
                    result = {'1': '2', '2': '1', 'X': 'X'}[result]
                return result
    return None

# ── Hoved-loop ────────────────────────────────────────────────────────────
df_matches = pd.read_csv(MATCHES_CSV)
df_matches['season'] = df_matches['season'].astype(int)
df_matches['round']  = df_matches['round'].astype(int)

_cs = str(int(CURRENT_SEASON))
_cr = str(int(CURRENT_ROUND))
df_rnd = df_matches[
    (df_matches['season'].astype(str) == _cs) &
    (df_matches['round'].astype(str)  == _cr)
].copy()

print(f'📊 {len(df_rnd)} kampe — sæson {_cs} runde {_cr}')
if df_rnd.empty:
    print('⚠ Ingen kampe for denne runde — kør 01_kampe.py først')
    sys.exit(0)

print('Henter resultater fra TheSportsDB...')
auto_results = {}
for _, row in df_rnd.sort_values('match_no').iterrows():
    mn   = int(row['match_no'])
    home = str(row['home_team'])
    away = str(row['away_team'])
    date = str(row.get('date', ''))
    existing = row.get('result')

    if pd.notna(existing) and str(existing).strip() not in ('', 'None', 'nan'):
        print(f'  ℹ️  #{mn:>2}: {home} vs {away} — {existing} (allerede gemt)')
        auto_results[mn] = existing
        continue

    result = _sportsdb_result(home, away, date)
    if result:
        auto_results[mn] = result
        print(f'  ✅ #{mn:>2}: {home} vs {away} — {result}')
    else:
        auto_results[mn] = None
        print(f'  ❌ #{mn:>2}: {home} vs {away} — ikke afsluttet endnu')

# Skriv resultater tilbage til weekly_matches.csv
updated = 0
for mn, result in auto_results.items():
    if result:
        mask = (
            (df_matches['season'] == CURRENT_SEASON) &
            (df_matches['round']  == CURRENT_ROUND)  &
            (df_matches['match_no'] == mn)
        )
        existing = df_matches.loc[mask, 'result'].values
        if len(existing) > 0 and (pd.isna(existing[0]) or str(existing[0]).strip() in ('', 'None', 'nan')):
            df_matches.loc[mask, 'result'] = result
            updated += 1

if updated > 0:
    df_matches.to_csv(MATCHES_CSV, index=False)
    print(f'\n✅ {updated} nye resultater skrevet til weekly_matches.csv')
else:
    print('\nℹ Ingen nye resultater at gemme')

found   = sum(1 for v in auto_results.values() if v)
missing = sum(1 for v in auto_results.values() if not v)
print(f'📊 {found} fundet, {missing} mangler')
