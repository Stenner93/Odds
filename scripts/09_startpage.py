#!/usr/bin/env python3
"""
09_startpage.py — Genererer den kompakte startside (index.html).

Startsiden samler de tre ting der bruges mest, på én skærm:
  1. Din H2H-kamp (fokus-spilleren) i den seneste H2H-runde
  2. Næste runde (kommende kampe + odds)
  3. Samlet stilling (top + fokus-spilleren fremhævet)

Det fulde dashboard skrives af 08_dashboard.py til dashboard.html og linkes
fra startsiden. Temaet matcher dashboard_template.html (mørkt, grøn accent,
1=blå / X=grå / 2=rød).

Kører efter 05_standings.py i pipelinen. Læser kun CSV'er — ingen netværk.
"""
import os, sys, html
import pandas as pd

# ── Konfiguration ─────────────────────────────────────────────────────────
FOCUS_PLAYER   = 'Anders Stenner'   # spilleren startsiden er bygget til
CURRENT_SEASON = 4
AFD_SIZE       = 17
STANDINGS_TOP  = 5                   # antal toprækker i stilling-kortet

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(REPO_ROOT, 'data')

MATCHES_CSV     = os.path.join(DATA_DIR, 'weekly_matches.csv')
ODDS_CSV        = os.path.join(DATA_DIR, 'odds.csv')
H2H_CSV         = os.path.join(DATA_DIR, 'h2h.csv')
PREDICTIONS_CSV = os.path.join(DATA_DIR, 'predictions.csv')
STANDINGS_CSV   = os.path.join(DATA_DIR, 'standings.csv')
OUTPUT_PATH     = os.path.join(REPO_ROOT, 'index.html')

def _norm_bet(v):
    if v is None: return None
    s = str(v).strip()
    if s.lower() in ('nan', 'none', ''): return None
    if s in ('1', '1.0'): return '1'
    if s in ('9', '9.0', 'x', 'X'): return 'X'
    if s in ('2', '2.0'): return '2'
    return None

def _num(v):
    """Odds som pæn streng, ellers None."""
    try:
        f = float(v)
        if f != f: return None
        return ('%g' % f)
    except (TypeError, ValueError):
        return None

def _afd_label(r):
    afd = (r - 1) // AFD_SIZE + 1
    rel = r - (afd - 1) * AFD_SIZE
    return afd, rel

def esc(s):
    return html.escape(str(s))

# ── Indlæs data ───────────────────────────────────────────────────────────
wm = pd.read_csv(MATCHES_CSV)
wm['season'] = wm['season'].astype(int); wm['round'] = wm['round'].astype(int)
wm_s = wm[wm['season'] == CURRENT_SEASON]
if wm_s.empty:
    print('❌ Ingen kampe for aktuel sæson'); sys.exit(1)

odds = pd.read_csv(ODDS_CSV)
odds['season'] = odds['season'].astype(int); odds['round'] = odds['round'].astype(int)

preds = pd.read_csv(PREDICTIONS_CSV)
preds['season'] = preds['season'].astype(int); preds['round'] = preds['round'].astype(int)

stand = pd.read_csv(STANDINGS_CSV)
stand = stand[stand['season'].astype(int) == CURRENT_SEASON].sort_values('pos')

h2h = pd.read_csv(H2H_CSV)
h2h['season'] = h2h['season'].astype(int); h2h['round'] = h2h['round'].astype(int)

# ── Bestem runder ─────────────────────────────────────────────────────────
next_round = int(wm_s['round'].max())

_h2h_focus = h2h[(h2h['season'] == CURRENT_SEASON) &
                 ((h2h['player_a'] == FOCUS_PLAYER) | (h2h['player_b'] == FOCUS_PLAYER))]
h2h_round = int(_h2h_focus['round'].max()) if not _h2h_focus.empty else None

print(f'Startside: næste runde = {next_round}, H2H-runde ({FOCUS_PLAYER}) = {h2h_round}')

# ── Byg: Næste runde ──────────────────────────────────────────────────────
fx = wm_s[wm_s['round'] == next_round].sort_values('match_no')
odds_nr = odds[(odds['season'] == CURRENT_SEASON) & (odds['round'] == next_round)]
odds_map = {r['match_code']: r for _, r in odds_nr.iterrows()}

