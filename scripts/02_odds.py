#!/usr/bin/env python3
"""
02_odds.py — Henter odds (The Odds API), ELO, Bzzoiro, N20, Poisson MC,
Odds MC og Ensemble. Opdaterer odds.csv.
Kræver: rapidfuzz, unidecode (installeres automatisk hvis mangler)
"""
import os, sys, json, requests, datetime, io
import pandas as pd
import numpy as np

try:
    from rapidfuzz import process, fuzz
    from unidecode import unidecode
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'rapidfuzz', 'unidecode', '-q'], check=True)
    from rapidfuzz import process, fuzz
    from unidecode import unidecode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import (
    CURRENT_SEASON, DATA_DIR, MATCHES_CSV, ODDS_CSV,
    ODDS_API_KEY, BZZOIRO_TOKEN,
    csv_upsert, get_current_round
)

CURRENT_ROUND      = get_current_round()
FORCE_REFRESH_ODDS = False
FORCE_REFRESH_BZZ  = True
FORCE_REFRESH_N20  = False

print(f'Odds-pipeline: sæson {CURRENT_SEASON}, runde {CURRENT_ROUND}')

# ══════════════════════════════════════════════════════════════════════════
# 02-A: TEAM-ALIASSER, LIGA-MAPPING, RANKINGS, ODDS API
# ══════════════════════════════════════════════════════════════════════════

