#!/usr/bin/env python3
"""
tools/source_test.py — TEST af nye datakilder (Bzzoiro, pitchapi) mod vores sæson 4-data.

Rører INGEN filer i data/ og indgår ikke i pipelinen. Køres manuelt via
workflowen "Kildetest" (.github/workflows/source-test.yml), fordi API-nøglerne
kun findes som GitHub-secrets. Rapporten skrives til loggen.

Tester:
  A. Dækning: hvilke af vores ligaer findes hos kilden
  B. Resultater: finder kilden vores kampe, og giver 90-min-resultatet det
     samme 1/X/2 som vores (også kampe afgjort i forlænget tid/straffe)
  C. Forudsigelser (Bzzoiro): træfprocent vs. bookmakerfavorit på samme kampe,
     og om forudsigelsen er lavet før kickoff
  D. Odds (Bzzoiro): konsensus-odds vs. vores odds på samme kampe
"""
import os, sys, time, json, datetime as dt
import requests
import pandas as pd
from rapidfuzz import fuzz
from unidecode import unidecode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
SEASON = 4

wm = pd.read_csv(os.path.join(DATA, 'weekly_matches.csv'))
wm = wm[wm['season'] == SEASON].copy()
wm['result'] = wm['result'].astype(str).str.strip()
played = wm[wm['result'].isin(['1', 'X', '2'])].copy()
upcoming = wm[~wm['result'].isin(['1', 'X', '2'])
              & (pd.to_datetime(wm['date'], errors='coerce') >= pd.Timestamp.now().normalize() - pd.Timedelta(days=1))].copy()
plog = pd.read_csv(os.path.join(DATA, 'predictor_log.csv'))
plog = plog[plog['season'] == SEASON]
odds = pd.read_csv(os.path.join(DATA, 'odds.csv'))
odds = odds[odds['season'] == SEASON]

# Navnevarianter fra vores egne filer (samme kilder som pipelinen)
_alias = {}
try:
    _alias.update(json.load(open(os.path.join(DATA, 'odds_aliases.json'))))
except Exception:
    pass
_elo = {}
try:
    hm = json.load(open(os.path.join(DATA, 'hold_mapping.json')))
    for r in (hm if isinstance(hm, list) else hm.values()):
        if isinstance(r, dict) and r.get('name') and r.get('elo_name'):
            _elo[r['name']] = r['elo_name']
except Exception:
    pass

_STRIP = {'fc', 'afc', 'sc', 'cf', 'fk', 'if', 'bk', 'ac', 'sk', 'ssc', 'cd', 'ud', 'sv', 'vfb', 'vfl', 'tsg', 'rc', 'as', 'us', 'ks'}

def norm(s):
    s = unidecode(str(s)).lower().replace('​', '')
    for ch in ".-/'&()":
        s = s.replace(ch, ' ')
    toks = [t for t in s.split() if t not in _STRIP]
    return ' '.join(toks)

def variants(n):
    out = [n, _elo.get(n), _alias.get(n), _alias.get(_elo.get(n, ''))]
    return list(dict.fromkeys(norm(v) for v in out if v))

def name_score(ours, theirs):
    t = norm(theirs)
    best = 0
    for v in variants(ours):
        if not v or not t:
            continue
        s = max(fuzz.token_sort_ratio(v, t), fuzz.ratio(v, t))
        if (v in t or t in v) and min(len(v), len(t)) >= 3:
            s = max(s, 90)
        best = max(best, s)
    return best

def pair_match(home, away, eh, ea, thr=80):
    """Begge hold skal matche (direkte eller byttet). Returnerer (score, byttet)."""
    d = min(name_score(home, eh), name_score(away, ea))
    s = min(name_score(home, ea), name_score(away, eh))
    if d >= thr and d >= s:
        return d, False
    if s >= thr:
        return s, True
    return 0, False

def one_x_two(h, a):
    try:
        h, a = int(h), int(a)
    except Exception:
        return None
    return '1' if h > a else ('2' if h < a else 'X')

def pct(a, b):
    return f'{a}/{b} ({100*a/b:.0f}%)' if b else '0/0'

calls = {'n': 0, '429': 0, 'err': 0}