next_rows = []
for _, m in fx.iterrows():
    o = odds_map.get(m['match_code'])
    o1 = _num(o['odds_1']) if o is not None else None
    ox = _num(o['odds_x']) if o is not None else None
    o2 = _num(o['odds_2']) if o is not None else None
    next_rows.append({
        'home': m['home_team'], 'away': m['away_team'],
        'o1': o1, 'ox': ox, 'o2': o2,
    })

# ── Byg: H2H ──────────────────────────────────────────────────────────────
h2h_block = None
if h2h_round is not None:
    pr = _h2h_focus[_h2h_focus['round'] == h2h_round].iloc[0]
    me_is_a = (pr['player_a'] == FOCUS_PLAYER)
    opp = pr['player_b'] if me_is_a else pr['player_a']

    def _val(col_a, col_b):
        v = pr[col_a] if me_is_a else pr[col_b]
        return v
    cor_me  = _val('correct_a', 'correct_b')
    cor_opp = _val('correct_b', 'correct_a')
    pts_me  = _val('h2h_pts_a', 'h2h_pts_b')
    pts_opp = _val('h2h_pts_b', 'h2h_pts_a')

    hm = wm_s[wm_s['round'] == h2h_round].sort_values('match_no')
    res_map = {}
    for _, m in hm.iterrows():
        rv = m['result']
        res_map[m['match_code']] = (str(rv).strip() if isinstance(rv, str) and str(rv).strip() else None)

    def _bets_for(player):
        d = preds[(preds['season'] == CURRENT_SEASON) & (preds['round'] == h2h_round) &
                  (preds['player'] == player)]
        return {r['match_code']: _norm_bet(r['bet']) for _, r in d.iterrows()}
    my_bets  = _bets_for(FOCUS_PLAYER)
    opp_bets = _bets_for(opp)

    rows = []
    played = 0
    for _, m in hm.iterrows():
        mc = m['match_code']
        res = res_map.get(mc)
        if res: played += 1
        rows.append({
            'label': f"{m['home_team']}–{m['away_team']}",
            'res': res, 'me': my_bets.get(mc), 'opp': opp_bets.get(mc),
        })

    complete = (played == len(rows) and len(rows) > 0)
    if complete and pts_me is not None and pts_me == pts_me:
        if pts_me > pts_opp:   outcome = ('vandt', 'win')
        elif pts_me < pts_opp: outcome = ('tabte', 'loss')
        else:                  outcome = ('uafgjort', 'draw')
    else:
        outcome = None

    def _ic(v):
        try: return int(v) if v == v else 0
        except (TypeError, ValueError): return 0

    h2h_block = {
        'opp': opp, 'me_correct': _ic(cor_me), 'opp_correct': _ic(cor_opp),
        'pts_me': _ic(pts_me), 'pts_opp': _ic(pts_opp),
        'played': played, 'total': len(rows), 'complete': complete,
        'outcome': outcome, 'rows': rows,
    }

# ── Byg: Stilling ─────────────────────────────────────────────────────────
st_rows = []
focus_rank = None
for _, r in stand.iterrows():
    pos = int(r['pos'])
    is_focus = (r['player'] == FOCUS_PLAYER)
    if is_focus: focus_rank = pos
    st_rows.append({
        'pos': pos, 'player': r['player'],
        'h2h': int(r['total_h2h_pts']) if pd.notna(r['total_h2h_pts']) else 0,
        'cor': int(r['total_correct']) if pd.notna(r['total_correct']) else 0,
        'focus': is_focus,
    })
rounds_played = int(stand['rounds_played'].iloc[0]) if not stand.empty else 0

# Kompakt udvalg: top N + fokus-spiller (+ nabo) hvis udenfor top N
sel = st_rows[:STANDINGS_TOP]
if focus_rank and focus_rank > STANDINGS_TOP:
    extra = [x for x in st_rows if x['pos'] in (focus_rank - 1, focus_rank, focus_rank + 1)]
    sel = st_rows[:STANDINGS_TOP] + [{'gap': True}] + extra
# afstand til top 3
gap_txt = ''
if focus_rank:
    top3 = st_rows[2]['h2h'] if len(st_rows) >= 3 else None
    me = next((x['h2h'] for x in st_rows if x.get('focus')), None)
    if top3 is not None and me is not None and focus_rank > 3:
        gap_txt = f"{top3 - me} point op til top 3"
    elif focus_rank <= 3:
        gap_txt = f"nr. {focus_rank} — i top 3"

# ═══════════════════════════════════════════════════════════════════════════
# RENDER
# ═══════════════════════════════════════════════════════════════════════════
PICK_CLASS = {'1': 'p1', 'X': 'px', '2': 'p2'}