TEAM_ALIASES = {
    'FC København':       ['FC København','F.C. København','FC Copenhagen','Copenhagen','FCK','FC Kbh'],
    'Brøndby':            ['Brøndby IF','Brøndby','Brondby IF','Brondby','BIF'],
    'FC Midtjylland':     ['FC Midtjylland','Midtjylland','FCM'],
    'FC Nordsjælland':    ['FC Nordsjælland','Nordsjælland','FC Nordsjaelland','FCN'],
    'AGF':                ['AGF','Aarhus GF','Aarhus','AGF Aarhus'],
    'OB':                 ['OB','Odense Boldklub','Odense BK'],
    'Silkeborg IF':       ['Silkeborg IF','Silkeborg'],
    'Randers FC':         ['Randers FC','Randers'],
    'Sønderjyske':        ['Sønderjyske','SønderjyskE','Sonderjyske'],
    'Viborg FF':          ['Viborg FF','Viborg'],
    'Lyngby BK':          ['Lyngby BK','Lyngby'],
    'Vejle BK':           ['Vejle BK','Vejle'],
    'HB Køge':            ['HB Køge'],
    'Hvidovre IF':        ['Hvidovre IF','Hvidovre'],
    'AaB':                ['AaB','Aalborg BK','Aalborg'],
    'AC Horsens':         ['AC Horsens','Horsens'],
    'Esbjerg':            ['Esbjerg','Esbjerg FB'],
    'Manchester City':    ['Manchester City','Man City','ManCity'],
    'Manchester United':  ['Manchester United','Man Utd','Man United','Manchester Utd'],
    'Arsenal':            ['Arsenal','Arsenal FC'],
    'Chelsea':            ['Chelsea','Chelsea FC'],
    'Liverpool':          ['Liverpool','Liverpool FC'],
    'Tottenham':          ['Tottenham','Tottenham Hotspur','Spurs'],
    'Newcastle United':   ['Newcastle United','Newcastle'],
    'Brighton':           ['Brighton','Brighton and Hove Albion'],
    'West Ham':           ['West Ham','West Ham United'],
    'Nottingham Forest':  ['Nottingham Forest','Nottm Forest','Forest'],
    'Bournemouth':        ['Bournemouth','AFC Bournemouth'],
    'Fulham':             ['Fulham','Fulham FC'],
    'Crystal Palace':     ['Crystal Palace','Palace'],
    'Leicester City':     ['Leicester City','Leicester'],
    'Aston Villa':        ['Aston Villa','Villa'],
    'Leeds United':       ['Leeds United','Leeds'],
    'Sheffield United':   ['Sheffield United','Sheffield Utd'],
    'Wolverhampton':      ['Wolverhampton','Wolves','Wolverhampton Wanderers'],
    'Everton':            ['Everton'],
    'Brentford':          ['Brentford'],
    'Southampton':        ['Southampton'],
    'Real Madrid':        ['Real Madrid','Real Madrid CF'],
    'Barcelona':          ['Barcelona','FC Barcelona'],
    'Atlético Madrid':    ['Atlético Madrid','Atletico Madrid','Atletico de Madrid','Atletico'],
    'Athletic Bilbao':    ['Athletic Bilbao','Athletic Club','Athletic Club Bilbao'],
    'Real Betis':         ['Real Betis','Betis'],
    'Villarreal':         ['Villarreal','Villarreal CF'],
    'Real Sociedad':      ['Real Sociedad'],
    'Sevilla':            ['Sevilla','Sevilla FC'],
    'Valencia':           ['Valencia','Valencia CF'],
    'Girona':             ['Girona','Girona FC'],
    'Osasuna':            ['Osasuna','CA Osasuna'],
    'Espanyol':           ['Espanyol','RCD Espanyol'],
    'Celta Vigo':         ['Celta Vigo','Celta de Vigo','Celta'],
    'Vallecano':          ['Rayo Vallecano','Rayo','Vallecano'],
    'Mallorca':           ['Mallorca','Mallorca FC'],
    'Bayern München':     ['Bayern München','Bayern Munich','FC Bayern München','FC Bayern Munich','Bayern'],
    'Borussia Dortmund':  ['Borussia Dortmund','Dortmund','BVB'],
    'RB Leipzig':         ['RB Leipzig','Leipzig','RasenBallsport Leipzig'],
    'Leverkusen':         ['Bayer Leverkusen','Leverkusen','Bayer 04 Leverkusen'],
    'Eintracht Frankfurt':['Eintracht Frankfurt','Frankfurt','Eintracht'],
    'Stuttgart':          ['VfB Stuttgart','Stuttgart'],
    'Werder Bremen':      ['Werder Bremen','Werder','SV Werder Bremen'],
    'FC Köln':            ['FC Köln','Köln','1. FC Köln'],
    'Union Berlin':       ['Union Berlin','1. FC Union Berlin'],
    'Mainz':              ['Mainz','Mainz 05','1. FSV Mainz 05'],
    'HSV Hamburg':        ['HSV Hamburg','Hamburger SV','HSV','Hamburg'],
    'FC St. Pauli':       ['FC St. Pauli','St. Pauli'],
    'Freiburg':           ['Freiburg','SC Freiburg'],
    'Hoffenheim':         ['TSG Hoffenheim','Hoffenheim','1899 Hoffenheim'],
    'Wolfsburg':          ['Wolfsburg','VFL Wolfsburg'],
    'AC Milan':           ['AC Milan','Milan'],
    'Inter':              ['Inter Milan','Inter','Internazionale','FC Internazionale'],
    'Juventus':           ['Juventus','Juventus FC'],
    'Napoli':             ['Napoli','SSC Napoli'],
    'Roma':               ['Roma','AS Roma'],
    'Lazio':              ['Lazio','SS Lazio'],
    'Atalanta':           ['Atalanta','Atalanta BC'],
    'Fiorentina':         ['Fiorentina','ACF Fiorentina'],
    'Paris Saint-Germain':['Paris Saint-Germain','PSG','Paris SG','Paris Saint Germain'],
    'Marseille':          ['Marseille','Olympique Marseille','Olympique de Marseille'],
    'Lyon':               ['Lyon','Olympique Lyonnais'],
    'Monaco':             ['Monaco','AS Monaco'],
    'Lille':              ['Lille','Lille OSC','LOSC Lille'],
    'Benfica':            ['Benfica','SL Benfica'],
    'Sporting CP':        ['Sporting CP','Sporting Lisbon','Sporting'],
    'Porto':              ['Porto','FC Porto'],
    'Ajax':               ['Ajax','AFC Ajax'],
    'Feyenoord':          ['Feyenoord','Feyenoord Rotterdam'],
    'PSV':                ['PSV','PSV Eindhoven'],
    'Club Brugge':        ['Club Brugge','Club Brugge KV','Brugge'],
    'Celtic':             ['Celtic','Celtic FC'],
    'Rangers':            ['Rangers','Rangers FC'],
    'Galatasaray':        ['Galatasaray','Galatasaray SK'],
    'Fenerbahçe':         ['Fenerbahçe','Fenerbahce'],
    'Bodø/Glimt':         ['Bodø/Glimt','Bodo/Glimt','FK Bodø/Glimt'],
    'Danmark':            ['Danmark','Denmark','DEN'],
    'England':            ['England','ENG'],
    'Frankrig':           ['Frankrig','France','FRA'],
    'Tyskland':           ['Tyskland','Germany','GER'],
    'Spanien':            ['Spanien','Spain','ESP'],
    'Italien':            ['Italien','Italy','ITA'],
    'Holland':            ['Holland','Netherlands','NED'],
    'Portugal':           ['Portugal','POR'],
    'Belgien':            ['Belgien','Belgium','BEL'],
    'Sverige':            ['Sverige','Sweden','SWE'],
    'Norge':              ['Norge','Norway','NOR'],
    'Schweiz':            ['Schweiz','Switzerland','SUI'],
    'Østrig':             ['Østrig','Austria','AUT'],
    # VM-hold (daniserede navne)
    'Kroatien':           ['Kroatien','Croatia','CRO'],
    'Ghana':              ['Ghana','GHA'],
    'Panama':             ['Panama','PAN'],
    'Colombia':           ['Colombia','COL'],
    'Algeriet':           ['Algeriet','Algeria','ALG','Algeria'],
    'Brasilien':          ['Brasilien','Brazil','BRA','Brasil'],
    'Japan':              ['Japan','JPN'],
    'Sydafrika':          ['Sydafrika','South Africa','RSA'],
    'Canada':             ['Canada','CAN'],
    'Senegal':            ['Senegal','SEN'],
    'Tunesien':           ['Tunesien','Tunisia','TUN'],
    'Egypten':            ['Egypten','Egypt','EGY'],
    'Iran':               ['Iran','IRN'],
    'Australien':         ['Australien','Australia','AUS'],
    'Marokko':            ['Marokko','Morocco','MAR'],
    'Cameroun':           ['Cameroun','Cameroon','CMR'],
    'Elfenbenskysten':    ['Elfenbenskysten','Ivory Coast','Côte d\'Ivoire','CIV'],
    'USA':                ['USA','United States','United States of America','USMNT'],
    'Mexico':             ['Mexico','MEX'],
    'Ecuador':            ['Ecuador','ECU'],
    'Qatar':              ['Qatar','Katar','QAT'],
    'Saudi-Arabien':      ['Saudi-Arabien','Saudi Arabia','KSA','KSA'],
    'Bosnien':            ['Bosnien','Bosnia and Herzegovina','Bosnia','BIH'],
    'Uzbekistan':         ['Uzbekistan','UZB'],
    'Argentina':          ['Argentina','ARG'],
    'Østrig':             ['Østrig','Austria','AUT'],
    # Nordiske klub-hold (Superettan, Veikkausliiga, OBOS-ligaen, Meistriliiga)
    'Varbergs BOIS':      ['Varbergs BOIS','Varberg','Varbergs BoIS'],
    'Östers IF':          ['Östers IF','Osters IF','Öster'],
    'HJK Helsinki':       ['HJK Helsinki','HJK','Helsingin Jalkapalloklubi'],
    'KuPS':               ['KuPS','Kuopion Palloseura','FC KuPS','KuPS Kuopio','Kuopio'],
    'Strømsgodset':       ['Strømsgodset','Stroemsgodset','IK Strømsgodset','Stromsgodset'],
    'Odds BK':            ['Odds BK','Odds','SK Odd','Odd Grenland','Odd'],
    'Levadia Tallinn':    ['Levadia Tallinn','FCI Levadia','Levadia','FC Levadia','FCI Levadia Tallinn'],
    'Flora Tallinn':      ['Flora Tallinn','FC Flora','Flora','FC Flora Tallinn'],
}

_V2C = {}
for canon, variants in TEAM_ALIASES.items():
    _V2C[canon] = canon
    for v in variants:
        _V2C[v] = canon

def _norm(s):
    return unidecode(str(s)).lower().replace('-', ' ').replace('/', ' ').strip()

_NORM_V2C = {_norm(v): c for v, c in _V2C.items()}

def resolve_team(raw):
    if not raw or str(raw).strip() in ('', 'nan'): return raw
    raw = str(raw).strip()
    if raw in _V2C: return _V2C[raw]
    n = _norm(raw)
    if n in _NORM_V2C: return _NORM_V2C[n]
    TEAM_ALIASES[raw] = [raw]; _V2C[raw] = raw; _NORM_V2C[n] = raw
    return raw

def _canon_set(name):
    variants = [name] + TEAM_ALIASES.get(name, [])
    return {_norm(x) for x in variants}

