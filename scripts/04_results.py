#!/usr/bin/env python3
"""
04_results.py — Henter kampresultater (1/X/2 efter 90 min).
Kilde 1: Bzzoiro (sports.bzzoiro.com) — faste hold-ID'er, 90-min-score adskilt
         fra forlænget tid/straffe. Kræver BZZOIRO_TOKEN; springes over uden.
Kilde 2: thesportsdb.com (gratis nøgle '123') — søger på engelske holdnavne
Kilde 3: numbertwenty.io predict_grouped (Status=FT) — fuzzy match på holdnavne
"""
import os, sys, time, json
import pandas as pd
import requests
from rapidfuzz import process, fuzz
from unidecode import unidecode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    CURRENT_SEASON, MATCHES_CSV, SPORTSDB_API_KEY, DATA_DIR, BZZOIRO_TOKEN,
    get_current_round
)
from bzzoiro import Bzzoiro

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

# Lærte feed-navne fra odds-pipelinen (02) — fx "Paris SG" -> "Paris Saint Germain",
# "FC København" -> "FC Copenhagen". Bruges også til resultat-matching, så et hold
# kun skal "læres" ét sted.
_ODDS_ALIASES: dict = {}
try:
    with open(os.path.join(DATA_DIR, 'odds_aliases.json'), encoding='utf-8') as _f:
        _ODDS_ALIASES = json.load(_f)
except Exception:
    pass

def _variants(name: str) -> list:
    """Alle kendte navne for et hold: vores navn, ELO-navn og lært feed-alias."""
    out = [name, _to_english(name), _ODDS_ALIASES.get(name), _ODDS_ALIASES.get(_to_english(name))]
    return list(dict.fromkeys(v for v in out if v))

def _norm(s: str) -> str:
    return unidecode(str(s)).lower().strip().replace(' ','').replace('-','').replace('.','')

def _name_match(a: str, b: str) -> bool:
    """True hvis to normaliserede holdnavne er samme klub.
    Robust mod klub-præfikser/-suffikser: token_sort_ratio ≥ 75 ELLER en klar
    delstreng (fx 'dortmund' i 'borussiadortmund'). _norm fjerner mellemrum, så
    token-baseret fuzzy-match fejler for flerordede klubnavne — 'Borussia
    Dortmund' vs 'Dortmund' giver kun 66.7 < 75 — og delstreng-reglen fanger dem.
    Kravet len ≥ 5 undgår falske match på korte fragmenter."""
    if not a or not b:
        return False
    if fuzz.token_sort_ratio(a, b) >= 75:
        return True
    short, lng = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 5 and short in lng

def _toks(s: str) -> list:
    s = unidecode(str(s)).lower()
    for ch in "-./&'\u200b":
        s = s.replace(ch, ' ')
    return [t for t in s.split() if t]

def _tok_match(a: str, b: str) -> bool:
    """Forkortelses-regler på ord-niveau (det fuzzy-match på sammentrukne navne ikke kan):
    - akronym:   'PSG'      = 'Paris Saint-Germain'   (initialer af alle ord)
    - initialer: 'Paris SG' = 'Paris Saint-Germain'   (fælles første ord + initialer)
    - ord-præfiks: 'Man City' = 'Manchester City'     (samme antal ord, hvert ord et præfiks)
    Reglerne kræver fælles første ord eller fuld initial-match, så fx 'Paris FC' ≠ 'Paris SG'
    og 'Man City' ≠ 'Man United'."""
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return False
    if len(ta) > len(tb):
        ta, tb = tb, ta
    if len(ta) == 1 and 2 <= len(ta[0]) <= 4 and len(tb) >= 2 and ta[0] == ''.join(t[0] for t in tb):
        return True
    # kort klubnavn = første ord i det lange: 'PSV' = 'PSV Eindhoven', 'AIK' = 'AIK Fotboll'
    # (præcis 3 bogstaver og ikke en generisk præfiks som FC/AFC, så 'Real' ≠ 'Real Madrid')
    if len(ta) == 1 and len(ta[0]) == 3 and ta[0] not in ('afc', 'cfc', 'sfc', 'ssc', 'vfb', 'vfl', 'tsv', 'man')\
            and len(tb) >= 2 and ta[0] == tb[0]:
        return True
    if len(ta) >= 2 and ta[0] == tb[0] and len(ta[0]) >= 3 and len(tb) > len(ta) - 1 \
            and ''.join(ta[1:]) == ''.join(t[0] for t in tb[1:]):
        return True
    if len(ta) == len(tb) and all(x == y or (len(x) >= 3 and y.startswith(x)) or (len(y) >= 3 and x.startswith(y))
                                  for x, y in zip(ta, tb)):
        return True
    return False

