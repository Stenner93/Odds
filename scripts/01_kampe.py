#!/usr/bin/env python3
"""
01_kampe.py — Henter kampdata fra Cognito Forms eller kupon_input.txt
og gemmer til weekly_matches.csv.
"""
import asyncio, json, os, re, sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    CURRENT_SEASON, DATA_DIR, MATCHES_CSV, KUPON_INPUT,
    csv_upsert
)

COGNITO_URL = "https://www.cognitoforms.com/Fodboldquiz1/N%C3%86STEKUPON"
HM_PATH = os.path.join(DATA_DIR, 'hold_mapping.json')

# ── Cognito-scraping (kræver playwright) ─────────────────────────────────
async def _scrape_cognito():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(COGNITO_URL, wait_until='networkidle', timeout=30000)
        await page.wait_for_timeout(4000)
        tekst = await page.inner_text('body')
        await browser.close()
    return tekst

def _fetch_cognito():
    try:
        tekst = asyncio.run(_scrape_cognito())
        if any(x in tekst for x in ["endnu ikke åben", "for tidligt", "for sent"]):
            print("⚠️  Formularen er ikke åben endnu")
            return None
        print(f"✅ Kampdata hentet fra Cognito ({len(tekst)} tegn)")
        return tekst
    except ImportError:
        print("⚠️  playwright ikke installeret — bruger kupon_input.txt")
        return None
    except Exception as e:
        print(f"⚠️  Cognito fejl: {e}")
        return None

def _read_kupon_input():
    if not os.path.exists(KUPON_INPUT):
        return None
    with open(KUPON_INPUT, encoding='utf-8') as f:
        lines = [l for l in f if not l.startswith('#')]
    text = '\n'.join(lines).strip()
    if not text:
        return None
    print(f"✅ Bruger kupon_input.txt ({len(text)} tegn)")
    return text

# ── hold_mapping.json ─────────────────────────────────────────────────────
_NAME_TO_ABBR = {}
if os.path.exists(HM_PATH):
    try:
        with open(HM_PATH, encoding='utf-8') as f:
            _raw_hm = json.load(f)
        for entry in _raw_hm:
            n = str(entry.get('name', '')).strip().lower()
            a = str(entry.get('abbr', '')).strip()
            e = str(entry.get('elo_name', '')).strip().lower()
            if n and a:
                _NAME_TO_ABBR[n] = a
            if e and a and e not in _NAME_TO_ABBR:
                _NAME_TO_ABBR[e] = a
        _EXTRA = {
            'athletic club bilbao': 'BIL', 'athletic club': 'BIL',
            'celta de vigo': 'VIG', 'celta': 'VIG', 'rayo vallecano': 'VAL',
            'ifk göteborg': 'GÖT', 'ifk goteborg': 'GÖT', 'esbjerg fb': 'EfB',
            'lokomotive leipzig': 'LEI', 'rw essen': 'RWE', 'würzburger kickers': 'WÜK',
        }
        _NAME_TO_ABBR.update({k: v for k, v in _EXTRA.items() if k not in _NAME_TO_ABBR})
        print(f'hold_mapping.json: {len(_NAME_TO_ABBR)} hold')
    except Exception as e:
        print(f'⚠ hold_mapping.json fejl: {e}')
else:
    print('⚠ hold_mapping.json ikke fundet — bruger fallback-forkortelser')

_ABBR_FALLBACK_LOG = []

