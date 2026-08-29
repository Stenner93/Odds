#!/usr/bin/env python3
"""
09_startpage.py — Bygger "Forside"-fanen til dashboardet.

Forsiden er en kompakt oversigt (din H2H-kamp, næste runde, samlet stilling)
der lever som den FØRSTE fane i dashboardets topbanner og er default-siden man
lander på. 08_dashboard.py importerer build_forside_pieces() og indsætter
stykkerne i den genererede HTML.

Layout er responsivt: én aflang kolonne på mobil, samlet i 2–3 kolonner på PC.
Temaet arves fra dashboardets :root (mørkt, grøn accent, 1=blå/X=grå/2=rød).
Alle CSS-klasser er scopet under #page-forside for ikke at kollidere med
dashboardets egne klasser.

Kan også køres standalone for at bygge en preview-fil:
    python scripts/09_startpage.py [output.html]
"""
import os, sys, html
from collections import defaultdict
import pandas as pd

FOCUS_PLAYER   = 'Anders Stenner'
CURRENT_SEASON = 4
AFD_SIZE       = 17
STANDINGS_TOP  = 6

def _norm_bet(v):
    if v is None: return None
    s = str(v).strip()
    if s.lower() in ('nan', 'none', ''): return None
    if s in ('1', '1.0'): return '1'
    if s in ('9', '9.0', 'x', 'X'): return 'X'
    if s in ('2', '2.0'): return '2'
    return None

def _num(v):
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

def _ic(v):
    try: return int(v) if v == v else 0
    except (TypeError, ValueError): return 0