LEAGUE_ODDS_KEY = {
    'Premier League':    'soccer_epl',
    'Championship':      'soccer_efl_champ',
    'FA Cup':            'soccer_fa_cup',
    'EFL Cup':           'soccer_england_efl_cup',
    'La Liga':           'soccer_spain_la_liga',
    'Copa del Rey':      'soccer_spain_copa_del_rey',
    'Bundesliga':        'soccer_germany_bundesliga',
    '2. Bundesliga':     'soccer_germany_bundesliga2',
    'Serie A':           'soccer_italy_serie_a',
    'Serie B':           'soccer_italy_serie_b',
    'Ligue 1':           'soccer_france_ligue_one',
    'Liga Portugal':     'soccer_portugal_primeira_liga',
    'Eredivisie':        'soccer_netherlands_eredivisie',
    'Superligaen':       'soccer_denmark_superliga',
    '1. division':       'soccer_denmark_division_1',
    # Europæiske turneringer: prøv både hovedturnering OG kvalifikation.
    # Kval-kampene (juli-aug) ligger under en separat sport-nøgle i Odds API.
    'Champions League':  ['soccer_uefa_champs_league',
                          'soccer_uefa_champs_league_qualification'],
    'Europa League':     ['soccer_uefa_europa_league',
                          'soccer_uefa_europa_league_qualification'],
    'Conference League': ['soccer_uefa_europa_conference_league',
                          'soccer_uefa_europa_conference_league_qualification'],
    'Nations League':    'soccer_uefa_nations_league',
    'Allsvenskan':       'soccer_sweden_allsvenskan',
    'Eliteserien':       'soccer_norway_eliteserien',
    'Coupe de France':   'soccer_france_coupe_de_france',
    'VM':                'soccer_fifa_world_cup',
    'Landskamp':         'soccer_fifa_world_cup',
    'Superettan':        'soccer_sweden_superettan',
    'Allsvenskan':       'soccer_sweden_allsvenskan',
    'Eliteserien':       'soccer_norway_eliteserien',
    'OBOS-ligaen':       'soccer_norway_tippeligaen_second',
    'Veikkausliiga':     'soccer_finland_veikkausliiga',
}

LEAGUE_DISPLAY = {
    'DBU Pokalen': 'DBU Pokalen', 'Superliga': 'Superligaen', 'Superligaen': 'Superligaen',
    'Premier League': 'Premier League', 'FA Cup': 'FA Cup', 'EFL Cup': 'EFL Cup',
    'Carabao Cup': 'EFL Cup', 'Championship': 'Championship',
    'La Liga': 'La Liga', 'Copa del Rey': 'Copa del Rey',
    'Bundesliga': 'Bundesliga', '2. Bundesliga': '2. Bundesliga', 'DFB-Pokal': 'DFB-Pokal',
    'Serie A': 'Serie A', 'Ligue 1': 'Ligue 1',
    'Liga Portugal': 'Liga Portugal', 'Primeira Liga': 'Liga Portugal',
    'Eredivisie': 'Eredivisie',
    'Champions League': 'Champions League', 'UEFA Champions League': 'Champions League',
    'Europa League': 'Europa League', 'UEFA Europa League': 'Europa League',
    'Conference League': 'Conference League', 'UEFA Conference League': 'Conference League',
    'Nations League': 'Nations League', 'Allsvenskan': 'Allsvenskan',
    'Coupe de France': 'Coupe de France', 'Serie B': 'Serie B',
    '1. division': '1. division', 'Landskamp': 'Landskamp',
    'Superettan': 'Superettan', 'Veikkausliiga': 'Veikkausliiga',
    'OBOS-ligaen': 'OBOS-ligaen', 'Meistriliiga': 'Meistriliiga',
    'Eliteserien': 'Eliteserien',
}

def resolve_league(raw):
    if not raw: return 'Ukendt'
    raw = str(raw).strip()
    if raw in LEAGUE_DISPLAY: return LEAGUE_DISPLAY[raw]
    for k, v in LEAGUE_DISPLAY.items():
        if k.lower() in raw.lower(): return v
    return raw

# ── Rankings (Opta + ClubElo) ─────────────────────────────────────────────
print('Henter club rankings...')
opta_df = elo_df = pd.DataFrame()
try:
    rel = requests.get(
        'https://api.github.com/repos/tonyelhabr/club-rankings/releases/latest',
        timeout=30).json()
    assets = {a['name']: a['browser_download_url']
              for a in rel.get('assets', []) if a['name'].endswith('.csv')}
    if 'opta-club-rankings.csv' in assets:
        opta_df = pd.read_csv(assets['opta-club-rankings.csv'], low_memory=False)
        opta_df['updated_at'] = pd.to_datetime(opta_df['updated_at'], errors='coerce')
        opta_df = opta_df[opta_df['updated_at'] == opta_df['updated_at'].max()].copy()
        opta_df['_norm'] = opta_df['team'].apply(_norm)
        _opta_age = (datetime.date.today() - opta_df['updated_at'].max().date()).days
        print(f'  Opta: {len(opta_df)} hold ({_opta_age} dage siden)')
    _today_str = datetime.date.today().isoformat()
    _elo_r = requests.get(f'http://api.clubelo.com/{_today_str}', timeout=15)
    if _elo_r.status_code == 200:
        elo_df = pd.read_csv(io.StringIO(_elo_r.text))
        elo_df['_norm'] = elo_df['Club'].apply(_norm)
        print(f'  ELO: {len(elo_df)} hold')
except Exception as e:
    print(f'  ⚠ Rankings fejl: {e}')

def _rank(team, df, val_col, cutoff=88):
    if df.empty: return None
    canonical = resolve_team(team)
    for alias_norm in _canon_set(canonical):
        ex = df[df['_norm'] == alias_norm]
        if not ex.empty: return ex[val_col].values[0]
    primary = _norm(canonical)
    m = process.extractOne(primary, df['_norm'].tolist(), scorer=fuzz.WRatio, score_cutoff=cutoff)
    if m: return df.loc[df['_norm'] == m[0], val_col].values[0]
    return None

# ── Odds API ──────────────────────────────────────────────────────────────
_odds_cache = {}

def _fetch_league(sport_key):
    if sport_key in _odds_cache: return _odds_cache[sport_key]
    url = f'https://api.the-odds-api.com/v4/sports/{sport_key}/odds/'
    params = {'apiKey': ODDS_API_KEY, 'regions': 'eu', 'markets': 'h2h', 'oddsFormat': 'decimal'}
    try:
        r = requests.get(url, params=params, timeout=25)
        rem = r.headers.get('x-requests-remaining', '?')
        if r.status_code == 401:
            print('  ⚠ Ugyldig API-nøgle')
            return []
        data = r.json()
        if isinstance(data, list):
            _odds_cache[sport_key] = data
            print(f'  {sport_key}: {len(data)} events (tilbage: {rem})')
            return data
        msg = data.get('message', str(data)) if isinstance(data, dict) else str(data)
        print(f'  ⚠ {sport_key}: {msg}')
    except Exception as e:
        print(f'  ⚠ Odds fejl {sport_key}: {e}')
    # Cache tomt svar (fx ukendt kval-nøgle) så nøglen kun kaldes én gang pr. kørsel
    _odds_cache[sport_key] = []
    return []

