#!/usr/bin/env python3
"""
10_analysis.py — Bygger "Analyse"-fanen til dashboardet.

Indhold:
  1. Modstander-scouting (næste H2H-modstander + vælg en vilkårlig spiller)
  2. Alle spillere side om side (spillestil og indbyrdes H2H mod fokus-spilleren)
  3. Hvilke predictors virker hvornår? — fair sammenligning på samme kampe
     (sæson 4, fra predictor_log.csv) + træfsikkerhed pr. turneringskategori
  4. Når fokus-spilleren går imod bookies' favorit
  5. Uafgjort: hvor tit det sker vs. hvor tit det gættes

Datakilder: predictions.csv (alle gæt), weekly_matches.csv (resultater + liga),
hist_matches.csv (bookies/ELO sæson 1–3), predictor_log.csv (alle predictors
sæson 4, fastfrosset før kickoff — se 07_predictor_log.py), h2h.csv.

08_dashboard.py importerer build_analysis_pieces() og indsætter fanen. Alle
CSS-klasser er scopet under #page-analyse. Kan køres standalone til preview:
    python scripts/10_analysis.py [output.html]
"""
import os, sys, json
import numpy as np
import pandas as pd

FOCUS_PLAYER = 'Anders Stenner'
HIDE = {'Ualmindeligt inaktiv'}
CATS = ['Landskampe', 'Klubturneringer', 'Store ligaer', 'Dansk', 'Øvrige']
KEY = ['season', 'round', 'match_code']

_LANDS = {'INT', 'Int', 'Landskamp', 'Nations League', 'VM', 'FWC', 'U21', 'EUR'}
_KLUB = {'CL', 'Champions League', 'EL', 'Europa League', 'ECL', 'Conference League', 'CWC', 'UEFA Super Cup'}
_STORE = {'PL', 'Premier League', 'ENG', 'SPA', 'La Liga', 'TYS', 'Bundesliga', 'ITA', 'Serie A', 'FRA', 'Ligue 1',
          'Championship', 'Coppa Italia', 'DfB Pokal', 'FA Cup', 'Copa del Rey', 'Coupe de France', 'EFL Cup',
          'EFL Trophy', 'Serie B', 'Serie C', 'Community Shield'}
_DANSK = {'SL', 'Superligaen', 'DAN', 'DK', '1. division', 'Betinia Liga', 'Oddset Pokalen', '3. division'}


def league_cat(l):
    l = str(l).strip()
    if l in _LANDS: return 'Landskampe'
    if l in _KLUB: return 'Klubturneringer'
    if l in _STORE: return 'Store ligaer'
    if l in _DANSK: return 'Dansk'
    return 'Øvrige'


def _pick(v):
    return {'1': '1', '1.0': '1', 'X': 'X', 'x': 'X', '9': 'X', '9.0': 'X', '2': '2', '2.0': '2'}.get(str(v).strip())


def _pct(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x) * 100, 1)