def _abbr(name):
    import unicodedata as _ud
    key = str(name).strip().lower()
    if key in _NAME_TO_ABBR:
        return _NAME_TO_ABBR[key]
    key_asc = _ud.normalize('NFKD', key).encode('ascii', 'ignore').decode()
    if key_asc in _NAME_TO_ABBR:
        return _NAME_TO_ABBR[key_asc]
    _SKIP = {'fc','sc','ac','as','ss','vfb','vfl','vfw','spvgg','bsc',
             'fk','sk','ik','if','bk','hb','cd','ud','cf','rc'}
    parts = key.split()
    sig = [p for p in parts if p not in _SKIP] or parts
    _used = set(_NAME_TO_ABBR.values())
    candidates = []
    if len(sig) >= 1: candidates.append(sig[0][:3].upper())
    if len(sig) >= 2:
        candidates.append(sig[1][:3].upper())
        candidates.append((sig[0][:2]+sig[1][:1]).upper())
        candidates.append((sig[0][:1]+sig[1][:2]).upper())
    candidates.append(''.join(key.split())[:3].upper())
    if len(sig) >= 3: candidates.append(sig[2][:3].upper())
    result = next((c for c in candidates if c and c not in _used), None)
    if result is None:
        base = candidates[0] if candidates else name[:3].upper()
        for n in range(2, 20):
            attempt = (base[:2] + str(n)).upper()
            if attempt not in _used:
                result = attempt
                break
        if result is None:
            result = candidates[0] if candidates else name[:3].upper()
    _NAME_TO_ABBR[key] = result
    if name not in [x[0] for x in _ABBR_FALLBACK_LOG]:
        _ABBR_FALLBACK_LOG.append((name, result))
    return result

def _make_code(home, away):
    return f"{_abbr(home)}-{_abbr(away)}"

_LEAGUE_NORM = {
    'premier league': 'Premier League', 'bundesliga': 'Bundesliga',
    'serie a': 'Serie A', 'la liga': 'La Liga', 'ligue 1': 'Ligue 1',
    'liga portugal': 'Liga Portugal', 'eredivisie': 'Eredivisie',
    'superliga': 'Superligaen', 'superligaen': 'Superligaen',
    'champions league': 'Champions League', 'europa league': 'Europa League',
    'conference league': 'Conference League', 'nations league': 'Nations League',
    'fa cup': 'FA Cup', 'copa del rey': 'Copa del Rey',
    'dbu pokalen': 'DBU Pokalen', 'dbu pokal': 'DBU Pokalen',
    'efl cup': 'EFL Cup', 'championship': 'Championship',
    'superettan': 'Superettan', 'allsvenskan': 'Allsvenskan',
    'veikkausliiga': 'Veikkausliiga', 'obos': 'OBOS-ligaen',
    'meistriliiga': 'Meistriliiga', 'eliteserien': 'Eliteserien',
}

def _norm_league(raw):
    if not raw: return 'Ukendt'
    key = raw.lower().strip()
    for k, v in _LEAGUE_NORM.items():
        if k in key: return v
    return raw.strip()

# ── Parser ────────────────────────────────────────────────────────────────
def _is_date(l): return bool(re.match(r'\d{2}\.\d{2}\.\d{2}', l))
def _is_tv(l):   return bool(re.match(r'TV:', l, re.I))
def _is_1x2(l):  return bool(re.match(r'^[1X2]$', l.strip(), re.I))

def parse_matches(text):
    lines = [l.rstrip() for l in text.splitlines()]
    date_indices = [i for i, l in enumerate(lines) if _is_date(l.strip())]
    if not date_indices:
        return []
    date_indices.append(len(lines))
    results = []
    for start, end in zip(date_indices, date_indices[1:]):
        block = [l.strip() for l in lines[start:end]
                 if l.strip() and not _is_tv(l.strip()) and not _is_1x2(l.strip())]
        date_str = time_str = league_raw = home_raw = away_raw = None
        for line in block:
            if _is_date(line):
                m = re.search(r'(\d{2})\.(\d{2})\.(\d{2,4})', line)
                if m:
                    d, mo, y = m.group(1), m.group(2), m.group(3)
                    date_str = f'20{y}-{mo}-{d}' if len(y) == 2 else f'{y}-{mo}-{d}'
                m2 = re.search(r'\b(\d{1,2}:\d{2})\b', line)
                if m2: time_str = m2.group(1)
                continue
            if re.match(r'^(på|i )\s+', line, re.I): continue
            if re.search(r'.+\s+-\s+.+', line) and not _is_date(line):
                if not re.match(r'^\d+\.?\s+runde', line, re.I):
                    m = re.match(r'^(.+?)\s+-\s+(.+)$', line)
                    if m and home_raw is None:
                        home_candidate = m.group(1).strip()
                        away_candidate = m.group(2).strip()
                        # Skip turneringstrin-beskrivelser der også har bindestreg,
                        # fx "VM - Kvartfinale", "EM - Semifinale", "VM - 16. delsfinale".
                        # Rigtige holdnavne starter aldrig med et ciffer eller et
                        # trin-ord, og hjemmesiden er aldrig "VM"/"EM".
                        _stage = re.match(
                            r'^(kvart|semi|kvalifik|delsfinale|finale|gruppe|ottendedels|\d)',
                            away_candidate, re.I)
                        if not _stage and home_candidate.lower() not in ('vm', 'em'):
                            home_raw = home_candidate
                            away_raw = away_candidate
                    continue
            if league_raw is None and not _is_date(line):
                league_raw = line.split(',')[0].strip()
        if home_raw:
            results.append({'date': date_str, 'time': time_str,
                            'league_raw': league_raw,
                            'home_raw': home_raw, 'away_raw': away_raw})
    return results