def pick_chip(bet, cls_extra=''):
    if not bet:
        return '<span class="pk pkghost">–</span>'
    return f'<span class="pk {PICK_CLASS[bet]}{cls_extra}">{bet}</span>'

def andpick(bet, res):
    if not bet:
        return '<span class="pk pkghost">–</span>'
    chip = f'<span class="pk {PICK_CLASS[bet]}">{bet}</span>'
    if res:
        tick = '<b class="tk ok">✓</b>' if bet == res else '<b class="tk no">✗</b>'
        return f'<span class="apw">{chip}{tick}</span>'
    return chip

# — Næste runde rækker —
nr_html = []
for r in next_rows:
    if r['o1'] and r['ox'] and r['o2']:
        try:
            vals = [float(r['o1']), float(r['ox']), float(r['o2'])]
            best = vals.index(min(vals))
        except ValueError:
            best = -1
        cells = ''.join(
            f'<span class="od{" best" if i == best else ""}">{v}</span>'
            for i, v in enumerate([r['o1'], r['ox'], r['o2']])
        )
        right = f'<div class="odds">{cells}</div>'
    else:
        right = '<span class="wait">afventer</span>'
    nr_html.append(
        f'<div class="fx-row"><div class="tm"><span class="t">{esc(r["home"])}</span>'
        f'<span class="t away">{esc(r["away"])}</span></div>{right}</div>'
    )
nr_html = '\n'.join(nr_html)
nr_afd, nr_rel = _afd_label(next_round)

# — H2H —
if h2h_block:
    b = h2h_block
    ha, hrel = _afd_label(h2h_round)
    if b['outcome']:
        verb, cls = b['outcome']
        badge = f'<span class="h2h-badge {cls}">{verb} {b["pts_me"]}–{b["pts_opp"]}</span>'
        meta  = 'afsluttet'
    else:
        badge = '<span class="h2h-badge live">i gang</span>'
        meta  = f'{b["played"]}/{b["total"]} spillet'
    focus_sub = f'{b["me_correct"]} rigtige' + (f' · nr. {focus_rank}' if focus_rank else '')
    grid = []
    for row in b['rows']:
        res = row['res']
        res_cell = f'<span class="res">{res}</span>' if res else '<span class="res pd">·</span>'
        grid.append(
            f'<div class="g-row"><span class="gm">{esc(row["label"])}</span>'
            f'{res_cell}<span class="gc">{andpick(row["me"], res)}</span>'
            f'<span class="gc">{andpick(row["opp"], res)}</span></div>'
        )
    grid = '\n'.join(grid)
    opp_short = esc(b['opp'])
    h2h_html = f'''
      <section class="card">
        <div class="c-head"><span class="c-title"><span class="bar"></span>Din H2H · runde {h2h_round}</span><span class="c-meta">{meta}</span></div>
        <div class="h2h-score">
          <div class="h2h-p me"><div class="nm">{esc(FOCUS_PLAYER)}</div><div class="sub">{focus_sub}</div></div>
          <div class="h2h-mid"><div class="h2h-vs"><span class="win">{b['me_correct']}</span><span class="sep">–</span><span>{b['opp_correct']}</span></div>{badge}</div>
          <div class="h2h-p r"><div class="nm">{opp_short}</div><div class="sub">{b['opp_correct']} rigtige</div></div>
        </div>
        <div class="grid">
          <div class="g-row head"><span>Runde {h2h_round} · afd. {ha}, {hrel}. runde</span><span class="gc">R</span><span class="gc">{esc(FOCUS_PLAYER.split()[0])}</span><span class="gc">Mod.</span></div>
          {grid}
        </div>
      </section>'''
else:
    h2h_html = '<section class="card"><div class="c-head"><span class="c-title"><span class="bar"></span>Din H2H</span></div><div class="empty">Ingen H2H-runde fundet for ' + esc(FOCUS_PLAYER) + ' endnu.</div></section>'

# — Stilling —
st_html = []
for x in sel:
    if x.get('gap'):
        st_html.append('<div class="s-row gap"><span>⋯</span></div>')
        continue
    cls = ' me' if x['focus'] else ''
    pcls = ' p1cls' if x['pos'] == 1 else (' p2cls' if x['pos'] == 2 else (' p3cls' if x['pos'] == 3 else ''))
    st_html.append(
        f'<div class="s-row{cls}"><span class="s-pos{pcls}">{x["pos"]}</span>'
        f'<span class="s-nm">{esc(x["player"])}</span>'
        f'<span class="s-pts">{x["h2h"]}</span><span class="s-cor">{x["cor"]}</span></div>'
    )