def _get_match_odds(home, away, league):
    sport_key = LEAGUE_ODDS_KEY.get(league)
    if not sport_key: return None, None, None, None, None
    # Nøgle kan være enkelt streng eller liste af kandidater (fx hovedturnering + kval)
    sport_keys = sport_key if isinstance(sport_key, (list, tuple)) else [sport_key]
    hc = _canon_set(home); ac = _canon_set(away)
    for sk in sport_keys:
        events = _fetch_league(sk)
        for ev in events:
            evh = _norm(ev.get('home_team', ''))
            eva = _norm(ev.get('away_team', ''))
            direct  = (evh in hc and eva in ac)
            swapped = (evh in ac and eva in hc)
            if not (direct or swapped):
                if (max(fuzz.WRatio(_norm(home), evh), fuzz.WRatio(_norm(home), eva)) >= 94 and
                        max(fuzz.WRatio(_norm(away), evh), fuzz.WRatio(_norm(away), eva)) >= 94):
                    direct = True
            if direct or swapped:
                mk = None
                for b in ev.get('bookmakers', []):
                    for mkt in b.get('markets', []):
                        if mkt.get('key') == 'h2h':
                            mk = mkt; break
                    if mk: break
                if not mk: continue
                prices = {_norm(o['name']): o['price'] for o in mk.get('outcomes', [])}
                oh = prices.get(_norm(ev['home_team']))
                oa = prices.get(_norm(ev['away_team']))
                od = prices.get('draw')
                if not oh or not oa: continue
                if swapped: oh, oa = oa, oh
                inv_h = 1/oh; inv_a = 1/oa; inv_d = 1/od if od else 0
                s = inv_h + inv_a + inv_d
                if s == 0: continue
                return (round(oh, 2), round(od, 2) if od else None, round(oa, 2),
                        round(inv_h/s*100, 1), round(inv_a/s*100, 1))
    return None, None, None, None, None

def _rec_regel(o1, ox, o2):
    if not (o1 and ox and o2): return None
    margin = 1/o1 + 1/ox + 1/o2
    p1r, pxr, p2r = (1/o1)/margin, (1/ox)/margin, (1/o2)/margin
    return max([('1', p1r), ('X', pxr), ('2', p2r)], key=lambda x: x[1])[0]

def _rec_lr(o1, ox, o2, elo_home, elo_away):
    if o1 and ox and o2: return _rec_regel(o1, ox, o2)
    if elo_home and elo_away:
        diff = elo_home - elo_away
        if diff > 80:   return '1'
        if diff < -80:  return '2'
        return 'X'
    return None

# Hent kampe for aktuel runde
df_matches = pd.read_csv(MATCHES_CSV)
df_matches['season'] = df_matches['season'].astype(int)
df_matches['round']  = df_matches['round'].astype(int)
df_rnd = df_matches[
    (df_matches['season'] == CURRENT_SEASON) &
    (df_matches['round']  == CURRENT_ROUND)
].sort_values('match_no').drop_duplicates(
    subset=['season', 'round', 'home_team', 'away_team'], keep='last'
)

if df_rnd.empty:
    print('❌ Ingen kampe for denne runde — kør 01_kampe.py først')
    sys.exit(1)

_odds_ok = set()
_df_ex = pd.DataFrame()
if os.path.exists(ODDS_CSV) and not FORCE_REFRESH_ODDS:
    _df_ex = pd.read_csv(ODDS_CSV)
    _df_ex = _df_ex[(_df_ex['season'] == CURRENT_SEASON) & (_df_ex['round'] == CURRENT_ROUND)]
    for _, _r in _df_ex.iterrows():
        if pd.notna(_r.get('odds_1')) and pd.notna(_r.get('odds_x')) and pd.notna(_r.get('odds_2')):
            _odds_ok.add(_r['match_code'])
if _odds_ok:
    print(f'  (springer {len(_odds_ok)} kamp(e) over — odds OK)')

rows = []
for _, m in df_rnd.iterrows():
    home, away = m['home_team'], m['away_team']
    canonical_league = resolve_league(m['league'])
    print(f"  [{int(m['match_no']):2}] {home} vs {away}...", end=' ', flush=True)
    mc = m.get('match_code', '')
    if mc in _odds_ok:
        # Tjek om ranking mangler — i så fald hentes ELO/Opta (ingen odds-API-kald)
        _ex_r = _df_ex[_df_ex['match_code'] == mc].iloc[0] if not _df_ex[_df_ex['match_code'] == mc].empty else None
        _has_ranking = _ex_r is not None and (pd.notna(_ex_r.get('elo_home')) or pd.notna(_ex_r.get('opta_home')))
        if _has_ranking:
            print('(spring over)'); continue
        eh = _rank(home, elo_df, 'Elo'); ea = _rank(away, elo_df, 'Elo')
        oh = _rank(home, opta_df, 'rating'); oa = _rank(away, opta_df, 'rating')
        eh = int(eh) if eh is not None else None
        ea = int(ea) if ea is not None else None
        if eh is None and ea is None and oh is None and oa is None:
            print('(spring over — ingen ranking)'); continue
        rows.append({
            'season': CURRENT_SEASON, 'round': CURRENT_ROUND,
            'match_no': int(m['match_no']), 'match_code': mc,
            'date': str(m.get('date', '')), 'league': canonical_league,
            'home_team': home, 'away_team': away,
            'odds_1': None, 'odds_x': None, 'odds_2': None,
            'prob_1': None, 'prob_2': None,
            'elo_home': eh, 'elo_away': ea,
            'elo_diff': (eh-ea) if (eh and ea) else None,
            'opta_home': round(oh, 1) if oh else None,
            'opta_away': round(oa, 1) if oa else None,
            'opta_diff': round(oh-oa, 1) if (oh and oa) else None,
            'favourit': None, 'rec_regel': None, 'rec_lr': None, 'rec_bzz': None,
        })
        print(f"(ELO: {eh or '–'}/{ea or '–'}, Opta: {'✓' if oh else '–'})")
        continue
    o1, ox, o2, p1, p2 = _get_match_odds(home, away, canonical_league)
    eh = _rank(home, elo_df, 'Elo')
    ea = _rank(away, elo_df, 'Elo')
    oh = _rank(home, opta_df, 'rating')
    oa = _rank(away, opta_df, 'rating')
    eh = int(eh) if eh is not None else None
    ea = int(ea) if ea is not None else None
    if p1 is not None and p2 is not None:
        fav = '1' if p1 > p2 else ('2' if p2 > p1 else 'X')
    elif eh is not None and ea is not None:
        fav = '1' if eh > ea else ('2' if ea > eh else 'X')
    elif oh is not None and oa is not None:
        fav = '1' if oh > oa else ('2' if oa > oh else 'X')
    else:
        fav = None
    rows.append({
        'season': CURRENT_SEASON, 'round': CURRENT_ROUND,
        'match_no': int(m['match_no']), 'match_code': mc,
        'date': str(m.get('date', '')), 'league': canonical_league,
        'home_team': home, 'away_team': away,
        'odds_1': o1, 'odds_x': ox, 'odds_2': o2,
        'prob_1': p1, 'prob_2': p2,
        'elo_home': eh, 'elo_away': ea,
        'elo_diff': (eh-ea) if (eh and ea) else None,
        'opta_home': round(oh, 1) if oh else None,
        'opta_away': round(oa, 1) if oa else None,
        'opta_diff': round(oh-oa, 1) if (oh and oa) else None,
        'favourit': fav,
        'rec_regel': _rec_regel(o1, ox, o2),
        'rec_lr':    _rec_lr(o1, ox, o2, eh, ea),
        'rec_bzz':   None,
    })
    print('OK' if o1 else ('ELO' if eh else '--'))