def compute(data_dir, focus=FOCUS_PLAYER):
    rd = lambda f: pd.read_csv(os.path.join(data_dir, f))
    wm = rd('weekly_matches.csv')
    wm = wm[pd.to_numeric(wm['season'], errors='coerce') <= 4].copy()
    wm['season'] = wm['season'].astype(int); wm['round'] = wm['round'].astype(int)
    wm['result'] = wm['result'].astype(str).str.strip()
    wm = wm[wm['result'].isin(['1', 'X', '2'])].copy()
    wm['cat'] = wm['league'].map(league_cat)

    pr = rd('predictions.csv')
    pr['bet'] = pr['bet'].map(_pick)
    pr = pr[pr['bet'].notna() & ~pr['player'].isin(HIDE)]
    pr = pr.merge(wm[KEY + ['result', 'cat']], on=KEY, how='inner')
    pr['ok'] = pr['bet'] == pr['result']

    # ── Predictor-bud pr. kamp ────────────────────────────────────────────
    P = []
    hm_p = os.path.join(data_dir, 'hist_matches.csv')
    if os.path.exists(hm_p):
        hm = pd.read_csv(hm_p)
        for _, r in hm.iterrows():
            imp = [r.get('avg_implied_1'), r.get('avg_implied_x'), r.get('avg_implied_2')]
            if all(pd.notna(v) for v in imp):
                P.append((r['season'], r['round'], r['match_code'], 'Bookies', '1X2'[int(np.argmax(imp))]))
            if pd.notna(r.get('elo_home')) and pd.notna(r.get('elo_away')):
                P.append((r['season'], r['round'], r['match_code'], 'ELO', '1' if r['elo_home'] >= r['elo_away'] else '2'))
    log_p = os.path.join(data_dir, 'predictor_log.csv')
    log = pd.read_csv(log_p) if os.path.exists(log_p) else pd.DataFrame(columns=KEY)
    for _, r in log.iterrows():
        k = (r['season'], r['round'], r['match_code'])
        p1, p2 = r.get('prob_1'), r.get('prob_2')
        if pd.notna(p1) and pd.notna(p2):
            P.append(k + ('Bookies', '1X2'[int(np.argmax([p1, 100 - p1 - p2, p2]))]))
        elif all(pd.notna(r.get(c)) for c in ('odds_1', 'odds_x', 'odds_2')):
            P.append(k + ('Bookies', '1X2'[int(np.argmin([r['odds_1'], r['odds_x'], r['odds_2']]))]))
        if pd.notna(r.get('elo_home')) and pd.notna(r.get('elo_away')):
            P.append(k + ('ELO', '1' if r['elo_home'] >= r['elo_away'] else '2'))
        if pd.notna(r.get('opta_home')) and pd.notna(r.get('opta_away')):
            P.append(k + ('Opta', '1' if r['opta_home'] >= r['opta_away'] else '2'))
        for nm, c in (('n20', 'n20_rec'), ('Ensemble', 'rec_ensemble'), ('Odds-MC', 'rec_odds_mc'), ('Bzzoiro', 'rec_bzz')):
            v = _pick(r.get(c)) if pd.notna(r.get(c)) else None
            if v: P.append(k + (nm, v))
    P = pd.DataFrame(P, columns=KEY + ['pred', 'pick'])
    if len(P):
        P['season'] = P['season'].astype(int); P['round'] = P['round'].astype(int)
        P = P.drop_duplicates(KEY + ['pred'], keep='last')

    def _major(s):
        vc = s.value_counts()
        return vc.index[0] if len(vc) == 1 or vc.iloc[0] > vc.iloc[1] else None
    crowd = pr.groupby(KEY)['bet'].agg(_major).dropna().reset_index().rename(columns={'bet': 'pick'})
    crowd['pred'] = 'Folket'
    me = pr[pr['player'] == focus][KEY + ['bet']].rename(columns={'bet': 'pick'})
    me['pred'] = focus.split()[0]
    ALL = pd.concat([P, crowd, me], ignore_index=True).merge(wm[KEY + ['result', 'cat']], on=KEY)
    ALL['ok'] = ALL['pick'] == ALL['result']

    preds = ['Bookies', 'ELO', 'Opta', 'n20', 'Ensemble', 'Odds-MC', 'Bzzoiro', 'Folket', focus.split()[0]]
    cur_s = int(pr['season'].max())

    def _acc(frame, plist):
        out = {}
        for p in plist:
            d = frame[frame['pred'] == p]
            out[p] = {}
            for c in CATS + ['Alle']:
                x = d if c == 'Alle' else d[d['cat'] == c]
                out[p][c] = {'n': int(len(x)), 'acc': _pct(x['ok'].mean()) if len(x) else None}
        return out
    # To visninger, så stikprøverne er sammenlignelige: aktuel sæson (alle predictors)
    # og alle sæsoner (kun predictors med historik).
    hist_preds = ['Bookies', 'ELO', 'Folket', focus.split()[0]]
    acc = {'cur': _acc(ALL[ALL['season'] == cur_s], preds), 'all': _acc(ALL, hist_preds),
           'cur_preds': preds, 'all_preds': hist_preds}

    # Fair sammenligning: sæson 4, kun kampe hvor ALLE har et bud
    fair_preds = ['Bookies', 'n20', 'Ensemble', 'Odds-MC', 'Folket', focus.split()[0]]
    s4 = ALL[ALL['season'] == 4].pivot_table(index=KEY, columns='pred', values='pick', aggfunc='first')
    s4 = s4.join(wm.set_index(KEY)[['result']], how='inner')
    have = [p for p in fair_preds if p in s4.columns]
    common = s4.dropna(subset=have)
    fair = {'n': int(len(common)), 'preds': []}
    for p in have:
        fair['preds'].append({'p': p, 'acc': _pct((common[p] == common['result']).mean()) if len(common) else None,
                              'x': _pct((common[p] == 'X').mean()) if len(common) else None,
                              'hits': int((common[p] == common['result']).sum())})
    fair['preds'].sort(key=lambda r: -(r['acc'] or 0))

    draw = {c: _pct((wm[wm['cat'] == c]['result'] == 'X').mean()) for c in CATS}
    draw['Alle'] = _pct((wm['result'] == 'X').mean())
    xpick = {c: _pct((pr[pr['cat'] == c]['bet'] == 'X').mean()) for c in CATS}

    # Fokus-spilleren vs. bookies' favorit
    bk = P[P['pred'] == 'Bookies'][KEY + ['pick']].rename(columns={'pick': 'bk'}) if len(P) else pd.DataFrame(columns=KEY + ['bk'])
    mb = pr[pr['player'] == focus].merge(bk, on=KEY)
    dv = mb[mb['bet'] != mb['bk']]; same = mb[mb['bet'] == mb['bk']]
    dev = {'n_total': int(len(mb)), 'n_dev': int(len(dv)),
           'me': _pct(dv['ok'].mean()) if len(dv) else None,
           'bk': _pct((dv['bk'] == dv['result']).mean()) if len(dv) else None,
           'same': _pct(same['ok'].mean()) if len(same) else None,
           'nX': int((dv['bet'] == 'X').sum()),
           'cat': {c: {'n': int((dv['cat'] == c).sum()),
                       'me': _pct(dv[dv['cat'] == c]['ok'].mean()) if (dv['cat'] == c).any() else None,
                       'bk': _pct((dv[dv['cat'] == c]['bk'] == dv[dv['cat'] == c]['result']).mean()) if (dv['cat'] == c).any() else None}
                   for c in CATS}}

    # ── Spillerprofiler ───────────────────────────────────────────────────
    pc = pr.merge(crowd.rename(columns={'pick': 'crowd'})[KEY + ['crowd']], on=KEY, how='left').merge(bk, on=KEY, how='left')
    h2h = rd('h2h.csv')
    h2h_done = h2h[h2h['h2h_pts_a'].notna()]

    def stats(x):
        if not len(x): return None
        r = {'n': int(len(x)), 'acc': _pct(x['ok'].mean()),
             'pick': {k: _pct((x['bet'] == k).mean()) for k in '1X2'}}
        f = x[x['bk'].notna()]; r['fav'] = _pct((f['bet'] == f['bk']).mean()) if len(f) else None
        c = x[x['crowd'].notna()]; con = c[c['bet'] != c['crowd']]
        r['contra'] = _pct(len(con) / len(c)) if len(c) else None
        r['contra_acc'] = _pct(con['ok'].mean()) if len(con) else None
        r['cat'] = {k: (_pct(x[x['cat'] == k]['ok'].mean()) if (x['cat'] == k).sum() >= 8 else None) for k in CATS}
        xs = x[x['bet'] == 'X']; r['x_acc'] = _pct(xs['ok'].mean()) if len(xs) else None
        return r

    prof = {}
    for pl in sorted(pr[pr['season'] == cur_s]['player'].unique()):
        a = pc[pc['player'] == pl]; a4 = a[a['season'] == cur_s]
        rr = a4.groupby('round')['ok'].sum().sort_index().tail(8)
        rec = {'v': 0, 'u': 0, 't': 0}
        for _, h in h2h_done.iterrows():
            if {h['player_a'], h['player_b']} == {focus, pl}:
                mine = h['h2h_pts_a'] if h['player_a'] == focus else h['h2h_pts_b']
                rec['v' if mine >= 3 else 'u' if mine == 1 else 't'] += 1
        prof[pl] = {'all': stats(a), 'cur': stats(a4), 'form': [int(v) for v in rr.values],
                    'form_r': [int(v) for v in rr.index], 'rec': rec}

    hc = h2h[(h2h['season'] == h2h['season'].max())]
    opp, opp_round = None, None
    mine = hc[(hc['player_a'] == focus) | (hc['player_b'] == focus)]
    if len(mine):
        m = mine[mine['round'] == mine['round'].max()].iloc[0]
        opp = m['player_b'] if m['player_a'] == focus else m['player_a']; opp_round = int(m['round'])

    return {'cats': CATS, 'preds': preds, 'acc': acc, 'fair': fair, 'draw': draw, 'xpick': xpick, 'dev': dev,
            'prof': prof, 'me': focus, 'opp': opp, 'opp_round': opp_round, 'cur_s': cur_s,
            'n_matches': int(len(wm)), 'n_preds': int(len(pr)),
            'log_n': int(len(log)), 'log_live': int((log.get('kilde') == 'live').sum()) if len(log) else 0}