def get(url, headers, params=None):
    for attempt in range(4):
        calls['n'] += 1
        try:
            r = requests.get(url, headers=headers, params=params, timeout=30)
        except Exception as e:
            calls['err'] += 1
            print(f'    ⚠ {url}: {e}')
            time.sleep(2)
            continue
        if r.status_code == 429:
            calls['429'] += 1
            wait = int(r.headers.get('Retry-After', '5') or 5)
            time.sleep(min(wait, 30))
            continue
        return r
    return None


# ══════════════════════════════════════════════════════════════════════════
def test_bzzoiro(token):
    print('\n' + '═' * 78 + '\nBZZOIRO (sports.bzzoiro.com/api/v2)\n' + '═' * 78)
    B = 'https://sports.bzzoiro.com/api/v2'
    H = {'Authorization': f'Token {token}'}

    # ── A. Ligaer ────────────────────────────────────────────────────────
    leagues, off = [], 0
    while True:
        r = get(f'{B}/leagues/', H, {'limit': 200, 'offset': off})
        if r is None or r.status_code != 200:
            print(f'  ✗ /leagues/ fejlede: {getattr(r, "status_code", "?")} {getattr(r, "text", "")[:200]}')
            return
        j = r.json()
        leagues += j.get('results', [])
        if not j.get('next'):
            break
        off += 200
    print(f'\nA. {len(leagues)} aktive ligaer hos Bzzoiro:')
    for l in sorted(leagues, key=lambda x: (str(x.get('country')), str(x.get('name')))):
        print(f"   id={l.get('id'):>4}  {l.get('country')}: {l.get('name')}")

    # ── B. Resultater ────────────────────────────────────────────────────
    print('\nB. Resultater — alle afgjorte S4-kampe')
    day_cache = {}
    def events_on(d):
        if d in day_cache:
            return day_cache[d]
        evs, off = [], 0
        while True:
            r = get(f'{B}/events/', H, {'date_from': d, 'date_to': d, 'limit': 200, 'offset': off})
            if r is None or r.status_code != 200:
                break
            j = r.json()
            evs += j.get('results', [])
            if not j.get('next') or off > 2000:
                break
            off += 200
        day_cache[d] = evs
        return evs

    sample_printed = False
    found, agree, rows, et_cases = 0, 0, [], []
    by_league = {}
    for _, m in played.sort_values(['round', 'match_no']).iterrows():
        d0 = dt.date.fromisoformat(str(m['date'])[:10])
        best = (0, None, False)
        for dd in (d0, d0 - dt.timedelta(days=1), d0 + dt.timedelta(days=1)):
            for ev in events_on(dd.isoformat()):
                sc, sw = pair_match(m['home_team'], m['away_team'], ev.get('home_team', ''), ev.get('away_team', ''))
                if sc > best[0]:
                    best = (sc, ev, sw)
            if best[0] >= 80:
                break
        lg = m['league']
        by_league.setdefault(lg, [0, 0])
        by_league[lg][1] += 1
        sc, ev, sw = best
        if not ev:
            rows.append((m, None, None, None))
            continue
        if not sample_printed:
            print('   (eksempel på rå kamp-JSON, forkortet):')
            print('   ' + json.dumps({k: ev.get(k) for k in ['id', 'league_id', 'home_team_id', 'home_team', 'away_team', 'event_date', 'status', 'home_score', 'away_score', 'home_score_ht', 'away_score_ht', 'extra_time_score', 'penalty_shootout', 'period']}, ensure_ascii=False)[:600])
            sample_printed = True
        found += 1
        by_league[lg][0] += 1
        res = one_x_two(ev.get('home_score'), ev.get('away_score'))
        if res and sw:
            res = {'1': '2', '2': '1', 'X': 'X'}[res]
        et = ev.get('extra_time_score') or ev.get('penalty_shootout')
        res90 = res
        if et:
            et_cases.append((m, ev))
        ok = (res90 == m['result'])
        agree += ok
        rows.append((m, ev, res90, sc))
    print(f'   Fundet: {pct(found, len(played))}   Samme 1X2 som vores: {pct(agree, found)}')
    print('   Dækning pr. liga (fundet/kampe):')
    for lg, (f, n) in sorted(by_league.items(), key=lambda x: -x[1][1]):
        print(f'     {lg:<22} {f}/{n}')
    print('   Uenige resultater:')
    for m, ev, r90, sc in rows:
        if ev is not None and r90 != m['result']:
            print(f"     R{m['round']} {m['home_team']}–{m['away_team']}: vores {m['result']} / Bzzoiro {r90} "
                  f"({ev.get('home_team')}–{ev.get('away_team')} {ev.get('home_score')}-{ev.get('away_score')}, "
                  f"status={ev.get('status')}, ET={ev.get('extra_time_score')}, PEN={ev.get('penalty_shootout')}, match={sc})")
    print('   Kampe med forlænget tid/straffe hos Bzzoiro (tjek om home_score er 90-min eller inkl. ET):')
    for m, ev in et_cases:
        print(f"     R{m['round']} {m['home_team']}–{m['away_team']} (vores {m['result']}): score={ev.get('home_score')}-{ev.get('away_score')} "
              f"HT={ev.get('home_score_ht')}-{ev.get('away_score_ht')} ET={ev.get('extra_time_score')} PEN={ev.get('penalty_shootout')}")
    if not et_cases:
        print('     (ingen fundet)')
    print('   Ikke fundet:')
    for m, ev, _, _ in rows:
        if ev is None:
            print(f"     R{m['round']} [{m['league']}] {m['home_team']}–{m['away_team']} ({m['date']})")

    # ── C. Forudsigelser ─────────────────────────────────────────────────
    print('\nC. Forudsigelser (/events/{id}/prediction/) på fundne kampe')
    n, hit, fav_hit, fav_n, pre_ko, shown = 0, 0, 0, 0, 0, False
    for m, ev, _, _ in rows:
        if ev is None:
            continue
        r = get(f"{B}/events/{ev['id']}/prediction/", H)
        if r is None or r.status_code != 200:
            continue
        p = r.json()
        if not shown:
            print('   (eksempel, forkortet): ' + json.dumps(p, ensure_ascii=False)[:500])
            shown = True
        mr = ((p.get('markets') or {}).get('match_result') or {})
        probs = {'1': mr.get('prob_home'), 'X': mr.get('prob_draw'), '2': mr.get('prob_away')}
        if None in probs.values():
            continue
        pred = max(probs, key=lambda k: probs[k])
        # Bzzoiro-hjemmehold kan være byttet ift. vores
        sc, sw = pair_match(m['home_team'], m['away_team'], ev.get('home_team', ''), ev.get('away_team', ''))
        if sw:
            pred = {'1': '2', '2': '1', 'X': 'X'}[pred]
        n += 1
        hit += (pred == m['result'])
        try:
            if pd.Timestamp(p.get('created_at')) < pd.Timestamp(ev.get('event_date')):
                pre_ko += 1
        except Exception:
            pass
        fl = plog[(plog['round'] == m['round']) & (plog['match_code'] == m['match_code'])]
        fav = fl['favourit'].iloc[0] if len(fl) else None
        if pd.notna(fav):
            fav = str(int(float(fav))) if str(fav) not in ('X', 'x') else 'X'
            fav_n += 1
            fav_hit += (fav == m['result'])
    print(f'   Forudsigelser fundet: {n}   Lavet før kickoff: {pct(pre_ko, n)}')
    print(f'   Bzzoiro træfprocent: {pct(hit, n)}')
    print(f'   Bookmakerfavorit (vores logbog) på de samme kampe: {pct(fav_hit, fav_n)}')

    # ── D. Odds ──────────────────────────────────────────────────────────
    print('\nD. Konsensus-odds (/events/{id}/odds/) vs. vores odds')
    diffs, n_odds, shown = [], 0, False
    targets = list(rows)
    # kommende kampe i aktuel runde
    for _, m in upcoming.iterrows():
        d0 = dt.date.fromisoformat(str(m['date'])[:10])
        best = (0, None, False)
        for ev in events_on(d0.isoformat()):
            sc, sw = pair_match(m['home_team'], m['away_team'], ev.get('home_team', ''), ev.get('away_team', ''))
            if sc > best[0]:
                best = (sc, ev, sw)
        print(f"   Kommende R{m['round']} {m['home_team']}–{m['away_team']}: "
              + (f"fundet ({best[1].get('home_team')}–{best[1].get('away_team')})" if best[1] else 'IKKE fundet'))
        if best[1]:
            targets.append((m, best[1], None, best[0]))
    for m, ev, _, _ in targets:
        if ev is None:
            continue
        r = get(f"{B}/events/{ev['id']}/odds/", H)
        if r is None or r.status_code != 200:
            continue
        j = r.json()
        if not shown:
            print('   (eksempel, forkortet): ' + json.dumps(j, ensure_ascii=False)[:400])
            shown = True
        o = j.get('odds') or {}
        if not o.get('home_win'):
            continue
        n_odds += 1
        oo = odds[(odds['round'] == m['round']) & (odds['match_code'] == m['match_code'])]
        if len(oo) and pd.notna(oo['odds_1'].iloc[0]):
            ours = (oo['odds_1'].iloc[0], oo['odds_x'].iloc[0], oo['odds_2'].iloc[0])
            sc, sw = pair_match(m['home_team'], m['away_team'], ev.get('home_team', ''), ev.get('away_team', ''))
            theirs = (o['home_win'], o['draw'], o['away_win'])
            if sw:
                theirs = theirs[::-1]
            diffs.append((m, ours, theirs))
        elif m['result'] not in ('1', 'X', '2'):
            print(f"     ➜ Odds hos Bzzoiro hvor VI mangler: R{m['round']} {m['home_team']}–{m['away_team']}: "
                  f"{o.get('home_win')}/{o.get('draw')}/{o.get('away_win')}")
    print(f'   Kampe med konsensus-odds: {n_odds}   heraf sammenlignelige med vores: {len(diffs)}')
    if diffs:
        same_fav = sum(1 for _, a, b in diffs if min(range(3), key=lambda i: a[i]) == min(range(3), key=lambda i: b[i]))
        mad = sum(abs(1/a[i] - 1/b[i]) for _, a, b in diffs for i in range(3)) / (3 * len(diffs))
        print(f'   Samme favorit: {pct(same_fav, len(diffs))}   Gns. forskel i implicit sandsynlighed: {100*mad:.1f} %-point')
        for m, a, b in diffs[-12:]:
            print(f"     R{m['round']} {m['match_code']}: vores {a[0]:.2f}/{a[1]:.2f}/{a[2]:.2f}  Bzzoiro {b[0]:.2f}/{b[1]:.2f}/{b[2]:.2f}")


