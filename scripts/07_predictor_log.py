#!/usr/bin/env python3
"""
07_predictor_log.py — Logbog over predictorernes bud pr. kamp (data/predictor_log.csv).

odds.csv overskrives løbende, så modelbud (n20, ensemble, Odds-MC, Poisson ...)
for afsluttede runder går tabt. Denne logbog tager et øjebliksbillede af hver
kamps predictor-felter, så længe kampen IKKE er gået i gang, og fryser rækken
ved kickoff. Dermed kan predictorerne evalueres bagefter uden at efterrationa-
liserede tal (fx opdateret efter kampen) sniger sig med.

Regler:
  - Før kickoff (kickoff = weekly_matches date+time, dansk tid): rækken opdateres
    med nyeste ikke-tomme værdier fra odds.csv; tomme felter overskriver ikke.
  - Efter kickoff: rækken røres ikke (frosset).
  - Ukendt kickoff: opdateres kun så længe kampen ikke har et resultat.

Logbogen blev startet med data genskabt fra git-historikken af odds.csv
(kilde='git'); nye snapshots har kilde='live'.

Kan køres standalone (python scripts/07_predictor_log.py) og kaldes desuden
fra 08_dashboard.py, så den kører ved hver pipeline-kørsel.
"""
import os, sys
import pandas as pd

LOG_FIELDS = [
    'odds_1', 'odds_x', 'odds_2', 'prob_1', 'prob_2', 'favourit', 'rec_regel', 'rec_lr', 'rec_bzz',
    'elo_home', 'elo_away', 'opta_home', 'opta_away',
    'n20_prob_1', 'n20_prob_x', 'n20_prob_2', 'n20_rec',
    'poisson_p1', 'poisson_px', 'poisson_p2', 'rec_poisson',
    'odds_mc_p1', 'odds_mc_px', 'odds_mc_p2', 'rec_odds_mc',
    'rec_ensemble', 'ensemble_conf', 'ensemble_p1', 'ensemble_px', 'ensemble_p2',
    'bzz_p1', 'bzz_px', 'bzz_p2', 'odds_src',
]
KEY = ['season', 'round', 'match_code']
COLS = KEY + LOG_FIELDS + ['kilde', 'logged_at']


def _kickoffs(wm):
    ko = pd.to_datetime(wm['date'].astype(str) + ' ' + wm['time'].fillna('').astype(str),
                        format='mixed', errors='coerce')
    try:
        ko = ko.dt.tz_localize('Europe/Copenhagen', ambiguous='NaT', nonexistent='NaT').dt.tz_convert('UTC')
    except Exception:
        ko = pd.Series(pd.NaT, index=wm.index)
    return ko


def update_log(data_dir, now=None):
    """Opdater predictor_log.csv ud fra odds.csv. Returnerer antal opdaterede kampe."""
    odds_p = os.path.join(data_dir, 'odds.csv')
    wm_p = os.path.join(data_dir, 'weekly_matches.csv')
    log_p = os.path.join(data_dir, 'predictor_log.csv')
    if not (os.path.exists(odds_p) and os.path.exists(wm_p)):
        return 0
    now = now or pd.Timestamp.now(tz='UTC')
    od = pd.read_csv(odds_p)
    wm = pd.read_csv(wm_p)
    for d in (od, wm):
        d['season'] = pd.to_numeric(d['season'], errors='coerce')
        d['round'] = pd.to_numeric(d['round'], errors='coerce')
    wm['_ko'] = _kickoffs(wm)
    wm['_res'] = wm['result'].astype(str).str.strip().isin(['1', 'X', '2'])
    od = od.merge(wm[KEY + ['_ko', '_res']], on=KEY, how='left')

    log = pd.read_csv(log_p) if os.path.exists(log_p) else pd.DataFrame(columns=COLS)
    for c in COLS:
        if c not in log.columns:
            log[c] = None
    log = log.astype({c: object for c in LOG_FIELDS + ['kilde', 'logged_at']})
    idx = {(int(r.season), int(r['round']), r.match_code): i for i, r in log.iterrows()}

    n = 0
    stamp = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    for _, r in od.iterrows():
        if pd.isna(r['season']) or pd.isna(r['round']):
            continue
        open_ = (now < r['_ko']) if pd.notna(r['_ko']) else not bool(r['_res'])
        if not open_:
            continue  # kampen er gået i gang / afgjort → frys
        vals = {c: r[c] for c in LOG_FIELDS if c in od.columns and pd.notna(r[c])}
        if not vals:
            continue
        k = (int(r['season']), int(r['round']), r['match_code'])
        if k in idx:
            i = idx[k]
            for c, v in vals.items():
                log.at[i, c] = v
            log.at[i, 'kilde'] = 'live'
            log.at[i, 'logged_at'] = stamp
        else:
            row = {c: None for c in COLS}
            row.update({'season': k[0], 'round': k[1], 'match_code': k[2], 'kilde': 'live', 'logged_at': stamp})
            row.update(vals)
            log = pd.concat([log, pd.DataFrame([row])], ignore_index=True)
            idx[k] = len(log) - 1
        n += 1

    log = log[COLS].sort_values(KEY).reset_index(drop=True)
    log['season'] = log['season'].astype(int)
    log['round'] = log['round'].astype(int)
    log.to_csv(log_p, index=False)
    return n


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    n = update_log(os.path.join(root, 'data'))
    print(f'✓ predictor_log.csv: {n} kampe opdateret (før kickoff)')
