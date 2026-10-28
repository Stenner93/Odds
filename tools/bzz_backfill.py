#!/usr/bin/env python3
"""
tools/bzz_backfill.py — Engangs-backfill af Bzzoiros forudsigelser til
data/predictor_log.csv for afgjorte S4-kampe.

Kun forudsigelser der beviseligt er lavet FØR kickoff (created_at < event_date)
skrives, og kun i tomme felter — eksisterende værdier røres ikke.
Køres via workflowen "Bzzoiro-backfill" (BZZOIRO_TOKEN er en GitHub-secret).
"""
import os, sys, json
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from bzzoiro import Bzzoiro

DATA = os.path.join(ROOT, 'data')
SEASON = 4
FIELDS = ['rec_bzz', 'bzz_p1', 'bzz_px', 'bzz_p2']

_alias, _elo = {}, {}
try:
    _alias = json.load(open(os.path.join(DATA, 'odds_aliases.json'), encoding='utf-8'))
except Exception:
    pass
try:
    for r in json.load(open(os.path.join(DATA, 'hold_mapping.json'), encoding='utf-8')):
        if r.get('name') and r.get('elo_name'):
            _elo.setdefault(r['name'], r['elo_name'])
except Exception:
    pass

def variants(n):
    return [n, _elo.get(n), _alias.get(n), _alias.get(_elo.get(n, ''))]

token = os.environ.get('BZZOIRO_TOKEN', '').strip()
if not token:
    sys.exit('Ingen BZZOIRO_TOKEN')
bz = Bzzoiro(token, variants=variants)

wm = pd.read_csv(os.path.join(DATA, 'weekly_matches.csv'))
wm = wm[(wm['season'] == SEASON) & wm['result'].astype(str).str.strip().isin(['1', 'X', '2'])]
log_p = os.path.join(DATA, 'predictor_log.csv')
log = pd.read_csv(log_p)
for c in FIELDS:
    if c not in log.columns:
        log[c] = None
    log[c] = log[c].astype(object)
for c in ('kilde', 'logged_at'):
    log[c] = log[c].astype(object)

found = pre = written = created = skipped_post = 0
for _, m in wm.sort_values(['round', 'match_no']).iterrows():
    ev, sw = bz.find(m['home_team'], m['away_team'], str(m['date']))
    if not ev:
        continue
    found += 1
    j = bz._get(f"/events/{ev['id']}/prediction/")
    if not j:
        continue
    mr = ((j.get('markets') or {}).get('match_result') or {})
    p = [mr.get('prob_home'), mr.get('prob_draw'), mr.get('prob_away')]
    if None in p:
        continue
    try:
        ok_pre = pd.Timestamp(j['created_at']) < pd.Timestamp(ev['event_date'])
    except Exception:
        ok_pre = False
    if not ok_pre:
        skipped_post += 1
        continue
    pre += 1
    p1, px, p2 = (float(p[2]), float(p[1]), float(p[0])) if sw else (float(p[0]), float(p[1]), float(p[2]))
    rec = max(zip((p1, px, p2), ('1', 'X', '2')))[1]
    vals = dict(zip(FIELDS, [rec, round(p1, 1), round(px, 1), round(p2, 1)]))
    msk = (log['season'] == SEASON) & (log['round'] == m['round']) & (log['match_code'] == m['match_code'])
    if msk.any():
        i = log.index[msk][0]
        if all(pd.isna(log.at[i, c]) for c in FIELDS):
            for c, v in vals.items():
                log.at[i, c] = v
            written += 1
    else:
        row = {c: None for c in log.columns}
        row.update({'season': SEASON, 'round': int(m['round']), 'match_code': m['match_code'],
                    'kilde': 'bzzoiro-backfill', 'logged_at': str(j.get('created_at'))})
        row.update(vals)
        log = pd.concat([log, pd.DataFrame([row])], ignore_index=True)
        created += 1

log = log.sort_values(['season', 'round', 'match_code']).reset_index(drop=True)
log['season'] = log['season'].astype(int)
log['round'] = log['round'].astype(int)
log.to_csv(log_p, index=False)
print(f'Afgjorte S4-kampe: {len(wm)} | fundet hos Bzzoiro: {found} | forudsigelse før kickoff: {pre} '
      f'(afvist efter kickoff: {skipped_post})')
print(f'Skrevet i eksisterende rækker: {written} | nye rækker: {created} | API-kald: {bz.calls}')