df_new = pd.DataFrame(rows)
if not df_new.empty:
    df_new.drop_duplicates(subset=['season', 'round', 'match_no'], keep='last', inplace=True)
    if os.path.exists(ODDS_CSV):
        try:
            df_ex_odds = pd.read_csv(ODDS_CSV)
            df_ex_odds['season'] = df_ex_odds['season'].astype(int)
            df_ex_odds['round']  = df_ex_odds['round'].astype(int)
            cleaned = df_ex_odds.drop_duplicates(subset=['season', 'round', 'match_no'], keep='last')
            if len(cleaned) < len(df_ex_odds):
                cleaned.to_csv(ODDS_CSV, index=False)
        except Exception: pass
    csv_upsert(path=ODDS_CSV, df_new=df_new,
               key_cols=['season', 'round', 'match_no'], overwrite_if_new_data=True)
else:
    print('  (alle kampe springet over)')

# ══════════════════════════════════════════════════════════════════════════
# 02-C: BZZOIRO ML-predictions
# ══════════════════════════════════════════════════════════════════════════
print(f'\nBzzoiro ML-predictions (S{CURRENT_SEASON} R{CURRENT_ROUND})...')

_BZZ_BASE    = 'https://sports.bzzoiro.com/api/v2'
_BZZ_HEADERS = {'Authorization': f'Token {BZZOIRO_TOKEN}'} if BZZOIRO_TOKEN else {}

_BZZ_LEAGUE_IDS = {
    'Premier League': 1, 'La Liga': 3, 'Serie A': 4, 'Bundesliga': 5,
    'Ligue 1': 6, 'Champions League': 7, 'Europa League': 8,
    'Eredivisie': 10, 'Superligaen': 11, '1. division': 38,
    'Liga Portugal': 2, 'FA Cup': 39, 'Allsvenskan': 26,
    'Copa del Rey': 41, 'Championship': 12,
}

_bzz_cache = {}

def _bzz_fetch_day(date_str):
    if not BZZOIRO_TOKEN: return []
    if date_str in _bzz_cache: return _bzz_cache[date_str]
    try:
        r = requests.get(f'{_BZZ_BASE}/events/',
                         headers=_BZZ_HEADERS,
                         params={'date_from': date_str, 'date_to': date_str, 'limit': 200},
                         timeout=15)
        r.raise_for_status()
        events = r.json().get('results', [])
        _bzz_cache[date_str] = events
        return events
    except Exception as e:
        print(f'  ⚠ Bzzoiro fejl ({date_str}): {e}')
        return []

def _bzz_prediction(home, away, date_str, league):
    if not BZZOIRO_TOKEN: return None
    events = _bzz_fetch_day(date_str)
    if not events: return None
    league_id  = _BZZ_LEAGUE_IDS.get(league)
    candidates = [e for e in events if e.get('league_id') == league_id] or events

    def clean_t(n):
        return unidecode(str(n)).lower().replace('fc ', '').replace('afc ', '').replace('sc ', '').strip()

    nh = clean_t(home); na = clean_t(away)
    best_score = 0; best_id = None
    for ev in candidates:
        eh = clean_t(ev.get('home_team', ''))
        ea = clean_t(ev.get('away_team', ''))
        score = max((fuzz.WRatio(nh, eh) + fuzz.WRatio(na, ea)) / 2,
                    (fuzz.WRatio(nh, ea) + fuzz.WRatio(na, eh)) / 2)
        if score > best_score:
            best_score = score; best_id = ev.get('id')
    if best_score < 55 or best_id is None: return None
    try:
        r = requests.get(f'{_BZZ_BASE}/predictions/{best_id}/', headers=_BZZ_HEADERS, timeout=15)
        if r.status_code == 404: return None
        r.raise_for_status()
        data = r.json()
        p1, px, p2 = data.get('home_win'), data.get('draw'), data.get('away_win')
        if None in (p1, px, p2): return None
        return max([(p1, '1'), (px, 'X'), (p2, '2')], key=lambda x: x[0])[1]
    except Exception:
        return None

if BZZOIRO_TOKEN and os.path.exists(ODDS_CSV):
    df_m_bzz = pd.read_csv(MATCHES_CSV)
    df_m_bzz = df_m_bzz[(df_m_bzz['season'] == CURRENT_SEASON) & (df_m_bzz['round'] == CURRENT_ROUND)]
    df_m_bzz.drop_duplicates(subset=['season', 'round', 'home_team', 'away_team'], keep='last', inplace=True)
    bzz_results = []
    for _, m in df_m_bzz.iterrows():
        print(f"  {m['home_team']} vs {m['away_team']}...", end=' ', flush=True)
        res = _bzz_prediction(m['home_team'], m['away_team'],
                              str(m.get('date', '')), resolve_league(m['league']))
        print(res or '--')
        if res:
            bzz_results.append({'match_no': m['match_no'], 'rec_bzz': res})
    if bzz_results:
        df_odds_bzz = pd.read_csv(ODDS_CSV)
        for r in bzz_results:
            mask = ((df_odds_bzz['season'] == CURRENT_SEASON) &
                    (df_odds_bzz['round']  == CURRENT_ROUND) &
                    (df_odds_bzz['match_no'] == r['match_no']))
            df_odds_bzz.loc[mask, 'rec_bzz'] = r['rec_bzz']
        df_odds_bzz.to_csv(ODDS_CSV, index=False)
        print(f'✅ Bzzoiro: {len(bzz_results)} predictions opdateret')