# ═══════════════════════════════════════════════════════════════════════════
STYLE = r'''<style>
#page-analyse{--me:#3987e5;--op:#d95926;--s3:#199e70;--neu:#6b7280}
#page-analyse .an-lead{color:var(--mut);font-size:12.5px;margin:-6px 0 14px}
#page-analyse .an-sec{margin:22px 0 10px;display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
#page-analyse .an-sec h3{font-size:15px;font-weight:800}
#page-analyse .an-sub{font-size:11.5px;color:var(--mut)}
#page-analyse .an-grid{display:grid;gap:12px;grid-template-columns:minmax(0,1fr)}
@media(min-width:820px){#page-analyse .an-grid.c2{grid-template-columns:repeat(2,minmax(0,1fr))}}
#page-analyse .an-card{background:var(--card);border:1px solid var(--bdr);border-radius:var(--rad);padding:14px;min-width:0}
#page-analyse .an-ct{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--mut);margin-bottom:10px}
#page-analyse .an-note{font-size:11.5px;color:var(--mut);margin-top:8px}
#page-analyse .an-ins{border-left:3px solid var(--grn);padding:7px 10px;background:rgba(34,197,94,.06);border-radius:0 8px 8px 0;font-size:13px;margin-top:10px;line-height:1.5}
#page-analyse .an-leg{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--mut);margin-bottom:8px}
#page-analyse .an-leg i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px;vertical-align:-1px}
#page-analyse select{background:var(--sf);color:var(--txt);border:1px solid var(--bdr);border-radius:8px;padding:6px 8px;font:inherit;font-size:13px;max-width:100%}
#page-analyse .an-hd{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}
#page-analyse .an-nm{font-weight:800;font-size:16px}#page-analyse .an-rec{font-size:12px;color:var(--mut);margin-left:8px}
#page-analyse .an-br{display:grid;grid-template-columns:118px minmax(0,1fr);gap:8px;align-items:center;margin:7px 0}
#page-analyse .an-bl{font-size:12px;color:var(--mut);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#page-analyse .an-bars{display:flex;flex-direction:column;gap:2px}
#page-analyse .an-bar{position:relative;height:13px;background:rgba(255,255,255,.04);border-radius:0 4px 4px 0}
#page-analyse .an-bar span{position:absolute;left:0;top:0;bottom:0;border-radius:0 4px 4px 0;min-width:2px}
#page-analyse .an-bar em{position:absolute;top:-1px;font-style:normal;font-size:11px;color:var(--txt);font-variant-numeric:tabular-nums;padding-left:6px;white-space:nowrap}
#page-analyse .an-bar.big{height:18px}#page-analyse .an-bar.big em{top:1px}
#page-analyse .an-tw{overflow-x:auto}
#page-analyse table{width:100%;border-collapse:collapse;font-size:12.5px}
#page-analyse th{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);text-align:center;padding:7px 6px;border-bottom:1px solid var(--bdr);white-space:nowrap}
#page-analyse th:first-child,#page-analyse td:first-child{text-align:left}
#page-analyse td{padding:7px 6px;border-bottom:1px solid rgba(55,65,81,.5);text-align:center;font-variant-numeric:tabular-nums;white-space:nowrap}
#page-analyse tr.me td{background:rgba(57,135,229,.10)}#page-analyse tr.op td{background:rgba(217,89,38,.10)}
#page-analyse .an-hc{border-radius:6px;padding:5px 4px;display:block}#page-analyse .an-hc small{display:block;font-size:9.5px;color:var(--mut)}
#page-analyse .an-best{font-weight:800}#page-analyse .an-best::after{content:" ★";color:#c98500}
#page-analyse .an-spark{width:100%;height:90px;display:block}
#page-analyse .an-tg{display:flex;gap:4px}#page-analyse .an-tg button{background:var(--sf);color:var(--mut);border:1px solid var(--bdr);border-radius:7px;padding:4px 9px;font:inherit;font-size:11.5px;cursor:pointer}#page-analyse .an-tg button.on{color:var(--grn);border-color:rgba(34,197,94,.4);background:rgba(34,197,94,.1);font-weight:600}
#page-analyse ul{margin:6px 0 0 18px;font-size:13px}#page-analyse li{margin:5px 0}
#an-tip{position:fixed;pointer-events:none;background:#0b1220;color:var(--txt);border:1px solid var(--bdr);border-radius:8px;padding:6px 9px;font-size:12px;opacity:0;transition:opacity .1s;z-index:999;max-width:250px}
</style>'''