# ═══════════════════════════════════════════════════════════════════════════
def build_forside_pieces(data_dir, focus_player=FOCUS_PLAYER):
    """Returnerer (style_html, nav_button_html, page_inner_html)."""
    MATCHES_CSV     = os.path.join(data_dir, 'weekly_matches.csv')
    ODDS_CSV        = os.path.join(data_dir, 'odds.csv')
    H2H_CSV         = os.path.join(data_dir, 'h2h.csv')
    PREDICTIONS_CSV = os.path.join(data_dir, 'predictions.csv')
    STANDINGS_CSV   = os.path.join(data_dir, 'standings.csv')

    wm = pd.read_csv(MATCHES_CSV)
    wm['season'] = wm['season'].astype(int); wm['round'] = wm['round'].astype(int)
    wm_s = wm[wm['season'] == CURRENT_SEASON]

    odds = pd.read_csv(ODDS_CSV)
    odds['season'] = odds['season'].astype(int); odds['round'] = odds['round'].astype(int)

    preds = pd.read_csv(PREDICTIONS_CSV)
    preds['season'] = preds['season'].astype(int); preds['round'] = preds['round'].astype(int)

    stand = pd.read_csv(STANDINGS_CSV)
    stand = stand[stand['season'].astype(int) == CURRENT_SEASON].sort_values('pos')

    h2h = pd.read_csv(H2H_CSV)
    h2h['season'] = h2h['season'].astype(int); h2h['round'] = h2h['round'].astype(int)

    next_round = int(wm_s['round'].max())
    _hf = h2h[(h2h['season'] == CURRENT_SEASON) &
              ((h2h['player_a'] == focus_player) | (h2h['player_b'] == focus_player))]
    h2h_round = int(_hf['round'].max()) if not _hf.empty else None

    # ── Næste runde ────────────────────────────────────────────────────────
    fx = wm_s[wm_s['round'] == next_round].sort_values('match_no')
    odds_map = {r['match_code']: r for _, r in
                odds[(odds['season'] == CURRENT_SEASON) & (odds['round'] == next_round)].iterrows()}
    next_rows = []
    for _, m in fx.iterrows():
        o = odds_map.get(m['match_code'])
        next_rows.append({
            'home': m['home_team'], 'away': m['away_team'],
            'o1': _num(o['odds_1']) if o is not None else None,
            'ox': _num(o['odds_x']) if o is not None else None,
            'o2': _num(o['odds_2']) if o is not None else None,
        })

    # ── H2H ────────────────────────────────────────────────────────────────
    h2h_block = None
    if h2h_round is not None:
        pr = _hf[_hf['round'] == h2h_round].iloc[0]
        me_a = (pr['player_a'] == focus_player)
        opp = pr['player_b'] if me_a else pr['player_a']
        pick = lambda a, b: (pr[a] if me_a else pr[b])
        hm = wm_s[wm_s['round'] == h2h_round].sort_values('match_no')
        res_map = {m['match_code']: (str(m['result']).strip()
                   if isinstance(m['result'], str) and str(m['result']).strip() else None)
                   for _, m in hm.iterrows()}
        def bets(p):
            d = preds[(preds['season'] == CURRENT_SEASON) & (preds['round'] == h2h_round) & (preds['player'] == p)]
            return {r['match_code']: _norm_bet(r['bet']) for _, r in d.iterrows()}
        mb, ob = bets(focus_player), bets(opp)

        # Odds-implicerede sandsynligheder pr. kamp (margin-normaliseret, som dashboardet)
        prob_map = {}
        for _, o in odds[(odds['season'] == CURRENT_SEASON) & (odds['round'] == h2h_round)].iterrows():
            try:
                p1 = float(o['prob_1']) / 100.0; p2 = float(o['prob_2']) / 100.0
                if p1 == p1 and p2 == p2:
                    prob_map[o['match_code']] = {'1': p1, '2': p2, 'X': max(0.0, 1 - p1 - p2)}
            except (TypeError, ValueError):
                pass

        rows, played, me_cor, opp_cor, diffs = [], 0, 0, 0, []
        for _, m in hm.iterrows():
            mc = m['match_code']; res = res_map.get(mc)
            a, b = mb.get(mc), ob.get(mc)
            if res:
                played += 1
                if a == res: me_cor += 1
                if b == res: opp_cor += 1
            elif a and b and a != b:
                # uafgjort kamp hvor de har gættet forskelligt → afgørende for H2H
                pm = prob_map.get(mc)
                if pm:
                    pa = pm.get(a, 0.0); pb = pm.get(b, 0.0); pn = max(0.0, 1 - pa - pb)
                else:
                    pa = pb = pn = 1.0 / 3     # ingen odds → uniform prior
                diffs.append((pa, pb, pn))
            rows.append({'label': f"{m['home_team']}–{m['away_team']}",
                         'res': res, 'me': a, 'opp': b})

        # DP: fordeling af (mine korrekte − modstanderens) over uafgjorte differens-kampe
        lead = me_cor - opp_cor
        dist = {lead: 1.0}
        for pa, pb, pn in diffs:
            nd = defaultdict(float)
            for d, p in dist.items():
                nd[d + 1] += p * pa
                nd[d - 1] += p * pb
                nd[d]     += p * pn
            dist = nd
        p_win  = round(sum(p for d, p in dist.items() if d > 0) * 100)
        p_tie  = round(sum(p for d, p in dist.items() if d == 0) * 100)
        p_loss = max(0, 100 - p_win - p_tie)

        complete = (played == len(rows) and len(rows) > 0)
        if complete:
            pts_me = _ic(pick('h2h_pts_a', 'h2h_pts_b')); pts_opp = _ic(pick('h2h_pts_b', 'h2h_pts_a'))
            if pts_me == 0 and pts_opp == 0 and me_cor != opp_cor:   # h2h.csv endnu ikke scoret
                pts_me, pts_opp = (3, 0) if me_cor > opp_cor else (0, 3)
            outcome = ('vandt', 'win') if pts_me > pts_opp else \
                      ('tabte', 'loss') if pts_me < pts_opp else ('uafgjort', 'draw')
        else:
            pts_me = pts_opp = 0
            outcome = None

        h2h_block = {'opp': opp, 'me_cor': me_cor, 'opp_cor': opp_cor,
                     'pts_me': pts_me, 'pts_opp': pts_opp, 'played': played,
                     'total': len(rows), 'outcome': outcome, 'rows': rows,
                     'p_win': p_win, 'p_tie': p_tie, 'p_loss': p_loss, 'n_open': len(diffs)}

    # ── Stilling ───────────────────────────────────────────────────────────
    st_rows, focus_rank = [], None
    for _, r in stand.iterrows():
        pos = int(r['pos']); is_f = (r['player'] == focus_player)
        if is_f: focus_rank = pos
        st_rows.append({'pos': pos, 'player': r['player'],
                        'h2h': int(r['total_h2h_pts']) if pd.notna(r['total_h2h_pts']) else 0,
                        'cor': int(r['total_correct']) if pd.notna(r['total_correct']) else 0,
                        'focus': is_f})
    rounds_played = int(stand['rounds_played'].iloc[0]) if not stand.empty else 0
    sel = st_rows[:STANDINGS_TOP]
    if focus_rank and focus_rank > STANDINGS_TOP:
        sel = st_rows[:STANDINGS_TOP] + [{'gap': True}] + \
              [x for x in st_rows if x['pos'] in (focus_rank - 1, focus_rank, focus_rank + 1)]
    gap_txt = ''
    if focus_rank:
        top3 = st_rows[2]['h2h'] if len(st_rows) >= 3 else None
        me = next((x['h2h'] for x in st_rows if x.get('focus')), None)
        if focus_rank <= 3:
            gap_txt = f'nr. {focus_rank} — i top 3'
        elif top3 is not None and me is not None:
            gap_txt = f'{top3 - me} point op til top 3'

    # ── Render helpers ─────────────────────────────────────────────────────
    PC = {'1': 'fs-p1', 'X': 'fs-px', '2': 'fs-p2'}
    def andpick(bet, res):
        if not bet: return '<span class="fs-pk fs-ghost">–</span>'
        chip = f'<span class="fs-pk {PC[bet]}">{bet}</span>'
        if res:
            tick = '<b class="fs-tk ok">✓</b>' if bet == res else '<b class="fs-tk no">✗</b>'
            return f'<span class="fs-apw">{chip}{tick}</span>'
        return chip

    # Næste runde
    nr = []
    for r in next_rows:
        if r['o1'] and r['ox'] and r['o2']:
            try:
                best = [float(r['o1']), float(r['ox']), float(r['o2'])]
                bi = best.index(min(best))
            except ValueError:
                bi = -1
            cells = ''.join(f'<span class="fs-od{" best" if i == bi else ""}">{v}</span>'
                            for i, v in enumerate([r['o1'], r['ox'], r['o2']]))
            right = f'<div class="fs-odds">{cells}</div>'
        else:
            right = '<span class="fs-wait">afventer</span>'
        nr.append(f'<div class="fs-fx"><div class="fs-tm"><span class="fs-t">{esc(r["home"])}</span>'
                  f'<span class="fs-t away">{esc(r["away"])}</span></div>{right}</div>')
    nr_html = '\n'.join(nr)
    nr_afd, nr_rel = _afd_label(next_round)

    # H2H
    if h2h_block:
        b = h2h_block; ha, hrel = _afd_label(h2h_round)
        if b['outcome']:
            verb, cls = b['outcome']
            badge = f'<span class="fs-badge {cls}">{verb} {b["pts_me"]}–{b["pts_opp"]}</span>'
            meta = 'afsluttet'
        else:
            badge = '<span class="fs-badge live">i gang</span>'
            meta = f'{b["played"]}/{b["total"]} spillet'
        sub = f'{b["me_cor"]} rigtige' + (f' · nr. {focus_rank}' if focus_rank else '')
        grows = []
        for x in b['rows']:
            res_cell = (f'<span class="fs-res">{x["res"]}</span>' if x['res']
                        else '<span class="fs-res pd">·</span>')
            grows.append(
                f'<div class="fs-grow"><span class="fs-gm">{esc(x["label"])}</span>'
                f'{res_cell}'
                f'<span class="fs-gc">{andpick(x["me"], x["res"])}</span>'
                f'<span class="fs-gc">{andpick(x["opp"], x["res"])}</span></div>')
        grid = '\n'.join(grows)
        first = esc(focus_player.split()[0])
        # Sandsynlighedsbjælke — vises mens runden er i gang og der er afgørende kampe tilbage
        prob_html = ''
        if not b['outcome'] and b['n_open'] > 0:
            opp_first = esc(b['opp'].split()[0])
            prob_html = f'''<div class="fs-prob">
    <div class="fs-prob-top"><span>Vinderchance · odds-baseret</span><span class="fs-prob-pct">{b["p_win"]}%</span></div>
    <div class="fs-prob-bar"><span class="w" style="width:{b["p_win"]}%"></span><span class="t" style="width:{b["p_tie"]}%"></span><span class="l" style="width:{b["p_loss"]}%"></span></div>
    <div class="fs-prob-lbl"><span>{first} {b["p_win"]}%</span><span>Uafgjort {b["p_tie"]}%</span><span>{opp_first} {b["p_loss"]}%</span></div>
  </div>'''
        h2h_html = f'''<section class="fs-card fs-h2h">
  <div class="fs-chead"><span class="fs-ctitle"><span class="fs-bar"></span>Din H2H · runde {h2h_round}</span><span class="fs-cmeta">{meta}</span></div>
  <div class="fs-h2hsc">
    <div class="fs-hp me"><div class="fs-nm">{esc(focus_player)}</div><div class="fs-sub">{sub}</div></div>
    <div class="fs-mid"><div class="fs-vs"><span class="win">{b["me_cor"]}</span><span class="sep">–</span><span>{b["opp_cor"]}</span></div>{badge}</div>
    <div class="fs-hp r"><div class="fs-nm">{esc(b["opp"])}</div><div class="fs-sub">{b["opp_cor"]} rigtige</div></div>
  </div>
  {prob_html}
  <div class="fs-g">
    <div class="fs-grow head"><span>Runde {h2h_round} · afd. {ha}, {hrel}. runde</span><span class="fs-gc">R</span><span class="fs-gc">{first}</span><span class="fs-gc">Mod.</span></div>
    {grid}
  </div>
</section>'''
    else:
        h2h_html = f'<section class="fs-card fs-h2h"><div class="fs-chead"><span class="fs-ctitle"><span class="fs-bar"></span>Din H2H</span></div><div class="fs-empty">Ingen H2H-runde for {esc(focus_player)} endnu.</div></section>'

    # Stilling
    st = []
    for x in sel:
        if x.get('gap'):
            st.append('<div class="fs-srow gap"><span>⋯</span></div>'); continue
        cls = ' me' if x['focus'] else ''
        pcls = ' r1' if x['pos'] == 1 else (' r2' if x['pos'] == 2 else (' r3' if x['pos'] == 3 else ''))
        st.append(f'<div class="fs-srow{cls}"><span class="fs-pos{pcls}">{x["pos"]}</span>'
                  f'<span class="fs-snm">{esc(x["player"])}</span>'
                  f'<span class="fs-spts">{x["h2h"]}</span><span class="fs-scor">{x["cor"]}</span></div>')
    st_html = '\n'.join(st)
    foot = (esc(gap_txt) + ' · ' if gap_txt else '') + '<b>Se fuld stilling</b> under fanen Stilling'

    next_html = f'''<section class="fs-card fs-next">
  <div class="fs-chead"><span class="fs-ctitle"><span class="fs-bar"></span>Næste runde · {next_round}</span><span class="fs-cmeta">afd. {nr_afd}, {nr_rel}. runde</span></div>
  <div class="fs-g">
    {nr_html}
  </div>
</section>'''

    stand_html = f'''<section class="fs-card fs-stilling">
  <div class="fs-chead"><span class="fs-ctitle"><span class="fs-bar"></span>Stilling</span><span class="fs-cmeta">efter {rounds_played} runder</span></div>
  <div class="fs-stand">
    <div class="fs-srow head"><span class="fs-pos">#</span><span>Spiller</span><span class="fs-spts">H2H</span><span class="fs-scor">Rgt</span></div>
    {st_html}
  </div>
  <div class="fs-foot">{foot}</div>
</section>'''

    page_inner = f'''<div class="fs-wrap">
  <div class="fs-grid">
    {h2h_html}
    {next_html}
    {stand_html}
  </div>
  <div class="fs-legend">
    <span class="fs-it"><span class="fs-pk fs-p1">1</span> Hjemme</span>
    <span class="fs-it"><span class="fs-pk fs-px">X</span> Uafgjort</span>
    <span class="fs-it"><span class="fs-pk fs-p2">2</span> Ude</span>
    <span class="fs-it">H2H = point · Rgt = rigtige</span>
  </div>
</div>'''

    nav_button = "<button class=\"active\" onclick=\"showPage('forside',this)\">Forside</button>"

    style = '''<style>
#page-forside{max-width:1180px;margin:0 auto}
#page-forside .fs-grid{display:grid;gap:14px;grid-template-columns:1fr}
@media(min-width:760px){#page-forside .fs-grid{grid-template-columns:1fr 1fr}#page-forside .fs-stilling{grid-column:1 / -1}}
@media(min-width:1160px){#page-forside .fs-grid{grid-template-columns:1.15fr 1.15fr .9fr}#page-forside .fs-stilling{grid-column:auto}}
#page-forside .fs-card{background:var(--card);border:1px solid var(--bdr);border-radius:var(--rad);overflow:hidden;align-self:start}
#page-forside .fs-chead{display:flex;align-items:center;justify-content:space-between;padding:10px 13px;border-bottom:1px solid var(--bdr)}
#page-forside .fs-ctitle{display:flex;align-items:center;gap:8px;font-size:11px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--mut)}
#page-forside .fs-bar{width:3px;height:13px;border-radius:2px;background:var(--grn)}
#page-forside .fs-cmeta{font-size:11px;font-weight:600;color:var(--mut)}
#page-forside .fs-empty{padding:16px 13px;color:var(--mut);font-size:13px}
#page-forside .fs-pk{display:inline-grid;place-items:center;min-width:21px;height:21px;padding:0 5px;border-radius:5px;font-size:11px;font-weight:700;color:#fff;font-variant-numeric:tabular-nums}
#page-forside .fs-p1{background:var(--blu)}#page-forside .fs-px{background:#4b5563}#page-forside .fs-p2{background:var(--red)}
#page-forside .fs-ghost{background:transparent;color:var(--mut);border:1px dashed var(--bdr)}
#page-forside .fs-apw{display:inline-flex;align-items:center;justify-content:center;gap:4px}
#page-forside .fs-tk{font-size:11px;font-weight:800}#page-forside .fs-tk.ok{color:var(--grn)}#page-forside .fs-tk.no{color:var(--red)}
#page-forside .fs-fx{display:grid;grid-template-columns:1fr auto;align-items:center;gap:10px;padding:9px 13px;border-top:1px solid var(--bdr)}
#page-forside .fs-fx:first-child{border-top:0}
#page-forside .fs-tm{min-width:0;font-size:13px;line-height:1.3}
#page-forside .fs-t{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#page-forside .fs-t.away{color:var(--mut)}
#page-forside .fs-odds{display:flex;gap:4px}
#page-forside .fs-od{font-size:11px;font-weight:600;color:var(--mut);background:var(--sf);border:1px solid var(--bdr);border-radius:5px;padding:5px 6px;min-width:34px;text-align:center;font-variant-numeric:tabular-nums}
#page-forside .fs-od.best{color:var(--txt);border-color:rgba(34,197,94,.4);background:rgba(34,197,94,.1);font-weight:700}
#page-forside .fs-wait{font-size:10.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--mut);border:1px dashed var(--bdr);border-radius:6px;padding:5px 8px}
#page-forside .fs-h2hsc{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 13px;background:var(--sf)}
#page-forside .fs-hp{flex:1;min-width:0}
#page-forside .fs-hp .fs-nm{font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#page-forside .fs-hp.me .fs-nm{color:var(--grn)}
#page-forside .fs-hp.r{text-align:right}
#page-forside .fs-sub{font-size:10.5px;color:var(--mut)}
#page-forside .fs-mid{display:flex;flex-direction:column;align-items:center;gap:5px;flex-shrink:0}
#page-forside .fs-vs{display:flex;align-items:baseline;gap:6px;font-weight:800;font-size:28px;line-height:.8;font-variant-numeric:tabular-nums}
#page-forside .fs-vs .sep{font-size:14px;color:var(--mut);font-weight:500}
#page-forside .fs-vs .win{color:var(--grn)}
#page-forside .fs-badge{font-size:9px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;border-radius:5px;padding:3px 6px;white-space:nowrap}
#page-forside .fs-badge.win{background:var(--grn);color:#08130d}
#page-forside .fs-badge.loss{background:var(--red);color:#fff}
#page-forside .fs-badge.draw{background:#4b5563;color:#fff}
#page-forside .fs-badge.live{background:rgba(245,158,11,.15);color:var(--gld);border:1px solid rgba(245,158,11,.3)}
#page-forside .fs-prob{padding:10px 13px;border-top:1px solid var(--bdr);display:flex;flex-direction:column;gap:6px}
#page-forside .fs-prob-top{display:flex;justify-content:space-between;align-items:baseline;font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mut)}
#page-forside .fs-prob-pct{font-size:15px;font-weight:800;color:var(--grn)}
#page-forside .fs-prob-bar{display:flex;height:8px;border-radius:99px;overflow:hidden;background:var(--bdr)}
#page-forside .fs-prob-bar .w{background:var(--grn)}
#page-forside .fs-prob-bar .t{background:#6b7280}
#page-forside .fs-prob-bar .l{background:var(--red)}
#page-forside .fs-prob-lbl{display:flex;justify-content:space-between;font-size:10.5px;color:var(--mut);font-variant-numeric:tabular-nums}
#page-forside .fs-g{display:flex;flex-direction:column}
#page-forside .fs-grow{display:grid;grid-template-columns:1fr 16px 44px 44px;align-items:center;gap:8px;padding:6px 13px;border-top:1px solid var(--bdr);font-size:12px}
#page-forside .fs-grow.head{border-top:0;color:var(--mut);font-size:9.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding-top:9px;padding-bottom:7px}
#page-forside .fs-gm{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--mut)}
#page-forside .fs-gc{display:grid;place-items:center}
#page-forside .fs-res{font-size:11px;font-weight:700;text-align:center;font-variant-numeric:tabular-nums}
#page-forside .fs-res.pd{color:var(--mut)}
#page-forside .fs-stand{display:flex;flex-direction:column}
#page-forside .fs-srow{display:grid;grid-template-columns:24px 1fr auto auto;align-items:center;gap:10px;padding:7px 13px;border-top:1px solid var(--bdr);font-size:12.5px}
#page-forside .fs-srow:first-child{border-top:0}
#page-forside .fs-srow.head{color:var(--mut);font-size:9.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;padding:9px 13px 7px}
#page-forside .fs-srow.gap{color:var(--mut);grid-template-columns:1fr;justify-items:start;padding:2px 13px}
#page-forside .fs-srow.me{background:rgba(34,197,94,.08);box-shadow:inset 3px 0 0 var(--grn)}
#page-forside .fs-srow.me .fs-snm{color:var(--grn);font-weight:700}
#page-forside .fs-pos{font-weight:800;font-size:12px;color:var(--mut);text-align:center;font-variant-numeric:tabular-nums}
#page-forside .fs-pos.r1{color:var(--gld)}#page-forside .fs-pos.r2{color:#cbd5e1}#page-forside .fs-pos.r3{color:#d69e5b}
#page-forside .fs-snm{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#page-forside .fs-spts{font-weight:800;font-size:13px;text-align:right;min-width:22px;font-variant-numeric:tabular-nums}
#page-forside .fs-scor{font-size:11px;color:var(--mut);text-align:right;min-width:22px;font-variant-numeric:tabular-nums}
#page-forside .fs-foot{padding:8px 13px;border-top:1px solid var(--bdr);font-size:10.5px;color:var(--mut);text-align:center}
#page-forside .fs-foot b{color:var(--txt)}
#page-forside .fs-legend{display:flex;flex-wrap:wrap;gap:10px 16px;color:var(--mut);font-size:11.5px;margin-top:14px;padding:0 2px}
#page-forside .fs-it{display:flex;align-items:center;gap:6px}
</style>'''

    return style, nav_button, page_inner

# ── Standalone preview (til lokal test) ────────────────────────────────────
if __name__ == '__main__':
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR  = os.path.join(REPO_ROOT, 'data')
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, 'forside_preview.html')
    style, navbtn, inner = build_forside_pieces(DATA_DIR)
    shell = f'''<!doctype html><html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Forside preview</title>
<style>:root{{--bg:#111827;--sf:#1a2235;--card:#1f2937;--bdr:#374151;--grn:#22c55e;--gld:#f59e0b;--red:#ef4444;--blu:#3b82f6;--pur:#a78bfa;--txt:#f9fafb;--mut:#9ca3af;--rad:12px}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--txt);font-family:'Inter','Segoe UI',system-ui,sans-serif;font-size:14px}}
main{{max-width:1440px;margin:0 auto;padding:22px 20px}}</style>{style}</head>
<body><main><div class="page active" id="page-forside">{inner}</div></main></body></html>'''
    with open(out, 'w', encoding='utf-8') as f:
        f.write(shell)
    print(f'Preview skrevet → {out}')
