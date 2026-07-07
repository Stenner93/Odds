#!/usr/bin/env python3
"""
04_results.py — Henter kampresultater fra TheSportsDB og numbertwenty.io.
Kilde 1: thesportsdb.com (gratis nøgle '123') — søger på engelske holdnavne
Kilde 2: numbertwenty.io predict_grouped (Status=FT) — fuzzy match på holdnavne
"""
import os, sys, time, json
import pandas as pd
import requests
from rapidfuzz import process, fuzz
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
    plain = unidecode(name)
    return _DAN_TO_ENG.get(plain, name)

def _norm(s: str) -> str:
    return unidecode(str(s)).lower().strip().replace(' ','').replace('-','').replace('.','')

def _score_to_1x2(home_score, away_score):
    try:
        h, a = int(home_score), int(away_score)
        if h > a:  return '1'
        if h == a: return 'X'
        return '2'
    except (TypeError, ValueError):
        return None

# ── Kilde 1: TheSportsDB ─────────────────────────────────────────────────

def _sdb_fetch(endpoint):
    url = f'{SPORTSDB_BASE}/{endpoint}'
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f'  ⚠ SportsDB fejl: {e}')
        return None

def _sportsdb_result(home, away, date_str):
    home_en, away_en = _to_english(home), _to_english(away)
    # Prøv ALLE kombinationer af dansk+engelsk navn i begge retninger.
    # Vigtigt for fx USA: kilden bruger "USA", men elo_name er "United States",
    # så kombinationen "USA vs Belgium" skal også prøves.
    homes = list(dict.fromkeys([home_en, home]))
    aways = list(dict.fromkeys([away_en, away]))
    name_pairs = []
    for _h in homes:
        for _a in aways:
            name_pairs.append((_h, _a, False))   # direkte
            name_pairs.append((_a, _h, True))    # ombyttet
    seen = set()
    for h, a, swapped in name_pairs:
        key = (h, a)
        if key in seen:
            continue
        seen.add(key)
        event_title = f"{h.replace(' ','_')}_vs_{a.replace(' ','_')}"
        data = _sdb_fetch(f'searchevents.php?e={event_title}&d={date_str}')
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

# ── Kilde 2: numbertwenty.io ──────────────────────────────────────────────

_n20_cache: dict = {}

def _n20_fetch(date_str: str) -> list:
    if date_str in _n20_cache:
        return _n20_cache[date_str]
    try:
        r = requests.get(
            f'https://numbertwenty.io/predict_grouped?date={date_str}&tz_offset=0',
            timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            _n20_cache[date_str] = []
            return []
        raw = r.json()
        items = raw if isinstance(raw, list) else raw.get('matches', [])
        finished = []
        for item in items:
            status = str(item.get('Status') or item.get('status') or '').upper()
            if status not in ('FT', 'PEN', 'AET'):
                continue
            if item.get('Is_Future') or item.get('is_future'):
                continue
            gf = next((item[k] for k in ['GF','gf','HomeGoals'] if k in item and item[k] is not None), None)
            ga = next((item[k] for k in ['GA','ga','AwayGoals'] if k in item and item[k] is not None), None)
            res = _score_to_1x2(gf, ga)
            if not res:
                continue
            team = str(item.get('Team') or item.get('home_team') or '').strip()
            opp  = str(item.get('Opponent') or item.get('away_team') or '').strip()
            if team:
                finished.append({'home': team, 'away': opp, 'result': res})
        _n20_cache[date_str] = finished
        return finished
    except Exception as e:
        print(f'  ⚠ N20 fejl ({date_str}): {e}')
        _n20_cache[date_str] = []
        return []

def _n20_result(home, away, date_str: str):
    matches = _n20_fetch(date_str)
    if not matches:
        return None
    # Prøv både dansk og engelsk navnevariant (fx USA / United States)
    home_vars = list(dict.fromkeys([_norm(_to_english(home)), _norm(home)]))
    away_vars = list(dict.fromkeys([_norm(_to_english(away)), _norm(away)]))
    all_homes = [_norm(m['home']) for m in matches]
    all_aways = [_norm(m['away']) for m in matches]

    def _pick(home_list, away_list, invert):
        for hv in home_list:
            best = process.extractOne(hv, all_homes, scorer=fuzz.token_sort_ratio)
            if not best or best[1] < 75:
                continue
            for m in [mm for mm in matches if _norm(mm['home']) == all_homes[best[2]]]:
                if any(fuzz.token_sort_ratio(av, _norm(m['away'])) >= 75 for av in away_list):
                    return {'1':'2','2':'1','X':'X'}[m['result']] if invert else m['result']
        return None

    # Direkte (home som hjemmehold) — ellers ombyttet (home optræder som udehold)
    return _pick(home_vars, away_vars, False) or _pick(away_vars, home_vars, True)

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
    source = 'SportsDB'
    if not result:
        result = _n20_result(home, away, date)
        source = 'N20'

    if result:
        auto_results[mn] = result
        print(f'  ✅ #{mn:>2}: {home} vs {away} — {result} ({source})')
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