# ══════════════════════════════════════════════════════════════════════════
def test_pitchapi(key):
    print('\n' + '═' * 78 + '\nPITCHAPI (api.pitchapi.dev/v1)\n' + '═' * 78)
    B = 'https://api.pitchapi.dev/v1'
    H = {'X-API-KEY': key}
    r = get(f'{B}/leagues', H)
    if r is None or r.status_code != 200:
        print(f'  ✗ /leagues fejlede: {getattr(r, "status_code", "?")} {getattr(r, "text", "")[:300]}')
        return
    j = r.json()
    print('   (rå /leagues, forkortet): ' + json.dumps(j, ensure_ascii=False)[:800])
    for path in ['/matches', '/matches/date/' + str(played['date'].iloc[-1])[:10]]:
        r = get(B + path, H, {'date': str(played['date'].iloc[-1])[:10]})
        print(f'   {path}: {getattr(r, "status_code", "?")} ' + (r.text[:800] if r is not None else ''))


if __name__ == '__main__':
    bz = os.environ.get('BZZOIRO_TOKEN', '').strip()
    pk = os.environ.get('PITCHAPI_KEY', '').strip()
    print(f'Sæson {SEASON}: {len(played)} afgjorte kampe, {len(upcoming)} uafgjorte')
    if bz:
        test_bzzoiro(bz)
    else:
        print('\nBZZOIRO: sprunget over (ingen BZZOIRO_TOKEN)')
    if pk:
        test_pitchapi(pk)
    else:
        print('\nPITCHAPI: sprunget over (ingen PITCHAPI_KEY)')
    print(f"\nAPI-kald i alt: {calls['n']}  (429-svar: {calls['429']}, netværksfejl: {calls['err']})")