PAGE = r'''<div class="ph"><h2>Analyse</h2><div class="pill">modstandere · predictors · dine valg</div></div>
<div class="an-lead">Bygget på <b>__NM__ afgjorte kampe</b> og <b>__NP__ gæt</b> fra sæson 1–4. Hold musen over (eller tryk på) søjler og celler for detaljer.</div>

<div class="an-sec"><h3>Modstander-scouting</h3></div>
<div class="an-card"><div class="an-hd"><div><span class="an-nm" id="an-opName"></span><span class="an-rec" id="an-opRec"></span></div>
<label style="font-size:12px;color:var(--mut)">Vælg spiller <select id="an-opSel"></select></label></div>
<div class="an-leg" style="margin-top:10px"><span><i style="background:var(--me)"></i><span id="an-meLeg"></span></span><span><i style="background:var(--op)"></i><span id="an-opLeg"></span></span></div>
<div class="an-grid c2">
 <div><div class="an-ct">Spillestil, alle sæsoner</div><div id="an-style"></div></div>
 <div><div class="an-ct">Træfsikkerhed pr. kategori</div><div id="an-cats"></div></div>
</div>
<div class="an-ct" style="margin-top:12px">Form: rigtige pr. runde, sæson __CS__ (seneste 8)</div><svg class="an-spark" id="an-form" viewBox="0 0 600 90" preserveAspectRatio="none"></svg>
<div class="an-ins" id="an-scout"></div></div>

<div class="an-sec"><h3>Alle spillere side om side</h3></div>
<div class="an-card"><div class="an-tw"><table id="an-all"></table></div>
<div class="an-note">Følger fav. = gætter bookies' favorit · Imod flertal = gætter anderledes end flertallet af puljen · Træf imod = hit-rate i de kampe · H2H mod dig = V-U-T i jeres indbyrdes opgør.</div></div>

<div class="an-sec"><h3>Hvilke predictors virker hvornår?</h3></div>
<div class="an-grid c2">
<div class="an-card"><div class="an-ct">Sæson 4: samme kampe for alle (n=<span id="an-fairN"></span>)</div><div id="an-fair"></div>
<div class="an-note">Fair sammenligning: kun kampe, hvor alle predictors havde et bud før kickoff (fra predictor-logbogen).</div><div class="an-ins" id="an-fairIns"></div></div>
<div class="an-card"><div class="an-hd"><div class="an-ct" style="margin:0">Træfsikkerhed pr. kategori</div><div class="an-tg" id="an-tg"><button data-m="cur" class="on">Sæson __CS__</button><button data-m="all">Alle sæsoner</button></div></div>
<div class="an-tw" style="margin-top:10px"><table id="an-pred"></table></div>
<div class="an-note" id="an-predNote"></div></div>
</div>

<div class="an-sec"><h3>Dine valg</h3></div>
<div class="an-grid c2">
<div class="an-card"><div class="an-ct">Når dit gæt ≠ bookies' favorit</div>
<div class="an-leg"><span><i style="background:var(--me)"></i>Dit gæt rigtigt</span><span><i style="background:var(--op)"></i>Favoritten rigtig</span></div><div id="an-dev"></div><div class="an-ins" id="an-devIns"></div></div>
<div class="an-card"><div class="an-ct">Uafgjort: hvor tit det sker vs. hvor tit det gættes</div>
<div class="an-leg"><span><i style="background:var(--s3)"></i>Kampe der endte X</span><span><i style="background:var(--me)"></i>Puljens X-gæt</span></div><div id="an-draw"></div><div class="an-ins" id="an-drawIns"></div></div>
</div>
<div class="an-note" style="margin-top:14px">Predictor-logbogen (data/predictor_log.csv) gemmer hver predictors bud før kickoff: __LOGN__ kampe indtil videre. Den blev startet med data genskabt fra git-historikken og fylder sig selv op hver runde.</div>
<div id="an-tip"></div>
<script>
(function(){
const D=__JSON__;
const $=id=>document.getElementById(id);
const tip=$('an-tip');
function showTip(e){const t=e.target.closest&&e.target.closest('#page-analyse [data-tip]');if(!t){tip.style.opacity=0;return}tip.innerHTML=t.dataset.tip;tip.style.opacity=1;const x=Math.min((e.clientX||0)+12,innerWidth-260);tip.style.left=x+'px';tip.style.top=((e.clientY||0)+14)+'px'}
document.addEventListener('mousemove',showTip);document.addEventListener('click',showTip);
const f=v=>v==null?'—':(Math.round(v*10)/10).toLocaleString('da-DK')+'%';
const first=n=>n.split(' ')[0];
function bar(v,col,max,t,big){const w=v==null?0:Math.min(100,v/max*100);return`<div class="an-bar${big?' big':''}" data-tip="${t}"><span style="width:${w}%;background:${col}"></span><em style="left:${w}%">${v==null?'—':Math.round(v)+'%'}</em></div>`}
function rows(items,max){return items.map(([lbl,a,b,ta,tb])=>`<div class="an-br"><div class="an-bl">${lbl}</div><div class="an-bars">${bar(a,'var(--me)',max,ta)}${bar(b,'var(--op)',max,tb)}</div></div>`).join('')}
const ME=D.me,P=D.prof,players=Object.keys(P).filter(p=>p!==ME);
if(!P[ME])return;
$('an-meLeg').textContent=ME;
const sel=$('an-opSel');sel.innerHTML=players.map(p=>`<option ${p===D.opp?'selected':''}>${p}</option>`).join('');
function scout(op){
 const a=P[ME].all,b=P[op].all,r=P[op].rec;
 $('an-opName').textContent=(op===D.opp?'Næste modstander (runde '+D.opp_round+'): ':'')+op;
 $('an-opRec').textContent=`H2H mod dig: ${r.v}V ${r.u}U ${r.t}T`;$('an-opLeg').textContent=op;
 const S=[['Træfsikkerhed',a.acc,b.acc],['Følger favorit',a.fav,b.fav],['Imod flertal',a.contra,b.contra],['Træf når imod',a.contra_acc,b.contra_acc],['Gætter X',a.pick.X,b.pick.X],['Træf på X',a.x_acc,b.x_acc]];
 $('an-style').innerHTML=rows(S.map(([l,x,y])=>[l,x,y,`${first(ME)} · ${l}: <b>${f(x)}</b>`,`${first(op)} · ${l}: <b>${f(y)}</b>`]),100);
 $('an-cats').innerHTML=rows(D.cats.map(c=>[c,a.cat[c],b.cat[c],`${first(ME)} · ${c}: <b>${f(a.cat[c])}</b>`,`${first(op)} · ${c}: <b>${f(b.cat[c])}</b>`]),80);
 const sv=$('an-form'),fa=P[ME].form,fb=P[op].form,R=P[op].form_r,n=Math.max(fa.length,fb.length,2);
 const X=i=>20+i*(560/(n-1)),Y=v=>80-v*7;let s='';
 for(let g=0;g<=10;g+=5)s+=`<line x1="20" x2="580" y1="${Y(g)}" y2="${Y(g)}" stroke="#374151" stroke-width="1"/><text x="2" y="${Y(g)+3}" fill="#9ca3af" font-size="9">${g}</text>`;
 [[fa,'var(--me)',first(ME)],[fb,'var(--op)',first(op)]].forEach(([arr,c,nm])=>{s+=`<polyline fill="none" stroke="${c}" stroke-width="2" vector-effect="non-scaling-stroke" points="${arr.map((v,i)=>X(i)+','+Y(v)).join(' ')}"/>`;
  arr.forEach((v,i)=>s+=`<circle cx="${X(i)}" cy="${Y(v)}" r="10" fill="transparent" data-tip="${nm} · R${R[i]??''}: <b>${v} rigtige</b>"/><circle cx="${X(i)}" cy="${Y(v)}" r="3" fill="${c}" stroke="#1f2937" stroke-width="2" pointer-events="none"/>`)});
 sv.innerHTML=s;
 const fo=first(op),L=[];
 L.push(`${fo} følger bookies' favorit i <b>${f(b.fav)}</b> af kampene (dig: ${f(a.fav)}).`);
 L.push(`${fo} går imod flertallet i <b>${f(b.contra)}</b> af kampene og rammer <b>${f(b.contra_acc)}</b> der.`);
 L.push(`${fo} gætter X i <b>${f(b.pick.X)}</b> af kampene (dig: ${f(a.pick.X)}).`);
 const cs=D.cats.filter(c=>b.cat[c]!=null).sort((x,y)=>b.cat[y]-b.cat[x]);
 if(cs.length)L.push(`Stærkest i <b>${cs[0]}</b> (${f(b.cat[cs[0]])}), svagest i <b>${cs[cs.length-1]}</b> (${f(b.cat[cs[cs.length-1]])}).`);
 L.push(`H2H afgøres kun i kampe, hvor I gætter forskelligt. ${(b.fav??0)<(a.fav??0)-5?`${fo} afviger oftere fra favoritten end dig, så det er typisk de kampe, der bliver afgørende.`:(b.fav??0)>(a.fav??0)+5?`${fo} følger favoritten oftere end dig, så dine egne afvigelser bliver afgørende.`:`I spiller ret ens, så der bliver få afgørende kampe.`}`);
 $('an-scout').innerHTML='<b>Scoutrapport</b><br>'+L.join('<br>');
}
sel.onchange=()=>scout(sel.value);scout(D.opp&&P[D.opp]?D.opp:players[0]);
(function(){const ps=Object.keys(P).sort((x,y)=>(P[y].cur?.acc||0)-(P[x].cur?.acc||0));
 $('an-all').innerHTML=`<thead><tr><th>Spiller</th><th>Træf S${D.cur_s}</th><th>Træf alle</th><th>X-andel</th><th>Følger fav.</th><th>Imod flertal</th><th>Træf imod</th><th>H2H mod dig</th></tr></thead><tbody>`+
 ps.map(p=>{const a=P[p].all,s=P[p].cur,r=P[p].rec;return`<tr class="${p===ME?'me':p===D.opp?'op':''}"><td>${p}</td><td>${f(s?.acc)}</td><td>${f(a.acc)}</td><td>${f(a.pick.X)}</td><td>${f(a.fav)}</td><td>${f(a.contra)}</td><td>${f(a.contra_acc)}</td><td>${p===ME?'—':r.v+'-'+r.u+'-'+r.t}</td></tr>`}).join('')+'</tbody>';})();
(function(){const F=D.fair;$('an-fairN').textContent=F.n;const mx=Math.max(...F.preds.map(p=>p.acc||0),1);const me=first(ME);
 $('an-fair').innerHTML=F.preds.map(p=>`<div class="an-br"><div class="an-bl">${p.p===me?'<b style="color:var(--txt)">'+p.p+'</b>':p.p}</div><div class="an-bars">${bar(p.acc,p.p===me?'var(--me)':'var(--neu)',100,`${p.p}: <b>${f(p.acc)}</b> rigtige (${p.hits} af ${F.n})<br>Gætter X i ${f(p.x)}`,true)}</div></div>`).join('');
 const top=F.preds[0],mine=F.preds.find(p=>p.p===me),n20=F.preds.find(p=>p.p==='n20');
 if(top&&mine)$('an-fairIns').innerHTML=`På de samme ${F.n} kampe rammer <b>${top.p}</b> ${f(top.acc)} og du ${f(mine.acc)}. Det er ${top.hits-mine.hits} rigtige mere til ${top.p}.`+(n20?` <b>n20</b> rammer ${f(n20.acc)} og gætter X i ${f(n20.x)} af kampene.`:'')+` Bookies, Ensemble og Odds-MC vælger næsten altid det samme.`;})();
(function(){const C=[...D.cats,'Alle'];
 function draw(m){const A=D.acc[m],PL=D.acc[m+'_preds'],min=m==='cur'?15:30,best={};
 C.forEach(c=>{let b=null;PL.forEach(p=>{const v=A[p][c];if(v.acc!=null&&v.n>=min&&(!b||v.acc>A[b][c].acc))b=p});best[c]=b});
 $('an-pred').innerHTML='<thead><tr><th>Predictor</th>'+C.map(c=>`<th>${c}</th>`).join('')+'</tr></thead><tbody>'+PL.map(p=>'<tr><td>'+p+'</td>'+C.map(c=>{const v=A[p][c];if(v.acc==null)return'<td>—</td>';
 const a=Math.max(0,Math.min(1,(v.acc-40)/25));return`<td><span class="an-hc ${best[c]===p?'an-best':''}" style="background:rgba(57,135,229,${(0.08+a*0.55).toFixed(2)})" data-tip="${p} · ${c}<br><b>${f(v.acc)}</b> rigtige af ${v.n} kampe">${f(v.acc)}<small>n=${v.n}</small></span></td>`}).join('')+'</tr>').join('')+'</tbody>';
 $('an-predNote').innerHTML=`Celle = andel rigtige (antal kampe nedenunder). ★ = bedst i kategorien (min. ${min} kampe). `+(m==='cur'?`Alle predictors er målt i sæson ${D.cur_s}, men på de kampe hvor hver især havde et bud. Små kategorier er usikre.`:`Kun predictors med historik fra flere sæsoner. n20, Ensemble, Odds-MC og Opta findes først fra sæson 4.`);
 document.querySelectorAll('#an-tg button').forEach(b=>b.classList.toggle('on',b.dataset.m===m));}
 document.querySelectorAll('#an-tg button').forEach(b=>b.onclick=()=>draw(b.dataset.m));draw('cur');})();
(function(){const v=D.dev;if(!v.n_dev)return;const items=D.cats.filter(c=>v.cat[c].n).map(c=>[`${c} <span style="color:#6b7280">(${v.cat[c].n})</span>`,v.cat[c].me,v.cat[c].bk,`Dit gæt rigtigt: <b>${f(v.cat[c].me)}</b> af ${v.cat[c].n}`,`Favoritten rigtig: <b>${f(v.cat[c].bk)}</b>`]);
 items.push([`<b>Alle</b> <span style="color:#6b7280">(${v.n_dev})</span>`,v.me,v.bk,`Dit gæt rigtigt: <b>${f(v.me)}</b>`,`Favoritten rigtig: <b>${f(v.bk)}</b>`]);
 $('an-dev').innerHTML=rows(items,70);
 const diff=((v.bk??0)-(v.me??0)).toFixed(1).replace('.',',');
 $('an-devIns').innerHTML=`Du går imod favoritten i <b>${Math.round(v.n_dev/v.n_total*100)}%</b> af kampene, og <b>${Math.round(v.nX/v.n_dev*100)}%</b> af gangene med et X. I de kampe rammer du ${f(v.me)} mod favorittens ${f(v.bk)} (${diff} procentpoint). Når du følger favoritten, rammer du ${f(v.same)}.`;})();
(function(){$('an-draw').innerHTML=D.cats.map(c=>`<div class="an-br"><div class="an-bl">${c}</div><div class="an-bars">${bar(D.draw[c],'var(--s3)',40,`${c}: <b>${f(D.draw[c])}</b> endte uafgjort`)}${bar(D.xpick[c],'var(--me)',40,`${c}: puljen gætter X i <b>${f(D.xpick[c])}</b>`)}</div></div>`).join('');
 $('an-drawIns').innerHTML=`Uafgjort sker i ${f(D.draw.Alle)} af kampene, og puljen gætter X næsten lige så tit. Men et X rammer kun omkring 3 ud af 10 gange, så det bør bygge på et konkret signal.`;})();
})();
</script>'''