st_html = '\n'.join(st_html)

page = f'''<!doctype html>
<html lang="da">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Oddsklub</title>
<style>
:root{{--bg:#111827;--sf:#1a2235;--card:#1f2937;--bdr:#374151;--grn:#22c55e;--gld:#f59e0b;--red:#ef4444;--blu:#3b82f6;--pur:#a78bfa;--txt:#f9fafb;--mut:#9ca3af;--rad:12px}}
*{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;background:var(--bg);color:var(--txt);font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased}}
header{{background:var(--card);border-bottom:1px solid var(--bdr);padding:0 16px;display:flex;align-items:center;justify-content:space-between;gap:12px;height:56px;position:sticky;top:0;z-index:100}}
.logo{{font-weight:800;font-size:19px;letter-spacing:-.01em}}
.logo span{{color:var(--grn)}}
.to-dash{{text-decoration:none;background:rgba(34,197,94,.1);color:var(--grn);border:1px solid rgba(34,197,94,.25);border-radius:8px;padding:7px 12px;font-size:12px;font-weight:600;white-space:nowrap}}
.to-dash:hover{{background:rgba(34,197,94,.16)}}
main{{max-width:520px;margin:0 auto;padding:14px 14px 40px;display:flex;flex-direction:column;gap:14px}}
.card{{background:var(--card);border:1px solid var(--bdr);border-radius:var(--rad);overflow:hidden}}
.c-head{{display:flex;align-items:center;justify-content:space-between;padding:10px 13px;border-bottom:1px solid var(--bdr)}}
.c-title{{display:flex;align-items:center;gap:8px;font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--mut)}}
.c-title .bar{{width:3px;height:13px;border-radius:2px;background:var(--grn)}}
.c-meta{{font-size:11px;font-weight:600;color:var(--mut)}}
.empty{{padding:16px 13px;color:var(--mut);font-size:13px}}
/* 1X2 chips: 1=blå, X=grå, 2=rød (som dashboard) */
.pk{{display:inline-grid;place-items:center;min-width:21px;height:21px;padding:0 5px;border-radius:5px;font-size:11px;font-weight:700;color:#fff;font-variant-numeric:tabular-nums}}
.pk.p1{{background:var(--blu)}}.pk.px{{background:#4b5563}}.pk.p2{{background:var(--red)}}
.pk.pkghost{{background:transparent;color:var(--mut);border:1px dashed var(--bdr)}}
.apw{{display:inline-flex;align-items:center;justify-content:center;gap:4px}}
.tk{{font-size:11px;font-weight:800}}.tk.ok{{color:var(--grn)}}.tk.no{{color:var(--red)}}
/* Næste runde */
.fx-row{{display:grid;grid-template-columns:1fr auto;align-items:center;gap:10px;padding:9px 13px;border-top:1px solid var(--bdr)}}
.fx-row:first-child{{border-top:0}}
.tm{{min-width:0;font-size:13px;line-height:1.3}}
.tm .t{{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.tm .away{{color:var(--mut)}}
.odds{{display:flex;gap:4px}}
.od{{font-size:11px;font-weight:600;color:var(--mut);background:var(--sf);border:1px solid var(--bdr);border-radius:5px;padding:5px 6px;min-width:34px;text-align:center;font-variant-numeric:tabular-nums}}
.od.best{{color:var(--txt);border-color:rgba(34,197,94,.4);background:rgba(34,197,94,.1);font-weight:700}}
.wait{{font-size:10.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--mut);border:1px dashed var(--bdr);border-radius:6px;padding:5px 8px}}
/* H2H */
.h2h-score{{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 13px;background:var(--sf)}}
.h2h-p{{flex:1;min-width:0}}
.h2h-p .nm{{font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.h2h-p.me .nm{{color:var(--grn)}}
.h2h-p.r{{text-align:right}}
.h2h-p .sub{{font-size:10.5px;color:var(--mut)}}
.h2h-mid{{display:flex;flex-direction:column;align-items:center;gap:5px;flex-shrink:0}}
.h2h-vs{{display:flex;align-items:baseline;gap:6px;font-weight:800;font-size:28px;line-height:.8;font-variant-numeric:tabular-nums}}
.h2h-vs .sep{{font-size:14px;color:var(--mut);font-weight:500}}
.h2h-vs .win{{color:var(--grn)}}
.h2h-badge{{font-size:9px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;border-radius:5px;padding:3px 6px;white-space:nowrap}}
.h2h-badge.win{{background:var(--grn);color:#08130d}}
.h2h-badge.loss{{background:var(--red);color:#fff}}
.h2h-badge.draw{{background:#4b5563;color:#fff}}
.h2h-badge.live{{background:rgba(245,158,11,.15);color:var(--gld);border:1px solid rgba(245,158,11,.3)}}
.grid{{display:flex;flex-direction:column}}
.g-row{{display:grid;grid-template-columns:1fr 16px 42px 42px;align-items:center;gap:8px;padding:6px 13px;border-top:1px solid var(--bdr);font-size:12px}}
.g-row.head{{border-top:0;color:var(--mut);font-size:9.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding-top:9px;padding-bottom:7px}}
.g-row .gm{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--mut)}}
.gc{{display:grid;place-items:center}}
.res{{font-size:11px;font-weight:700;text-align:center;font-variant-numeric:tabular-nums}}
.res.pd{{color:var(--mut)}}
/* Stilling */
.stand{{display:flex;flex-direction:column}}
.s-row{{display:grid;grid-template-columns:24px 1fr auto auto;align-items:center;gap:10px;padding:7px 13px;border-top:1px solid var(--bdr);font-size:12.5px}}
.s-row:first-child{{border-top:0}}
.s-row.head{{color:var(--mut);font-size:9.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:9px 13px 7px}}
.s-row.gap{{color:var(--mut);justify-items:start;padding:2px 13px;grid-template-columns:1fr}}
.s-row.me{{background:rgba(34,197,94,.08);box-shadow:inset 3px 0 0 var(--grn)}}
.s-row.me .s-nm{{color:var(--grn);font-weight:700}}
.s-pos{{font-weight:800;font-size:12px;color:var(--mut);text-align:center;font-variant-numeric:tabular-nums}}
.s-pos.p1cls{{color:var(--gld)}}.s-pos.p2cls{{color:#cbd5e1}}.s-pos.p3cls{{color:#d69e5b}}
.s-nm{{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.s-pts{{font-weight:800;font-size:13px;text-align:right;min-width:22px;font-variant-numeric:tabular-nums}}
.s-cor{{font-size:11px;color:var(--mut);text-align:right;min-width:22px;font-variant-numeric:tabular-nums}}
.s-foot{{padding:8px 13px;border-top:1px solid var(--bdr);font-size:10.5px;color:var(--mut);text-align:center}}
.s-foot b{{color:var(--txt)}}
.legend{{display:flex;flex-wrap:wrap;gap:10px 16px;color:var(--mut);font-size:11.5px;padding:2px 2px}}
.legend .it{{display:flex;align-items:center;gap:6px}}
.updated{{text-align:center;color:var(--mut);font-size:10.5px}}
</style>
</head>
<body>
<header>
  <div class="logo">Odds<span>klub</span></div>
  <a class="to-dash" href="dashboard.html">Fuldt dashboard →</a>
</header>
<main>

{h2h_html}

  <section class="card">
    <div class="c-head"><span class="c-title"><span class="bar"></span>Næste runde · {next_round}</span><span class="c-meta">afd. {nr_afd}, {nr_rel}. runde</span></div>
    <div class="grid">
      {nr_html}
    </div>
  </section>

  <section class="card">
    <div class="c-head"><span class="c-title"><span class="bar"></span>Stilling</span><span class="c-meta">efter {rounds_played} runder</span></div>
    <div class="stand">
      <div class="s-row head"><span class="s-pos">#</span><span>Spiller</span><span class="s-pts">H2H</span><span class="s-cor">Rgt</span></div>
      {st_html}
    </div>
    <div class="s-foot">{esc(gap_txt) + " · " if gap_txt else ""}<b>Se fuld stilling</b> i dashboardet</div>
  </section>

  <div class="legend">
    <span class="it"><span class="pk p1">1</span> Hjemme</span>
    <span class="it"><span class="pk px">X</span> Uafgjort</span>
    <span class="it"><span class="pk p2">2</span> Ude</span>
    <span class="it">H2H = point · Rgt = rigtige</span>
  </div>
</main>
</body>
</html>'''

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write(page)
print(f'✅ index.html (startside) gemt ({len(page)//1024} KB) → {OUTPUT_PATH}')