def _team_match(a: str, b: str) -> bool:
    """Er to rå holdnavne samme klub? Kombinerer fuzzy/delstreng (_name_match) og
    forkortelses-reglerne (_tok_match)."""
    return _name_match(_norm(a), _norm(b)) or _tok_match(a, b)

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
    # Prøv ALLE kombinationer af kendte navne (dansk, ELO-navn, lært alias) i begge
    # retninger. Vigtigt for fx USA ("USA" vs "United States") og PSG ("Paris SG"
    # vs "Paris Saint Germain").
    homes = _variants(home)
    aways = _variants(away)
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
            # Puljen afgøres efter 90 min. Forlænget spilletid/straffe spilles kun når
            # det står lige efter 90 min, så AET/straffe = X (slutscoren inkl.
            # forlænget spilletid må IKKE bruges — fx VM-finalen 1-0 AET er X).
            if _st in ('aet', 'pens', 'ap'):
                result = 'X'
            else:
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
            # AET/PEN = uafgjort efter 90 min (se SportsDB-kommentaren ovenfor)
            res = 'X' if status in ('PEN', 'AET') else _score_to_1x2(gf, ga)
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
    home_vars, away_vars = _variants(home), _variants(away)
    def _pick(home_list, away_list, invert):
        # Iterér over datoens kampe og kræv match på BÅDE hjemme- og udehold.
        for m in matches:
            if any(_team_match(hv, m['home']) for hv in home_list) and \
               any(_team_match(av, m['away']) for av in away_list):
                return {'1':'2','2':'1','X':'X'}[m['result']] if invert else m['result']
        return None

    # Direkte (home som hjemmehold) — ellers ombyttet (home optræder som udehold)
    return _pick(home_vars, away_vars, False) or _pick(away_vars, home_vars, True)

def _n20_candidates(home, away, date_str: str) -> list:
    """Diagnostik: N20-kampe på datoen hvor mindst ét ord går igen fra et af holdene."""
    words = {t for n in _variants(home) + _variants(away) for t in _toks(n) if len(t) >= 4}
    out = []
    for m in _n20_fetch(date_str):
        if words & set(_toks(m['home']) + _toks(m['away'])):
            out.append(f"{m['home']} v {m['away']} ({m['result']})")
    return out[:6]

# ── Hoved-loop ────────────────────────────────────────────────────────────
import datetime as _dt
df_matches = pd.read_csv(MATCHES_CSV)
df_matches['season'] = df_matches['season'].astype(int)
df_matches['round']  = df_matches['round'].astype(int)

_cs = int(CURRENT_SEASON)
_cr = int(CURRENT_ROUND)

def _has_result(v):
    return pd.notna(v) and str(v).strip() not in ('', 'None', 'nan')

# Kampe der tjekkes = den aktuelle runde PLUS "efternølere": kampe i tidligere
# runder der stadig mangler resultat, men er spillet inden for de sidste
# LOOKBACK_DAYS dage. Uden dette hentes en tidligere rundes sene kampe ALDRIG,
# når en ny runde er scrapet ind (så CURRENT_ROUND = max-runde er rykket videre).
# Fx blev ITA-BEL (runde 31, spillet 25/9) forældreløs da runde 32 kom ind.
LOOKBACK_DAYS = 14
_today = _dt.date.today()

def _recent_undecided(row):
    if int(row['round']) == _cr or _has_result(row.get('result')):
        return False
    try:
        md = _dt.date.fromisoformat(str(row.get('date', '')).strip()[:10])
    except Exception:
        return False
    return 0 <= (_today - md).days <= LOOKBACK_DAYS

_cur_mask    = (df_matches['season'] == _cs) & (df_matches['round'] == _cr)
_orphan_mask = (df_matches['season'] == _cs) & df_matches.apply(_recent_undecided, axis=1)
df_rnd = df_matches[_cur_mask | _orphan_mask].copy()

_n_orphan = int(_orphan_mask.sum())
print(f'📊 {len(df_rnd)} kampe — sæson {_cs} runde {_cr}'
      + (f' (+ {_n_orphan} efternølere fra tidligere runder)' if _n_orphan else ''))
if df_rnd.empty:
    print('⚠ Ingen kampe for denne runde — kør 01_kampe.py først')
    sys.exit(0)

_bzz = Bzzoiro(BZZOIRO_TOKEN, variants=_variants)
if not _bzz.enabled:
    print('  ℹ Bzzoiro sprunget over (ingen BZZOIRO_TOKEN) — bruger SportsDB/N20')

auto_results = {}   # (runde, match_no) -> resultat
for _, row in df_rnd.sort_values(['round', 'match_no']).iterrows():
    rnd  = int(row['round'])
    mn   = int(row['match_no'])
    home = str(row['home_team'])
    away = str(row['away_team'])
    date = str(row.get('date', ''))
    existing = row.get('result')
    tag = f'R{rnd} #{mn:>2}'

    if _has_result(existing):
        print(f'  ℹ️  {tag}: {home} vs {away} — {existing} (allerede gemt)')
        auto_results[(rnd, mn)] = existing
        continue

    result = _bzz.result(home, away, date) if _bzz.enabled else None
    source = 'Bzzoiro'
    if not result:
        result = _sportsdb_result(home, away, date)
        source = 'SportsDB'
    if not result:
        result = _n20_result(home, away, date)
        source = 'N20'

    if result:
        auto_results[(rnd, mn)] = result
        print(f'  ✅ {tag}: {home} vs {away} — {result} ({source})')
    else:
        auto_results[(rnd, mn)] = None
        print(f'  ❌ {tag}: {home} vs {away} — ikke afsluttet endnu')
        # Diagnostik for kampe der burde være spillet: vis hvad N20 havde på datoen,
        # så et navne-mismatch kan ses direkte i loggen.
        try:
            if _dt.date.fromisoformat(date[:10]) < _today:
                _c = _n20_candidates(home, away, date)
                if _c:
                    print(f'      ↳ N20 havde på {date[:10]}: ' + ' | '.join(_c))
        except Exception:
            pass

# Skriv resultater tilbage til weekly_matches.csv (nøgle: runde + match_no)
updated = 0
for (rnd, mn), result in auto_results.items():
    if result:
        mask = (
            (df_matches['season'] == _cs) &
            (df_matches['round']  == rnd)  &
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