# ── Kør ──────────────────────────────────────────────────────────────────
raw_text = _fetch_cognito() or _read_kupon_input()
if not raw_text:
    print('❌ Ingen kampdata — indsæt tekst i data/kupon_input.txt')
    sys.exit(1)

raw_parsed = parse_matches(raw_text)
print(f'📋 Parsede {len(raw_parsed)} kampblokke')

if not raw_parsed:
    print('❌ Ingen kampe parsede — tjek format i kuponsteksten')
    sys.exit(1)

# Auto-detekter CURRENT_ROUND fra kuponstekst
CURRENT_ROUND = None
_rnd_match = re.search(r'(?:kupon|runde)\s+nr\.?\s*(\d+)', raw_text, re.I)
if _rnd_match:
    CURRENT_ROUND = int(_rnd_match.group(1))
    print(f'  ✓ Runde {CURRENT_ROUND} detekteret fra kuponstekst')
elif os.path.exists(MATCHES_CSV):
    try:
        _df = pd.read_csv(MATCHES_CSV)
        _df['season'] = _df['season'].astype(int)
        _df['round']  = _df['round'].astype(int)
        CURRENT_ROUND = int(_df[_df['season'] == CURRENT_SEASON]['round'].max())
        print(f'  ✓ Runde {CURRENT_ROUND} hentet fra weekly_matches.csv')
    except Exception as e:
        print(f'  ⚠ Kunne ikke hente runde: {e}')

if CURRENT_ROUND is None:
    print('❌ Kunne ikke detektere runde — indsæt "Runde nr. X" i kuponsteksten')
    sys.exit(1)

for i, r in enumerate(raw_parsed, 1):
    print(f'  #{i}: {r["home_raw"]} vs {r["away_raw"]} ({r["date"]}, {r["league_raw"]})')

resolved = []
for i, r in enumerate(raw_parsed, 1):
    h  = r['home_raw'] or ''
    a  = r['away_raw'] or ''
    lg = _norm_league(r['league_raw'])
    resolved.append({
        'season':       CURRENT_SEASON,
        'round':        CURRENT_ROUND,
        'match_no':     i,
        'match_code':   _make_code(h, a),
        'date':         r['date'],
        'time':         r['time'],
        'league':       lg,
        'league_raw':   r['league_raw'],
        'home_team':    h,
        'away_team':    a,
        'fixture_id':   None,
        'league_id':    None,
        'home_team_id': None,
        'away_team_id': None,
        'result':       None,
    })

if _ABBR_FALLBACK_LOG:
    print('\n⚠️  Hold uden mapping (brugte fallback-forkortelse):')
    for holdnavn, fbkode in _ABBR_FALLBACK_LOG:
        print(f'   ➜  "{holdnavn}" → "{fbkode}"')

df_new = pd.DataFrame(resolved)
df_new['season'] = df_new['season'].astype(int)
df_new['round']  = df_new['round'].astype(int)

csv_upsert(
    path=MATCHES_CSV,
    df_new=df_new,
    key_cols=['season', 'round', 'match_no'],
    overwrite_if_new_data=False,
)

print(f'\n✅ {len(df_new)} kampe gemt → sæson {CURRENT_SEASON}, runde {CURRENT_ROUND}')
