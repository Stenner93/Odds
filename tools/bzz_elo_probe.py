#!/usr/bin/env python3
"""Test (kun læsning): har Bzzoiro klub-ELO (teams.elo_rating), og hvor bred er dækningen?"""
import os, sys, json, requests
B = 'https://sports.bzzoiro.com/api/v2'
H = {'Authorization': f"Token {os.environ.get('BZZOIRO_TOKEN','').strip()}"}
def get(path, **p):
    r = requests.get(B + path, headers=H, params=p, timeout=30)
    print(f'  {path} {p} -> {r.status_code}')
    return r.json() if r.status_code == 200 else {}
j = get('/teams/', limit=3)
print('rå eksempel:', json.dumps(j, ensure_ascii=False)[:600])
LEAGUES = {1: 'Premier League', 12: 'Championship', 86: 'League One', 84: 'Superliga', 54: 'Eliteserien',
           26: 'Allsvenskan', 38: 'Segunda División', 3: 'La Liga', 11: 'Süper Lig', 7: 'Champions League'}
for lid, nm in LEAGUES.items():
    j = get('/teams/', league_id=lid, limit=200)
    rows = j.get('results', [])
    vals = [(t.get('name'), t.get('elo_rating', t.get('elo'))) for t in rows]
    have = [v for v in vals if v[1] is not None]
    print(f'{nm:<18} hold={len(rows):>3} med elo={len(have):>3}  eks: {sorted(have, key=lambda x: -x[1])[:3]} ... {sorted(have, key=lambda x: x[1])[:2]}')
# Samlet antal hold med ELO (paginer)
tot = have_tot = 0; off = 0
while off < 20000:
    j = get('/teams/', limit=200, offset=off)
    rows = j.get('results', [])
    if not rows: break
    tot += len(rows); have_tot += sum(1 for t in rows if t.get('elo_rating', t.get('elo')) is not None)
    if not j.get('next'): break
    off += 200
print(f'I alt: {tot} hold, {have_tot} med ELO')
