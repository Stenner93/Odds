"""
bzzoiro.py — Fælles opslag i Bzzoiro Sports Data (sports.bzzoiro.com/api/v2).

Bruges af 02_odds.py (konsensus-odds som reserve + forudsigelser til logbogen)
og 04_results.py (første resultatkilde). Gratis fodbold-nøgle: 7.500 kald/døgn.

Kampe findes via /events/?date_from=D&date_to=D og matches på BEGGE holdnavne
(direkte eller ombyttet). Navnelogikken er den, der i kildetesten (tools/
source_test.py) fandt 226/263 S4-kampe uden et eneste forkert match.

Bzzoiros home_score/away_score er stillingen efter 90 min; forlænget tid og
straffespark ligger separat i extra_time_score / penalty_shootout — præcis
vores regel (afgjort efter 90 min).
"""
import datetime as _dt
import requests
from rapidfuzz import fuzz
from unidecode import unidecode

BASE = 'https://sports.bzzoiro.com/api/v2'
MATCH_THRESHOLD = 80

_STRIP = {'fc', 'afc', 'sc', 'cf', 'fk', 'if', 'bk', 'ac', 'sk', 'ssc', 'cd', 'ud',
          'sv', 'vfb', 'vfl', 'tsg', 'rc', 'as', 'us', 'ks'}


class Bzzoiro:
    def __init__(self, token, variants=None, log=print):
        """variants(name) -> liste af kendte navne for et hold (vores navn først)."""
        self.token = (token or '').strip()
        self.headers = {'Authorization': f'Token {self.token}'}
        self.variants = variants or (lambda n: [n])
        self.log = log
        self.calls = 0
        self._days = {}

    @property
    def enabled(self):
        return bool(self.token)

    # ── HTTP ─────────────────────────────────────────────────────────────
    def _get(self, path, params=None):
        if not self.enabled:
            return None
        try:
            self.calls += 1
            r = requests.get(f'{BASE}{path}', headers=self.headers, params=params, timeout=20)
        except Exception as e:
            self.log(f'  ⚠ Bzzoiro {path}: {e}')
            return None
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            self.log(f'  ⚠ Bzzoiro {path}: HTTP {r.status_code}')
            return None
        try:
            return r.json()
        except Exception:
            return None

    def events_on(self, date_str):
        if date_str in self._days:
            return self._days[date_str]
        evs, off = [], 0
        while True:
            j = self._get('/events/', {'date_from': date_str, 'date_to': date_str,
                                       'limit': 200, 'offset': off})
            if not j:
                break
            evs += j.get('results', [])
            if not j.get('next') or off >= 1000:
                break
            off += 200
        self._days[date_str] = evs
        return evs

    # ── Navnematch ───────────────────────────────────────────────────────
    @staticmethod
    def _norm(s):
        s = unidecode(str(s)).lower().replace('​', '')
        for ch in ".-/'&()":
            s = s.replace(ch, ' ')
        return ' '.join(t for t in s.split() if t not in _STRIP)

    def _score(self, ours, theirs):
        t = self._norm(theirs)
        best = 0
        for v in dict.fromkeys(self._norm(x) for x in self.variants(ours) if x):
            if not v or not t:
                continue
            s = max(fuzz.token_sort_ratio(v, t), fuzz.ratio(v, t))
            if (v in t or t in v) and min(len(v), len(t)) >= 3:
                s = max(s, 90)
            best = max(best, s)
        return best

    def find(self, home, away, date_str, neighbours=True):
        """Find kampen. Returnerer (event, byttet) eller (None, False)."""
        try:
            d0 = _dt.date.fromisoformat(str(date_str)[:10])
        except Exception:
            return None, False
        days = [d0]
        if neighbours:
            days += [d0 - _dt.timedelta(days=1), d0 + _dt.timedelta(days=1)]
        best = (0, None, False)
        for d in days:
            for ev in self.events_on(d.isoformat()):
                eh, ea = ev.get('home_team', ''), ev.get('away_team', '')
                direct = min(self._score(home, eh), self._score(away, ea))
                swap = min(self._score(home, ea), self._score(away, eh))
                sc, sw = (direct, False) if direct >= swap else (swap, True)
                if sc > best[0]:
                    best = (sc, ev, sw)
            if best[0] >= MATCH_THRESHOLD:
                break
        if best[0] >= MATCH_THRESHOLD:
            return best[1], best[2]
        return None, False

    # ── Data ─────────────────────────────────────────────────────────────
    @staticmethod
    def _flip(r):
        return {'1': '2', '2': '1', 'X': 'X'}.get(r, r)

    def result(self, home, away, date_str):
        """1/X/2 efter 90 min for en afsluttet kamp, ellers None."""
        ev, sw = self.find(home, away, date_str)
        # 'aet' = afgjort i forlænget tid; scoren er stadig 90-min-stillingen
        if not ev or str(ev.get('status', '')).lower() not in ('finished', 'aet'):
            return None
        try:
            h, a = int(ev['home_score']), int(ev['away_score'])
        except Exception:
            return None
        r = '1' if h > a else ('2' if h < a else 'X')
        return self._flip(r) if sw else r

    def odds(self, home, away, date_str):
        """Konsensus 1X2-odds (o1, ox, o2) for en kamp der IKKE er startet, ellers None."""
        ev, sw = self.find(home, away, date_str, neighbours=False)
        if not ev or str(ev.get('status', '')).lower() != 'notstarted':
            return None
        j = self._get(f"/events/{ev['id']}/odds/")
        o = (j or {}).get('odds') or {}
        o1, ox, o2 = o.get('home_win'), o.get('draw'), o.get('away_win')
        if not (o1 and ox and o2):
            return None
        if sw:
            o1, o2 = o2, o1
        return round(float(o1), 2), round(float(ox), 2), round(float(o2), 2)

    def prediction(self, home, away, date_str):
        """(p1, px, p2) i procent fra Bzzoiros model, eller None."""
        ev, sw = self.find(home, away, date_str, neighbours=False)
        if not ev:
            return None
        j = self._get(f"/events/{ev['id']}/prediction/")
        mr = (((j or {}).get('markets') or {}).get('match_result') or {})
        p1, px, p2 = mr.get('prob_home'), mr.get('prob_draw'), mr.get('prob_away')
        if None in (p1, px, p2):
            return None
        if sw:
            p1, p2 = p2, p1
        return round(float(p1), 1), round(float(px), 1), round(float(p2), 1)