else:
    print('  (ingen Bzzoiro-token eller odds.csv mangler)')

# ══════════════════════════════════════════════════════════════════════════
# 02-D: numbertwenty.io predictions
# ══════════════════════════════════════════════════════════════════════════
print(f'\nN20 predictions...')

def _n20_norm(name):
    return unidecode(str(name)).lower().strip().replace(' ','').replace('-','').replace('.','')

_N20_ALIASES = {
    'parissg': 'parissaintgermain', 'psg': 'parissaintgermain',
    'bvb': 'borussiadortmund', 'dortmund': 'borussiadortmund',
    'leverkusen': 'bayerleverkusen', 'inter': 'intermilan',
}

def _n20_variants(name):
    n = _n20_norm(name)
    variants = [_N20_ALIASES.get(n, n)]
    try:
        nl = name.lower()
        for canonical, alias_list in TEAM_ALIASES.items():
            if any(v.lower() == nl for v in ([canonical] + list(alias_list))):
                for v in ([canonical] + list(alias_list)):
                    nv = _n20_norm(v)
                    if nv not in variants: variants.append(nv)
                break
    except Exception: pass
    if n not in variants: variants.append(n)
    return variants

def _n20_extract(item):
    team = (item.get('Team') or item.get('team') or item.get('home_team') or '')
    opp  = (item.get('Opponent') or item.get('opponent') or item.get('away_team') or '')
    pp   = item.get('pred_probs') or {}
    if not pp or not team: return None
    try:
        return {
            'team': str(team).strip(), 'opponent': str(opp).strip(),
            'prob_1': round(float(pp.get('1', pp.get('home', 0))) * 100, 1),
            'prob_x': round(float(pp.get('X', pp.get('draw', 0))) * 100, 1),
            'prob_2': round(float(pp.get('2', pp.get('away', 0))) * 100, 1),
            'elo_home': item.get('Elo_Team') or item.get('elo_team'),
            'elo_away': item.get('Elo_Opponent') or item.get('elo_opponent'),
        }
    except Exception: return None