def build_analysis_pieces(data_dir, focus_player=FOCUS_PLAYER):
    """Returnerer (style_html, nav_button_html, page_inner_html)."""
    d = compute(data_dir, focus_player)
    page = (PAGE.replace('__JSON__', json.dumps(d, ensure_ascii=False))
                .replace('__NM__', f"{d['n_matches']:,}".replace(',', '.'))
                .replace('__NP__', f"{d['n_preds']:,}".replace(',', '.'))
                .replace('__CS__', str(d['cur_s']))
                .replace('__LOGN__', str(d['log_n'])))
    nav = "<button onclick=\"showPage('analyse',this)\">Analyse</button>"
    return STYLE, nav, page


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, 'analyse_preview.html')
    style, _, inner = build_analysis_pieces(os.path.join(root, 'data'))
    shell = f'''<!doctype html><html lang="da"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Analyse preview</title>
<style>:root{{--bg:#111827;--sf:#1a2235;--card:#1f2937;--bdr:#374151;--grn:#22c55e;--txt:#f9fafb;--mut:#9ca3af;--rad:12px}}
*{{box-sizing:border-box;margin:0;padding:0}}body{{background:var(--bg);color:var(--txt);font-family:Inter,'Segoe UI',system-ui,sans-serif;font-size:14px}}
main{{max-width:1180px;margin:0 auto;padding:18px 14px}}.ph{{display:flex;gap:10px;align-items:center;margin-bottom:16px}}.ph h2{{font-size:17px;font-weight:800}}
.pill{{background:rgba(34,197,94,.12);color:var(--grn);border:1px solid rgba(34,197,94,.25);border-radius:99px;padding:2px 10px;font-size:10px;font-weight:600;text-transform:uppercase}}</style>{style}</head>
<body><main><div class="page active" id="page-analyse">{inner}</div></main></body></html>'''
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(shell)
    print(f'Preview skrevet → {out}')
