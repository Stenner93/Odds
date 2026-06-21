"""
Delt konfiguration for alle scripts.
Alle scripts importerer herfra i stedet for at definere globals selv.
"""
import os, pandas as pd

# ── Repo-stier ────────────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(REPO_ROOT, 'data')

# ── Sæson ────────────────────────────────────────────────────────────────
CURRENT_SEASON  = 4
API_SEASON_YEAR = 2025

# ── API-nøgler (hentes fra GitHub Secrets via miljøvariabler) ────────────
GITHUB_TOKEN   = os.environ.get('GITHUB_TOKEN', '')
ODDS_API_KEY   = os.environ.get('ODDS_API_KEY', 'c0c769b1de997f244fde74902a303138')
BZZOIRO_TOKEN  = os.environ.get('BZZOIRO_TOKEN', '456373dd0bdb3336ac9cadf4fc903d1d3d322a79')
SPORTSDB_API_KEY = '123'

# ── GitHub repo-info ─────────────────────────────────────────────────────
GITHUB_USER     = 'Stenner93'
GITHUB_REPO     = 'Odds'
GITHUB_FILENAME = 'index.html'

# ── CSV-stier ─────────────────────────────────────────────────────────────
MATCHES_CSV     = os.path.join(DATA_DIR, 'weekly_matches.csv')
PREDICTIONS_CSV = os.path.join(DATA_DIR, 'predictions.csv')
ODDS_CSV        = os.path.join(DATA_DIR, 'odds.csv')
POINTS_CSV      = os.path.join(DATA_DIR, 'points.csv')
H2H_CSV         = os.path.join(DATA_DIR, 'h2h.csv')
STANDINGS_CSV   = os.path.join(DATA_DIR, 'standings.csv')
ELO_CSV         = os.path.join(DATA_DIR, 'elo_history.csv')
HIST_MATCHES    = os.path.join(DATA_DIR, 'hist_matches.csv')
HIST_ODDS       = os.path.join(DATA_DIR, 'hist_odds.csv')
HIST_PREDS      = os.path.join(DATA_DIR, 'hist_predictions.csv')
PLAYER_STATS    = os.path.join(DATA_DIR, 'player_stats.csv')
SOFASCORE_CSV   = os.path.join(DATA_DIR, 'sofascore_data.csv')
H2H_ORDER_FILE  = os.path.join(DATA_DIR, 'h2h_order.txt')
KUPON_INPUT     = os.path.join(DATA_DIR, 'kupon_input.txt')

# ── H2H point-konstanter ─────────────────────────────────────────────────
H2H_WIN  = 3
H2H_DRAW = 1
H2H_LOSS = 0

# ── Hjælpefunktioner ─────────────────────────────────────────────────────
def _norm_bet(v):
    """Konverterer råt gætværdi til '1'/'X'/'2' eller None."""
    if v is None: return None
    try:
        s = str(v).strip()
        if s.lower() in ('nan', 'none', ''): return None
        if s in ('1', '1.0'): return '1'
        if s in ('9', '9.0', 'X', 'x'): return 'X'
        if s in ('2', '2.0'): return '2'
        vi = int(float(s))
        return {1: '1', 9: 'X', 2: '2'}.get(vi)
    except:
        return None

def get_current_round():
    """Henter aktuel runde fra weekly_matches.csv."""
    df = pd.read_csv(MATCHES_CSV)
    df['season'] = df['season'].astype(int)
    df['round']  = df['round'].astype(int)
    return int(df[df['season'] == CURRENT_SEASON]['round'].max())

def csv_upsert(path, df_new, key_cols, overwrite_if_new_data=False):
    """Opdaterer eller indsætter rækker i en CSV. Overskriver IKKE eksisterende data som standard."""
    for col in key_cols:
        if col in df_new.columns:
            try: df_new[col] = df_new[col].astype(int)
            except: pass

    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            df_existing = pd.read_csv(path)
            for col in key_cols:
                try: df_existing[col] = df_existing[col].astype(int)
                except: pass

            merged = pd.merge(df_existing, df_new, on=key_cols, how='outer', suffixes=('_old','_new'))
            for col in df_new.columns:
                if col in key_cols: continue
                old, new = f'{col}_old', f'{col}_new'
                if old in merged.columns and new in merged.columns:
                    if overwrite_if_new_data:
                        merged[col] = merged[new].fillna(merged[old])
                    else:
                        merged[col] = merged[old].fillna(merged[new])
                elif new in merged.columns:
                    merged[col] = merged[new]
                elif old in merged.columns:
                    merged[col] = merged[old]
            df_final = merged[df_new.columns]
        except Exception as e:
            print(f'  ⚠ csv_upsert læsefejl ({os.path.basename(path)}): {e} — opretter ny')
            df_final = df_new
    else:
        df_final = df_new

    df_final.to_csv(path, index=False)
    print(f'  ✓ {os.path.basename(path)}: {len(df_final)} rækker')
