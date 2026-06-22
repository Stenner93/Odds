#!/usr/bin/env python3
"""
06_mapping_update.py — Opdaterer hold_mapping.json med nye holdnavne fra weekly_matches.csv.

For hvert hold i aktuel runde:
  ≥ 90%  fuzzy-score → tilføj som alias (samme abbr som det matchende hold)
  70-89% fuzzy-score → advar om mulig dublet, opret nyt entry
  < 70%  fuzzy-score → opret nyt entry med auto-genereret forkortelse

Scriptet er sikkert at køre flere gange — det springer over allerede kendte hold.
"""
import json, os, sys
import pandas as pd
from rapidfuzz import process, fuzz
from unidecode import unidecode

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CURRENT_SEASON, MATCHES_CSV, DATA_DIR, get_current_round

HOLD_MAP_PATH = os.path.join(DATA_DIR, 'hold_mapping.json')
CURRENT_ROUND = get_current_round()

# ── Indlæs hold_mapping.json ──────────────────────────────────────────────
with open(HOLD_MAP_PATH, encoding='utf-8') as f:
    mapping: list = json.load(f)

def _norm(s: str) -> str:
    return unidecode(str(s)).lower().strip()

# Byg normaliseret opslag: norm_navn → indeks
_idx: dict[str, int] = {}
for i, e in enumerate(mapping):
    for key in ('name', 'elo_name'):
        n = _norm(e.get(key, ''))
        if n and n not in _idx:
            _idx[n] = i
_all_norms = list(_idx.keys())

# ── Generer unik 3-bogstavs forkortelse ──────────────────────────────────
_used_abbrs = {e.get('abbr', '').upper() for e in mapping if e.get('abbr')}

def _make_abbr(name: str) -> str:
    words = unidecode(name).upper().split()
    skip = {'FC', 'BK', 'IF', 'FK', 'SK', 'IK', 'AC', 'AFC', 'IFK', 'AEK', 'AS', 'SS'}
    content_words = [w for w in words if w not in skip] or words
    candidates = []
    if len(content_words) >= 3:
        candidates.append(''.join(w[0] for w in content_words[:3]))
    if len(content_words) >= 2:
        candidates.append(content_words[0][:2] + content_words[1][0])
        candidates.append(content_words[0][:3])
    if content_words:
        candidates.append(content_words[0][:3])
    for c in candidates:
        c3 = c[:3]
        if len(c3) == 3 and c3 not in _used_abbrs:
            _used_abbrs.add(c3)
            return c3
    # Fallback med nummer
    base = (candidates[0][:2] if candidates else name[:2].upper())
    for i in range(1, 20):
        attempt = f'{base}{i}'[:3]
        if attempt not in _used_abbrs:
            _used_abbrs.add(attempt)
            return attempt
    return name[:3].upper()

# ── Find hold der mangler i mapping ──────────────────────────────────────
df = pd.read_csv(MATCHES_CSV)
df['season'] = df['season'].astype(int)
df['round']  = df['round'].astype(int)
df_rnd = df[(df['season'] == CURRENT_SEASON) & (df['round'] == CURRENT_ROUND)]

if df_rnd.empty:
    print(f'⚠ Ingen kampe for S{CURRENT_SEASON}R{CURRENT_ROUND} — kør 01_kampe.py først')
    sys.exit(0)

teams = {str(t) for col in ('home_team', 'away_team') for t in df_rnd[col] if t and str(t) not in ('', 'nan')}
new_entries: list = []
warnings: list = []

print(f'📋 Tjekker {len(teams)} hold fra S{CURRENT_SEASON}R{CURRENT_ROUND} mod hold_mapping.json...')

for team in sorted(teams):
    n = _norm(team)
    if n in _idx:
        continue  # Allerede kendt

    # Fuzzy match mod alle kendte navne
    hit = process.extractOne(n, _all_norms, scorer=fuzz.token_sort_ratio)
    score = hit[1] if hit else 0
    best_norm = hit[0] if hit else None

    if score >= 90:
        # Høj sikkerhed → alias til eksisterende
        existing = mapping[_idx[best_norm]]
        print(f'  🔗 ALIAS  "{team}" → "{existing["name"]}" ({score:.0f}%) — abbr: {existing["abbr"]}')
        new_entries.append({
            'abbr':     existing['abbr'],
            'type':     existing.get('type', 'INT'),
            'land':     existing.get('land', 'INT'),
            'name':     team,
            'elo_name': existing.get('elo_name', team),
        })

    elif score >= 70:
        # Mulig dublet — advarer men opretter stadig nyt entry
        existing = mapping[_idx[best_norm]]
        warnings.append(
            f'  ⚠ "{team}" ligner "{existing["name"]}" ({score:.0f}%) '
            f'— tjek om det er samme hold (abbr: {existing["abbr"]})'
        )
        abbr = _make_abbr(team)
        new_entries.append({
            'abbr': abbr, 'type': 'INT', 'land': 'INT',
            'name': team, 'elo_name': team,
        })
        print(f'  ➕ NYT    "{team}" → abbr: {abbr} (mulig dublet med "{existing["name"]}")')

    else:
        abbr = _make_abbr(team)
        new_entries.append({
            'abbr': abbr, 'type': 'INT', 'land': 'INT',
            'name': team, 'elo_name': team,
        })
        print(f'  ➕ NYT    "{team}" → abbr: {abbr}')

    # Opdater lokal opslag så næste hold kan matche mod det nye
    _idx[n] = len(mapping) + len(new_entries) - 1
    _all_norms.append(n)

if warnings:
    print('\nAdvarsler (overvej om det er dubletter):')
    print('\n'.join(warnings))

aliased = sum(1 for e in new_entries if e['elo_name'] != e['name'] or
              any(x['name'] == e['elo_name'] for x in mapping))
added   = len(new_entries) - aliased

if new_entries:
    mapping.extend(new_entries)
    mapping.sort(key=lambda e: _norm(e.get('name', '')))
    with open(HOLD_MAP_PATH, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f'\n✅ {len(new_entries)} nye entries tilføjet til hold_mapping.json '
          f'({aliased} aliaser, {added} helt nye hold)')
else:
    print(f'\n✅ Alle {len(teams)} hold kendes allerede — ingen ændringer')