def _fetch_n20_for_date(date_str):
    try:
        r = requests.get(
            f'https://numbertwenty.io/predict_grouped?date={date_str}&tz_offset=0',
            timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200: return []
        raw = r.json()
        items = raw if isinstance(raw, list) else raw.get('matches', [])
        return [m for m in (_n20_extract(i) for i in items) if m]
    except Exception: return []

if os.path.exists(ODDS_CSV):
    try:
        _df_odds_n20 = pd.read_csv(ODDS_CSV)
        _df_cur_n20  = _df_odds_n20[
            (_df_odds_n20['season'].astype(int) == CURRENT_SEASON) &
            (_df_odds_n20['round'].astype(int)  == CURRENT_ROUND)
        ].drop_duplicates('match_code').copy()

        _skip_n20 = False
        if not FORCE_REFRESH_N20 and 'n20_rec' in _df_odds_n20.columns:
            _done_n20 = set(_df_odds_n20[_df_odds_n20['n20_rec'].notna()]['match_code'])
            _todo_n20 = _df_cur_n20[~_df_cur_n20['match_code'].isin(_done_n20)]
            if _todo_n20.empty:
                print('  N20 allerede hentet — sæt FORCE_REFRESH_N20=True for at genindlæse')
                _skip_n20 = True
        else:
            _todo_n20 = _df_cur_n20

        if not _skip_n20 and not _todo_n20.empty:
            _dates = set()
            if os.path.exists(MATCHES_CSV):
                _df_wm = pd.read_csv(MATCHES_CSV)
                _df_wm = _df_wm[(_df_wm['season'].astype(int) == CURRENT_SEASON) &
                                 (_df_wm['round'].astype(int)  == CURRENT_ROUND)]
                _dc = next((c for c in ['date','match_date','datetime'] if c in _df_wm.columns), None)
                if _dc:
                    for _d in _df_wm[_dc].dropna():
                        try: _dates.add(str(pd.to_datetime(_d).date()))
                        except Exception: pass
            for _off in range(6):
                _dates.add(str(datetime.date.today() + datetime.timedelta(days=_off)))
            _dates = sorted(_dates)
            print(f'  Henter N20 for {len(_dates)} datoer')

            _all_n20 = {}
            for _d in _dates:
                for _m in _fetch_n20_for_date(_d):
                    _key = _n20_norm(_m['team'])
                    _all_n20[_key] = _m

            _all_teams = list(_all_n20.keys())
            _updates_n20 = []

            for _, _row in _todo_n20.iterrows():
                _home = str(_row.get('home_team', '')).strip()
                _away = str(_row.get('away_team', '')).strip()
                _mc   = str(_row['match_code'])
                if not _home or _home == 'nan': continue
                _hn_variants = _n20_variants(_home)
                _found = None
                for _hn in _hn_variants:
                    if _hn in _all_n20:
                        _found = _all_n20[_hn]; break
                if not _found and _all_teams:
                    _bm, _bs, _ = process.extractOne(_hn_variants[0], _all_teams, scorer=fuzz.token_sort_ratio)
                    if _bs >= 78: _found = _all_n20[_bm]
                if _found:
                    _probs = [('1', _found['prob_1']), ('X', _found['prob_x']), ('2', _found['prob_2'])]
                    _rec = max(_probs, key=lambda x: x[1])[0]
                    _updates_n20.append({
                        'match_code': _mc,
                        'n20_prob_1': _found['prob_1'], 'n20_prob_x': _found['prob_x'],
                        'n20_prob_2': _found['prob_2'], 'n20_rec': _rec,
                        'n20_elo_home': round(float(_found['elo_home']), 0) if _found.get('elo_home') else None,
                        'n20_elo_away': round(float(_found['elo_away']), 0) if _found.get('elo_away') else None,
                    })
                    print(f'  {_home} vs {_away}: N20={_rec}')
                else:
                    print(f'  {_home} vs {_away}: ingen N20-match')

            if _updates_n20:
                for _col in ['n20_prob_1','n20_prob_x','n20_prob_2','n20_rec','n20_elo_home','n20_elo_away']:
                    if _col not in _df_odds_n20.columns: _df_odds_n20[_col] = None
                for _, _u in pd.DataFrame(_updates_n20).iterrows():
                    _mask = _df_odds_n20['match_code'] == _u['match_code']
                    for _col in ['n20_prob_1','n20_prob_x','n20_prob_2','n20_rec','n20_elo_home','n20_elo_away']:
                        _df_odds_n20.loc[_mask, _col] = _u[_col]
                _df_odds_n20.to_csv(ODDS_CSV, index=False)
                print(f'✅ N20: {len(_updates_n20)} predictions opdateret')
    except Exception as _n20_e:
        print(f'  ⚠ N20 fejl: {_n20_e}')

# ══════════════════════════════════════════════════════════════════════════
# 02-F: Poisson Monte Carlo
# ══════════════════════════════════════════════════════════════════════════
print(f'\nPoisson MC...')

MODEL_PARAMS_JSON = os.path.join(DATA_DIR, 'model_params.json')
_LIGA_MAP = {
    'bundesliga': 'D1', '2. bundesliga': 'D2',
    'la liga': 'SP1', 'ligue 1': 'F1', 'serie a': 'I1',
    'premier league': 'E0', 'championship': 'E1',
    'eredivisie': 'N1', 'primeira liga': 'P1',
}

def _fdc_code(league):
    lc = str(league).lower()
    for k, v in _LIGA_MAP.items():
        if k in lc: return v
    return None

def _find_team_fdc(name, candidates):
    if not name or not candidates: return None
    m = process.extractOne(name, candidates, scorer=fuzz.token_sort_ratio)
    if m and m[1] >= 72: return m[0]
    return None

def _poisson_mc(lh, la, n=10_000, unc=0.15):
    rng = np.random.default_rng()
    lh_s = np.maximum(rng.normal(lh, lh*unc, n), 0.02)
    la_s = np.maximum(rng.normal(la, la*unc, n), 0.02)
    hg = rng.poisson(lh_s); ag = rng.poisson(la_s)
    return float((hg>ag).mean()), float((hg==ag).mean()), float((hg<ag).mean())

if not os.path.exists(MODEL_PARAMS_JSON):
    print('  ⚠ model_params.json mangler — springer Poisson over')
elif os.path.exists(ODDS_CSV):
    try:
        with open(MODEL_PARAMS_JSON, encoding='utf-8') as _f:
            _mp = json.load(_f)
        _df_wm_p = pd.read_csv(MATCHES_CSV)
        _rnd_p = _df_wm_p[
            (_df_wm_p['season'].astype(str) == str(int(CURRENT_SEASON))) &
            (_df_wm_p['round'].astype(str)  == str(int(CURRENT_ROUND)))
        ].sort_values('match_no')
        _poi_rows = []
        for _, _row in _rnd_p.iterrows():
            _home = str(_row['home_team']); _away = str(_row['away_team'])
            _mc   = str(_row['match_code']); _liga = str(_row.get('league',''))
            _fdc  = _fdc_code(_liga)
            if not _fdc or _fdc not in _mp: continue
            _par = _mp[_fdc]; _tms = _par['teams']
            _hf = _find_team_fdc(_home, _tms); _af = _find_team_fdc(_away, _tms)
            if not _hf or not _af: continue
            _lh = (_par['home_adv'] *
                   np.exp(_par['attack'][_hf] - _par['defense'][_af]) *
                   _par['avg_goals_home'])
            _la = (np.exp(_par['attack'][_af] - _par['defense'][_hf]) * _par['avg_goals_away'])
            _p1, _px, _p2 = _poisson_mc(_lh, _la)
            _rec = '1' if _p1==max(_p1,_px,_p2) else ('X' if _px==max(_p1,_px,_p2) else '2')
            print(f'  {_mc}: {_rec} ({_p1:.0%}/{_px:.0%}/{_p2:.0%})')
            _poi_rows.append({'match_code': _mc, 'poisson_p1': round(_p1*100,1),
                              'poisson_px': round(_px*100,1), 'poisson_p2': round(_p2*100,1),
                              'rec_poisson': _rec})
        if _poi_rows:
            _dfo_p = pd.read_csv(ODDS_CSV)
            for _col in ['poisson_p1','poisson_px','poisson_p2','rec_poisson']:
                if _col not in _dfo_p.columns: _dfo_p[_col] = None
            _msk_base = ((_dfo_p['season'].astype(str)==str(int(CURRENT_SEASON))) &
                         (_dfo_p['round'].astype(str)==str(int(CURRENT_ROUND))))
            for _r in _poi_rows:
                _m = _msk_base & (_dfo_p['match_code'] == _r['match_code'])
                for _c in ['poisson_p1','poisson_px','poisson_p2','rec_poisson']:
                    _dfo_p.loc[_m, _c] = _r[_c]
            _dfo_p.to_csv(ODDS_CSV, index=False)
            print(f'✅ Poisson: {len(_poi_rows)} forudsigelser gemt')
        else:
            print('  (ingen hold matchede Poisson-modellen)')
    except Exception as _pe:
        print(f'  ⚠ Poisson fejl: {_pe}')

# ══════════════════════════════════════════════════════════════════════════
# 02-G: Odds Monte Carlo
# ══════════════════════════════════════════════════════════════════════════
print(f'\nOdds MC...')

HIST_ODDS_CSV = os.path.join(DATA_DIR, 'hist_odds.csv')

if not os.path.exists(HIST_ODDS_CSV):
    print('  ⚠ hist_odds.csv mangler — springer Odds MC over')
elif os.path.exists(ODDS_CSV):
    try:
        _df_ho = pd.read_csv(HIST_ODDS_CSV, encoding='utf-8-sig')
        for _c in ['home_odds', 'draw_odds', 'away_odds']:
            _df_ho[_c] = pd.to_numeric(_df_ho[_c], errors='coerce')
        _df_ho = _df_ho.dropna(subset=['home_odds','draw_odds','away_odds'])
        _df_ho = _df_ho[(_df_ho.home_odds>1)&(_df_ho.draw_odds>1)&(_df_ho.away_odds>1)]
        _mg = 1/_df_ho.home_odds + 1/_df_ho.draw_odds + 1/_df_ho.away_odds
        _df_ho['p1'] = (1/_df_ho.home_odds) / _mg
        _ms = _df_ho.groupby('match_id').agg(
            p1_mean=('p1','mean'), p1_std=('p1','std'), n_bm=('bookmaker','count')
        ).dropna().query('n_bm >= 3')
        _ms['bucket'] = (_ms.p1_mean / 0.05).round() * 0.05
        _vol = _ms.groupby('bucket')['p1_std'].median().reset_index()
        _vol.columns = ['bucket','sigma_median']

        def _lookup_sigma(p1):
            b = round(p1 / 0.05) * 0.05
            row = _vol[_vol.bucket == b]
            if not row.empty: return float(row.iloc[0]['sigma_median'])
            return float(_vol.iloc[(_vol.bucket - p1).abs().idxmin()]['sigma_median'])

        def _odds_mc(p1, px, p2, n=10_000):
            sigma = max(_lookup_sigma(p1), 0.001)
            N_eff = max((p1*(1-p1)) / sigma**2, 4.0)
            alpha = np.maximum(np.array([p1, px, p2]) * N_eff, 0.1)
            draws = np.random.default_rng().dirichlet(alpha, n)
            return float(draws[:,0].mean()), float(draws[:,1].mean()), float(draws[:,2].mean()), float(draws[:,0].std())

        _df_o_mc = pd.read_csv(ODDS_CSV)
        _cs_mc = str(int(CURRENT_SEASON)); _cr_mc = str(int(CURRENT_ROUND))
        _rnd_mc = _df_o_mc[(_df_o_mc['season'].astype(str)==_cs_mc) &
                            (_df_o_mc['round'].astype(str)==_cr_mc)].copy()
        for _col in ['odds_mc_p1','odds_mc_px','odds_mc_p2','odds_mc_unc','rec_odds_mc']:
            if _col not in _df_o_mc.columns: _df_o_mc[_col] = None
        _mc_count = 0
        for _, _r in _rnd_mc.iterrows():
            _mc = str(_r['match_code'])
            _o1 = _r.get('odds_1'); _ox = _r.get('odds_x'); _o2 = _r.get('odds_2')
            if pd.isna(_o1) or pd.isna(_ox) or pd.isna(_o2): continue
            _mg2 = 1/float(_o1)+1/float(_ox)+1/float(_o2)
            _p1=(1/float(_o1))/_mg2; _px=(1/float(_ox))/_mg2; _p2=(1/float(_o2))/_mg2
            _mp1,_mpx,_mp2,_unc = _odds_mc(_p1, _px, _p2)
            _rec = '1' if _mp1==max(_mp1,_mpx,_mp2) else ('X' if _mpx==max(_mp1,_mpx,_mp2) else '2')
            print(f'  {_mc}: {_rec} ({_mp1:.0%}/{_mpx:.0%}/{_mp2:.0%}) unc={round(_unc*100,1)}%')
            _msk = ((_df_o_mc['season'].astype(str)==_cs_mc) &
                    (_df_o_mc['round'].astype(str)==_cr_mc) &
                    (_df_o_mc['match_code']==_mc))
            _df_o_mc.loc[_msk,'odds_mc_p1']  = round(_mp1*100,1)
            _df_o_mc.loc[_msk,'odds_mc_px']  = round(_mpx*100,1)
            _df_o_mc.loc[_msk,'odds_mc_p2']  = round(_mp2*100,1)
            _df_o_mc.loc[_msk,'odds_mc_unc'] = round(_unc*100,1)
            _df_o_mc.loc[_msk,'rec_odds_mc'] = _rec
            _mc_count += 1
        _df_o_mc.to_csv(ODDS_CSV, index=False)
        print(f'✅ Odds MC: {_mc_count} forudsigelser gemt')
    except Exception as _mce:
        print(f'  ⚠ Odds MC fejl: {_mce}')

# ══════════════════════════════════════════════════════════════════════════
# 02-H: Ensemble
# ══════════════════════════════════════════════════════════════════════════
print(f'\nEnsemble...')

_W_PRIOR = {
    'rec_odds_mc': 0.35, 'rec_poisson': 0.25, 'rec_lr': 0.15,
    'n20_rec': 0.12, 'rec_bzz': 0.08, 'rec_regel': 0.05,
}

_calib_json = os.path.join(DATA_DIR, 'model_calibration.json')
if os.path.exists(_calib_json):
    try:
        with open(_calib_json, encoding='utf-8') as _f:
            _calib = json.load(_f)
        _weights = _calib.get('weights', _W_PRIOR)
        print(f'  Kalibrerede vægte indlæst ({_calib.get("calibrated_date", "?")})')
    except Exception:
        _weights = _W_PRIOR
else:
    _weights = _W_PRIOR
    print('  ℹ Bruger priori-vægte')

if os.path.exists(ODDS_CSV):
    try:
        _df_ens = pd.read_csv(ODDS_CSV)
        _cs_ens = str(int(CURRENT_SEASON)); _cr_ens = str(int(CURRENT_ROUND))
        _rnd_ens = _df_ens[(_df_ens['season'].astype(str)==_cs_ens) &
                            (_df_ens['round'].astype(str)==_cr_ens)].copy()
        for _col in ['rec_ensemble','ensemble_conf','ensemble_p1','ensemble_px','ensemble_p2']:
            if _col not in _df_ens.columns: _df_ens[_col] = None

        for _, _r in _rnd_ens.iterrows():
            _mc = str(_r['match_code'])
            _votes = {'1': 0.0, 'X': 0.0, '2': 0.0}; _total_w = 0.0
            for _model, _w in _weights.items():
                _rec_v = _r.get(_model)
                if pd.notna(_rec_v):
                    _rec_s = str(_rec_v)
                    if _rec_s.endswith('.0'): _rec_s = _rec_s[:-2]
                    if _rec_s in ('1','X','2'):
                        _votes[_rec_s] += _w; _total_w += _w
            if _total_w < 0.05: continue
            for _k in _votes: _votes[_k] /= _total_w
            _rec_ens = max(_votes, key=_votes.get)
            _sv = sorted(_votes.values(), reverse=True)
            _conf = _sv[0] - _sv[1]
            _agree = sum(1 for _m in _weights if pd.notna(_r.get(_m)) and str(_r.get(_m)) == _rec_ens)
            _total_models = sum(1 for _m in _weights if pd.notna(_r.get(_m)))
            print(f'  {_mc}: {_rec_ens} ({_votes[_rec_ens]:.0%}) conf={round(_conf*100,1)}% [{_agree}/{_total_models}]')
            _msk_ens = ((_df_ens['season'].astype(str)==_cs_ens) &
                        (_df_ens['round'].astype(str)==_cr_ens) &
                        (_df_ens['match_code']==_mc))
            _df_ens.loc[_msk_ens,'rec_ensemble']  = _rec_ens
            _df_ens.loc[_msk_ens,'ensemble_conf'] = round(_conf*100,1)
            _df_ens.loc[_msk_ens,'ensemble_p1']   = round(_votes['1']*100,1)
            _df_ens.loc[_msk_ens,'ensemble_px']   = round(_votes['X']*100,1)
            _df_ens.loc[_msk_ens,'ensemble_p2']   = round(_votes['2']*100,1)
        _df_ens.to_csv(ODDS_CSV, index=False)
        print(f'✅ Ensemble gemt i odds.csv')
    except Exception as _ee:
        print(f'  ⚠ Ensemble fejl: {_ee}')

print(f'\n✅ 02_odds.py færdig')
