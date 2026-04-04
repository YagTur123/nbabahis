"""
NBA Predictor — v11.0
Birleştirme: v10.2 (Odds API) + v10.3 (Settings & Backtest)
Eklemeler:
  - Gerçek backtest doğrulaması (NBA box score ile karşılaştırma)
  - Rate limiting + retry queue
  - HOT/COLD trend alarmı
  - Rakip savunma profili (pozisyon bazlı)
  - Kelly Criterion düzeltmesi (geçmiş hit rate'den)
  - CSV export
  - Karşılaştırma modu

pip install flask flask-cors nba_api pandas numpy scikit-learn xgboost lightgbm requests python-dotenv
"""

from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS
import pandas as pd
import numpy as np
import time, sqlite3, logging, warnings, math, threading, requests, json, os, pickle, io, csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from functools import lru_cache
from collections import deque

from dotenv import load_dotenv
load_dotenv()

try:
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    ADVANCED_ML = True
except ImportError as e:
    ADVANCED_ML = False
    print(f"[WARNING] Advanced ML libs not found ({e}), using sklearn fallback")

from nba_api.stats.endpoints import (
    playergamelog, scoreboardv2, commonteamroster,
    leaguedashteamstats, boxscoretraditionalv2
)
from nba_api.stats.static import teams as nba_teams
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

warnings.filterwarnings('ignore')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('predictor_v11.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('PredictorV11')

# ─── CONFIG ───────────────────────────────────────────────────
MAX_THREADS = 5
MIN_GAMES = 6          # 10 → 6
MIN_AVG_MIN = 10       # 14 → 10
MIN_RECENT_MIN = 8     # 12 → 8
MAX_INJURY_GAP = 12    # 7  → 12
MIN_CURR_GAMES = 3
DB = 'predictor_v12.db'

# Runtime config (UI'dan değiştirilebilir)
RUNTIME_CONFIG = {
    'odds_api_key': os.getenv('ODDS_API_KEY', ''),
    'default_bookmakers': ['draftkings', 'fanduel', 'betmgm', 'pinnacle', 'bet365']
}

ODDS_API_URL = 'https://api.the-odds-api.com/v4/sports/basketball_nba'

MODEL_WEIGHTS = {
    'xgb': 0.35, 'lgb': 0.35, 'gbm': 0.20, 'rf': 0.10
} if ADVANCED_ML else {'gbm': 0.6, 'rf': 0.4}

CV_LIMITS = {
    'PTS': 0.40, 'REB': 0.50, 'AST': 0.55,
    'STL': 0.70, 'BLK': 0.75, 'TOV': 0.65, 'PF': 0.65,
    'FG3M': 0.68, 'FGM': 0.48, 'FTM': 0.65, 'FTA': 0.65,
    'FGA': 0.50, 'FG3A': 0.58,
    'PRA': 0.45, 'P+R': 0.48, 'P+A': 0.48, 'A+R': 0.55, 'S+B': 0.70,
}

FLOOR = {
    'PTS': 5.0,  'REB': 1.5,  'AST': 1.0,
    'STL': 0.2,  'BLK': 0.2,  'TOV': 0.3,  'PF': 0.5,
    'FG3M': 0.4, 'FGM': 1.2,  'FTM': 0.4,  'FTA': 0.4,
    'FGA': 3.0,  'FG3A': 0.8,
    'PRA': 7.0,  'P+R': 6.0,  'P+A': 6.0,  'A+R': 2.0,  'S+B': 0.3,
}

STAT_POSITION_WEIGHT = {
    'PTS':(1.05,1.00,1.10),'FGM':(1.05,1.00,1.10),'FGA':(1.05,1.00,1.10),
    'FG3M':(1.08,1.00,0.95),'FG3A':(1.08,1.00,0.92),'FTM':(1.00,1.00,1.05),
    'FTA':(1.00,1.00,1.05),'AST':(1.08,1.00,0.92),'REB':(0.90,1.00,1.15),
    'BLK':(0.80,1.00,1.20),'STL':(1.10,1.00,0.85),'TOV':(1.05,1.00,0.95),
    'PF':(0.90,1.00,1.10),'PRA':(1.00,1.00,1.05),'P+R':(0.98,1.00,1.08),
    'P+A':(1.05,1.00,0.95),'A+R':(0.95,1.00,1.05),'S+B':(1.00,1.00,1.05),
}

STAT_TO_ODDS_MARKET = {
    'PTS': 'player_points', 'REB': 'player_rebounds', 'AST': 'player_assists',
    'STL': 'player_steals', 'BLK': 'player_blocks',
    'P+R': 'player_points_rebounds', 'P+A': 'player_points_assists',
    'A+R': 'player_rebounds_assists', 'PRA': 'player_points_rebounds_assists',
    'FG3M': 'player_threes', 'S+B': 'player_blocks_steals'
}

ODDS_BOOKMAKER_NAMES = {
    'draftkings': 'DK', 'fanduel': 'FD', 'betmgm': 'MGM',
    'pinnacle': 'PIN', 'bet365': 'B365', 'williamhill_us': 'Caesars',
    'bovada': 'Bov', 'betus': 'BetUS'
}

ALL_STATS = ['PTS','REB','AST','STL','BLK','TOV','PF',
             'FG3M','FGM','FTM','FTA','FGA','FG3A',
             'PRA','P+R','P+A','A+R','S+B']

# ─── GLOBAL STATE ─────────────────────────────────────────────
_cache: Dict = {}
_cache_lock = threading.Lock()
_lig_data: Dict = {}
_curr_s: str = ''
_prev_s: str = ''
_prog = {'pct':0,'msg':'','total':0,'done':0,'active':False}
_prog_lock = threading.Lock()
_recent_def: Dict = {}
_team_rosters: Dict = {}
_rosters_lock = threading.Lock()
_injury_cache: Dict = {}
_injury_date: str = ''
_injury_lock = threading.Lock()
ESPN_INJURY_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries'
_model_cache: Dict = {}
_model_cache_lock = threading.Lock()
_odds_cache: Dict = {}
_odds_cache_time: Dict = {}
_odds_lock = threading.Lock()

# Rakip pozisyon bazlı savunma verisi
_opp_def_profile: Dict = {}  # {team_abbr: {guard: {PTS: x, AST: x}, forward: {...}, center: {...}}}
_def_profile_lock = threading.Lock()

# Hit rate geçmişi (Kelly için)
_hit_rate_cache: Dict = {}  # {stat: hit_rate}
_hit_rate_lock = threading.Lock()

# ─── RATE LIMITER ─────────────────────────────────────────────

class RateLimiter:
    """NBA API için token bucket rate limiter"""
    def __init__(self, calls_per_minute=20, min_interval=0.5):
        self.calls_per_minute = calls_per_minute
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._timestamps = deque()
        self._last_call = 0

    def wait(self):
        with self._lock:
            now = time.time()
            # Min interval
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
                now = time.time()
            # Per-minute limit
            self._timestamps = deque(t for t in self._timestamps if now - t < 60)
            if len(self._timestamps) >= self.calls_per_minute:
                oldest = self._timestamps[0]
                sleep_time = 60 - (now - oldest) + 0.1
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.time()
                    self._timestamps = deque(t for t in self._timestamps if now - t < 60)
            self._timestamps.append(now)
            self._last_call = now

nba_limiter = RateLimiter(calls_per_minute=20, min_interval=0.5)

def nba_request(func, *args, max_retries=4, **kwargs):
    """Rate-limited NBA API request with exponential backoff"""
    for attempt in range(max_retries):
        try:
            nba_limiter.wait()
            return func(*args, **kwargs).get_data_frames()
        except Exception as e:
            err = str(e).lower()
            if '429' in err or 'rate' in err or 'timeout' in err:
                wait = (2 ** attempt) * 1.5
                log.warning(f"NBA API rate limit/timeout (attempt {attempt+1}), waiting {wait:.1f}s")
                time.sleep(wait)
            elif attempt == max_retries - 1:
                log.debug(f"NBA API failed after {max_retries} attempts: {e}")
                raise
            else:
                time.sleep(0.8 * (attempt + 1))
    return None

# ─── UTILS ────────────────────────────────────────────────────

def _norm_name(name: str) -> str:
    import unicodedata, re
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r"[^a-z ]", "", name.lower()).strip()

def fetch_injury_report(date_str: str):
    global _injury_date
    with _injury_lock:
        if _injury_date == date_str and _injury_cache:
            return
    try:
        resp = requests.get(ESPN_INJURY_URL, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        data = resp.json()
        new_cache: Dict = {}
        for team_entry in data.get('injuries', []):
            for injury in team_entry.get('injuries', []):
                athlete = injury.get('athlete', {})
                raw_name = athlete.get('displayName', '')
                status = injury.get('status', '')
                if raw_name:
                    new_cache[_norm_name(raw_name)] = status
        with _injury_lock:
            _injury_cache.clear()
            _injury_cache.update(new_cache)
            _injury_date = date_str
        log.info(f"Injury report: {len(new_cache)} players")
    except Exception as e:
        log.warning(f"Injury fetch failed: {e}")

def is_injured(name: str) -> bool:
    with _injury_lock:
        if not _injury_cache:
            return False
        status = _injury_cache.get(_norm_name(name), '')
    return status.lower() in ('out', 'doubtful')

def prog_set(pct, msg='', done=None, total=None):
    with _prog_lock:
        _prog['pct'] = min(int(pct), 99)
        _prog['active'] = True
        if msg: _prog['msg'] = msg
        if done is not None: _prog['done'] = done
        if total is not None: _prog['total'] = total

def prog_done(msg='Tamamlandı'):
    with _prog_lock:
        _prog['pct'] = 100
        _prog['msg'] = msg
        _prog['active'] = False

def seasons(date_str):
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    y = dt.year
    if dt.month >= 9:
        return f"{y}-{str(y+1)[-2:]}", f"{y-1}-{str(y)[-2:]}"
    return f"{y-1}-{str(y)[-2:]}", f"{y-2}-{str(y-1)[-2:]}"

def db_init():
    with sqlite3.connect(DB) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS predictions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Tarih TEXT, Oyuncu TEXT, Takim TEXT, Rakip TEXT,
            Stat TEXT, Tahmin REAL, Barem REAL, Risk REAL, Guven INTEGER,
            Models TEXT, MarketLine REAL, Edge REAL, BestBookmaker TEXT,
            Trend TEXT, HitRate REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS slips(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Tarih TEXT, KuponAdi TEXT, Icerik TEXT,
            ToplamSecim INTEGER, OrtEdge REAL, OrtGuven REAL,
            OrtValue REAL, Timestamp TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS backtest_results(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            TestDate TEXT, TrainUntil TEXT, Oyuncu TEXT, Takim TEXT,
            Rakip TEXT, Stat TEXT, Tahmin REAL, Gercek REAL,
            Barem REAL, Hit INTEGER, AbsError REAL,
            Timestamp TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS hit_rates(
            Stat TEXT PRIMARY KEY, Hits INTEGER, Total INTEGER,
            HitRate REAL, AvgError REAL, LastUpdated TEXT)''')
        c.commit()

def get_data(pid):
    with _cache_lock:
        if pid in _cache:
            return _cache[pid].copy()
    combined = pd.DataFrame()
    for s in [_prev_s, _curr_s]:
        try:
            dfs = nba_request(playergamelog.PlayerGameLog, player_id=pid, season=s)
            if dfs:
                df = dfs[0]
                combined = pd.concat([combined, df], ignore_index=True)
        except Exception as e:
            log.debug(f"get_data pid={pid} season={s}: {e}")

    if not combined.empty:
        for col in ['PTS','REB','AST','STL','BLK']:
            if col not in combined.columns:
                combined[col] = 0
        combined['PRA'] = combined[['PTS','REB','AST']].sum(axis=1)
        combined['P+R'] = combined[['PTS','REB']].sum(axis=1)
        combined['P+A'] = combined[['PTS','AST']].sum(axis=1)
        combined['A+R'] = combined[['AST','REB']].sum(axis=1)
        combined['S+B'] = combined[['STL','BLK']].sum(axis=1)

    with _cache_lock:
        if len(_cache) > 200:
            for k in list(_cache.keys())[:50]:
                del _cache[k]
        _cache[pid] = combined
    return combined.copy()

# ─── TREND DETECTION ──────────────────────────────────────────

def detect_trend(df: pd.DataFrame, stat: str) -> dict:
    """HOT/COLD/NEUTRAL trend tespiti"""
    if stat not in df.columns or len(df) < 8:
        return {'trend': 'NEUTRAL', 'pct': 0, 'label': ''}

    season_avg = df[stat].mean()
    recent_avg = df[stat].tail(5).mean()

    if season_avg == 0:
        return {'trend': 'NEUTRAL', 'pct': 0, 'label': ''}

    pct_diff = ((recent_avg - season_avg) / season_avg) * 100

    # Tutarlılık skoru: son 5 maçın kaçı ortalamanın üstünde?
    above_avg = (df[stat].tail(5) > season_avg).sum()

    if pct_diff >= 20 and above_avg >= 4:
        return {'trend': 'HOT', 'pct': round(pct_diff, 1), 'label': '🔥'}
    elif pct_diff <= -20 and above_avg <= 1:
        return {'trend': 'COLD', 'pct': round(pct_diff, 1), 'label': '❄️'}
    elif pct_diff >= 12 and above_avg >= 3:
        return {'trend': 'WARM', 'pct': round(pct_diff, 1), 'label': '📈'}
    elif pct_diff <= -12 and above_avg <= 2:
        return {'trend': 'COOLING', 'pct': round(pct_diff, 1), 'label': '📉'}
    else:
        return {'trend': 'NEUTRAL', 'pct': round(pct_diff, 1), 'label': ''}

# ─── OPPONENT DEFENSE PROFILE ─────────────────────────────────

def build_opp_def_profiles(season: str):
    """Takımların pozisyon bazlı savunma profillerini oluştur"""
    global _opp_def_profile
    log.info("Building opponent defense profiles...")

    abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}

    try:
        # Her takımın verdiği istatistikleri analiz et
        # Pozisyon: G=Guard, F=Forward, C=Center
        profiles = {}

        dfs = nba_request(
            leaguedashteamstats.LeagueDashTeamStats,
            season=season,
            measure_type_detailed_defense='Opponent'
        )
        if not dfs or dfs[0].empty:
            return

        opp_df = dfs[0]

        for _, row in opp_df.iterrows():
            abbr = abbr_map.get(row['TEAM_ID'])
            if not abbr:
                continue
            profiles[abbr] = {
                'opp_pts': row.get('OPP_PTS', 0),
                'opp_reb': row.get('OPP_REB', 0),
                'opp_ast': row.get('OPP_AST', 0),
            }

        with _def_profile_lock:
            _opp_def_profile.update(profiles)

        log.info(f"Defense profiles built for {len(profiles)} teams")
    except Exception as e:
        log.warning(f"Defense profile build failed: {e}")

def get_opp_def_factor(opp_abbr: str, stat: str, position: str) -> float:
    """Rakip savunma faktörü döndür (1.0 = ortalama)"""
    with _def_profile_lock:
        if not _opp_def_profile or opp_abbr not in _opp_def_profile:
            return 1.0

    profile = _opp_def_profile.get(opp_abbr, {})

    # Pozisyon bazlı ağırlık
    pos_str = str(position).upper()
    is_guard = 'G' in pos_str
    is_center = 'C' in pos_str

    stat_map = {
        'PTS': 'opp_pts', 'REB': 'opp_reb', 'AST': 'opp_ast',
        'PRA': 'opp_pts', 'P+R': 'opp_pts', 'P+A': 'opp_pts'
    }

    key = stat_map.get(stat)
    if not key or key not in profile:
        return 1.0

    # Tüm takımların ortalaması
    all_vals = [p.get(key, 0) for p in _opp_def_profile.values() if p.get(key, 0) > 0]
    if not all_vals:
        return 1.0

    avg = np.mean(all_vals)
    team_val = profile[key]

    if avg == 0:
        return 1.0

    return round(team_val / avg, 3)

# ─── HIT RATE & KELLY ─────────────────────────────────────────

def load_hit_rates() -> Dict:
    """DB'den geçmiş hit rate'leri yükle"""
    try:
        with sqlite3.connect(DB) as conn:
            rows = conn.execute("SELECT Stat, HitRate, AvgError FROM hit_rates").fetchall()
            return {r[0]: {'hit_rate': r[1], 'avg_error': r[2]} for r in rows}
    except:
        return {}

def update_hit_rates():
    """Backtest sonuçlarından hit rate güncelle"""
    try:
        with sqlite3.connect(DB) as conn:
            rows = conn.execute("""
                SELECT Stat,
                    COUNT(*) as total,
                    SUM(Hit) as hits,
                    AVG(AbsError) as avg_err
                FROM backtest_results
                WHERE Hit IS NOT NULL
                GROUP BY Stat
            """).fetchall()

            for stat, total, hits, avg_err in rows:
                hit_rate = (hits / total) if total > 0 else 0.52
                conn.execute("""
                    INSERT OR REPLACE INTO hit_rates (Stat, Hits, Total, HitRate, AvgError, LastUpdated)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (stat, hits or 0, total, round(hit_rate, 3), round(avg_err or 2.0, 2),
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()

        with _hit_rate_lock:
            _hit_rate_cache.clear()
            _hit_rate_cache.update(load_hit_rates())

        log.info(f"Hit rates updated for {len(rows)} stats")
    except Exception as e:
        log.warning(f"Hit rate update failed: {e}")

def kelly_criterion(pred: float, line: float, market_odds: float, stat: str) -> float:
    """Gerçekçi Kelly fraction hesapla"""
    if market_odds <= 1 or line <= 0:
        return 0

    # Geçmiş hit rate'i kullan (yoksa varsayılan)
    with _hit_rate_lock:
        stat_data = _hit_rate_cache.get(stat, {})
    our_prob = stat_data.get('hit_rate', 0.52)

    # Edge'e göre prob ayarla
    edge_ratio = (pred - line) / (line + 1e-6)
    if edge_ratio > 0.1:
        our_prob = min(0.72, our_prob + edge_ratio * 0.5)
    elif edge_ratio < -0.05:
        our_prob = max(0.35, our_prob + edge_ratio * 0.3)

    b = market_odds - 1
    kelly = ((b * our_prob) - (1 - our_prob)) / b if b > 0 else 0
    return max(0, min(kelly * 0.25, 0.05))  # Quarter Kelly, max %5 bankroll

# ─── THE ODDS API ─────────────────────────────────────────────

class OddsAPIClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = ODDS_API_URL
        self.session = requests.Session()

    def get_events(self, date_str: str) -> List[Dict]:
        if not self.api_key:
            return []
        cache_key = f"events_{date_str}"
        with _odds_lock:
            if cache_key in _odds_cache:
                if datetime.now() - _odds_cache_time.get(cache_key, datetime.min) < timedelta(minutes=5):
                    return _odds_cache[cache_key]
        try:
            url = f"{self.base_url}/events"
            params = {
                'apiKey': self.api_key, 'regions': 'us',
                'oddsFormat': 'decimal',
                'commenceTimeFrom': f"{date_str}T00:00:00Z",
                'commenceTimeTo': f"{date_str}T23:59:59Z"
            }
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            events = resp.json()
            with _odds_lock:
                _odds_cache[cache_key] = events
                _odds_cache_time[cache_key] = datetime.now()
            return events
        except Exception as e:
            log.error(f"Odds API events error: {e}")
            return []

    def get_player_props(self, event_id: str, bookmakers: List[str] = None) -> Dict:
        if not self.api_key:
            return {}
        bookmakers = bookmakers or RUNTIME_CONFIG['default_bookmakers']
        markets = list(STAT_TO_ODDS_MARKET.values())
        cache_key = f"props_{event_id}"
        with _odds_lock:
            if cache_key in _odds_cache:
                if datetime.now() - _odds_cache_time.get(cache_key, datetime.min) < timedelta(minutes=3):
                    return _odds_cache[cache_key]
        try:
            url = f"{self.base_url}/events/{event_id}/odds"
            params = {
                'apiKey': self.api_key, 'regions': 'us',
                'markets': ','.join(markets),
                'bookmakers': ','.join(bookmakers),
                'oddsFormat': 'decimal'
            }
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 422:
                return {}
            resp.raise_for_status()
            parsed = self._parse_player_props(resp.json())
            with _odds_lock:
                _odds_cache[cache_key] = parsed
                _odds_cache_time[cache_key] = datetime.now()
            return parsed
        except Exception as e:
            log.error(f"Odds API props error for {event_id}: {e}")
            return {}

    def _parse_player_props(self, data: Dict) -> Dict:
        result = {}
        for bm in data.get('bookmakers', []):
            bm_key = bm['key']
            for market in bm.get('markets', []):
                market_key = market['key']
                for outcome in market.get('outcomes', []):
                    player_name = outcome.get('description', outcome.get('name', ''))
                    norm = _norm_name(player_name)
                    line = outcome.get('point', 0)
                    odds = outcome.get('price', 0)
                    if norm not in result:
                        result[norm] = {}
                    if market_key not in result[norm]:
                        result[norm][market_key] = {}
                    if bm_key not in result[norm][market_key] or odds > result[norm][market_key][bm_key].get('over_odds', 0):
                        result[norm][market_key][bm_key] = {
                            'line': line,
                            'over_odds': odds,
                            'bookmaker': ODDS_BOOKMAKER_NAMES.get(bm_key, bm_key)
                        }
        return result

    def find_best_line(self, props: Dict, player_norm: str, stat: str) -> Optional[Dict]:
        market = STAT_TO_ODDS_MARKET.get(stat)
        if not market:
            return None
        market_data = props.get(player_norm, {}).get(market, {})
        if not market_data:
            return None
        best = None
        best_odds = 0
        for bm_key, data in market_data.items():
            if data.get('over_odds', 0) > best_odds:
                best_odds = data['over_odds']
                best = {
                    'line': data['line'],
                    'odds': data['over_odds'],
                    'implied_prob': 1 / data['over_odds'] if data['over_odds'] > 0 else 0,
                    'bookmaker': data.get('bookmaker', bm_key),
                    'bookmaker_key': bm_key,
                    'all_lines': {k: v['line'] for k, v in market_data.items()}
                }
        return best

def get_odds_client() -> Optional[OddsAPIClient]:
    key = RUNTIME_CONFIG.get('odds_api_key', '')
    if not key:
        return None
    return OddsAPIClient(key)

# ─── FEATURE ENGINEERING ──────────────────────────────────────

def create_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 3:   # 5 → 3
        return df
    df = df.sort_values('GAME_DATE').reset_index(drop=True)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df['REST_DAYS'] = df['GAME_DATE'].diff().dt.days.fillna(7)
    df['OPP'] = df['MATCHUP'].apply(lambda x: x.split()[-1])
    df['HOME'] = df['MATCHUP'].apply(lambda x: 1 if 'vs.' in x else 0)
    df['SEASON_PART'] = np.where(df.index >= len(df)//2, 1, 0)
    core_stats = ['PTS','REB','AST','STL','BLK','TOV','MIN','FGA','FGM','FTA','FTM']
    for col in core_stats:
        if col not in df.columns:
            continue
        for span in [3, 5, 7, 10]:
            df[f'{col}_EMA_{span}'] = df[col].ewm(span=span, adjust=False).mean()
            df[f'{col}_EWM_STD_{span}'] = df[col].ewm(span=span, adjust=False).std()
        for window in [3, 5, 10, 15]:
            if len(df) >= window:
                df[f'{col}_ROLL_{window}'] = df[col].rolling(window, min_periods=1).mean()
                df[f'{col}_ROLL_STD_{window}'] = df[col].rolling(window, min_periods=1).std()
                df[f'{col}_MOM_{window}'] = df[col] / (df[f'{col}_ROLL_{window}'] + 1e-6)
        for lag in [1, 2, 3]:
            df[f'{col}_LAG_{lag}'] = df[col].shift(lag)
        if len(df) >= 5:
            df[f'{col}_TREND_5'] = df[col].rolling(5, min_periods=3).apply(
                lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) >= 3 else 0, raw=True
            )
    if 'MIN' in df.columns and 'FGA' in df.columns:
        df['USAGE_RATE'] = df['FGA'] / (df['MIN'] + 1e-6) * 36
        df['TS_PCT'] = df['PTS'] / (2 * (df['FGA'] + 0.44 * df.get('FTA', 0)) + 1e-6)
    df['B2B'] = (df['REST_DAYS'] <= 1).astype(int)
    games_last_7 = []
    for i, row in df.iterrows():
        curr_date = row['GAME_DATE']
        count = df[(df['GAME_DATE'] >= curr_date - timedelta(days=7)) &
                   (df['GAME_DATE'] < curr_date)].shape[0]
        games_last_7.append(count)
    df['GAMES_LAST_7'] = games_last_7
    df['REST_HOME_INT'] = df['REST_DAYS'] * df['HOME']
    return df.fillna(0)

# ─── ML PIPELINE ──────────────────────────────────────────────

class MLPipeline:
    def get_cache_key(self, pid, stat):
        return f"{pid}_{stat}_{_curr_s}"

    def _sample_weights(self, n: int) -> np.ndarray:
        """Son maçlara daha yüksek ağırlık ver (üstel azalma)"""
        w = np.exp(np.linspace(0, 1.5, n))
        return w / w.sum()

    def _select_features(self, df: pd.DataFrame, stat: str, feature_cols: list) -> list:
        """Stat'a göre en ilgili feature'ları seç — gürültüyü azalt"""
        stat_base = stat.split('+')[0].replace('PRA','PTS')
        priority = []
        for c in feature_cols:
            # Stat ile doğrudan ilgili feature'lar önce gelsin
            if stat_base in c or stat.replace('+','') in c:
                priority.append((0, c))
            elif any(x in c for x in ['EMA','ROLL','LAG','TREND','MOM']):
                priority.append((1, c))
            elif c in ['HOME','REST_DAYS','B2B','GAMES_LAST_7','USAGE_RATE','SEASON_PART']:
                priority.append((2, c))
            else:
                priority.append((3, c))
        priority.sort(key=lambda x: x[0])
        # Max 40 feature — fazlası overfitting yapar
        return [c for _, c in priority[:40]]

    def train(self, df: pd.DataFrame, stat: str, pid: int):
        cache_key = self.get_cache_key(pid, stat)
        with _model_cache_lock:
            if cache_key in _model_cache:
                return _model_cache[cache_key]
        if len(df) < 6:   # 12 → 6
            return None
        exclude = ['GAME_DATE','MATCHUP','OPP','PLAYER_ID','SEASON', stat]
        all_feature_cols = [c for c in df.columns if c not in exclude
                        and df[c].dtype in ['float64','int64','float32','int32']]
        if len(all_feature_cols) < 3:   # 5 → 3
            return None

        feature_cols = self._select_features(df, stat, all_feature_cols)

        X = df[feature_cols].iloc[:-1]
        y = df[stat].iloc[1:]
        if len(X) != len(y):
            min_len = min(len(X), len(y))
            X, y = X.iloc[:min_len], y.iloc[:min_len]

        # Son maçlara ağırlık ver
        sample_w = self._sample_weights(len(X))

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        models = {}
        if ADVANCED_ML:
            models['xgb'] = xgb.XGBRegressor(
                n_estimators=150, max_depth=3, learning_rate=0.04,
                subsample=0.75, colsample_bytree=0.75, gamma=0.15,
                min_child_weight=3, reg_alpha=0.1, reg_lambda=1.5,
                random_state=42, n_jobs=-1
            )
            models['lgb'] = lgb.LGBMRegressor(
                n_estimators=150, max_depth=3, learning_rate=0.04,
                num_leaves=20, subsample=0.75, colsample_bytree=0.75,
                min_child_samples=5, reg_alpha=0.1, reg_lambda=1.5,
                random_state=42, n_jobs=-1, verbose=-1
            )
        models['gbm'] = GradientBoostingRegressor(
            n_estimators=100, max_depth=3, learning_rate=0.04,
            subsample=0.8, min_samples_leaf=3, random_state=42
        )
        models['rf'] = RandomForestRegressor(
            n_estimators=100, max_depth=4, min_samples_leaf=3,
            random_state=42, n_jobs=-1
        )
        for name, model in list(models.items()):
            try:
                if name in ['xgb', 'lgb']:
                    model.fit(X_scaled, y, sample_weight=sample_w)
                else:
                    model.fit(X, y, sample_weight=sample_w)
            except Exception as e:
                log.debug(f"Training failed for {name}: {e}")
                del models[name]

        # Cross-val ile her modelin bireysel hatasını ölç → dinamik ağırlık
        model_errors = {}
        if len(X) > 12:   # 24 → 12
            n_splits = 3 if len(X) > 18 else 2
            tscv = TimeSeriesSplit(n_splits=n_splits)
            for mname, model in models.items():
                errs = []
                for train_idx, val_idx in tscv.split(X):
                    try:
                        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
                        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]
                        sw_tr = self._sample_weights(len(X_tr))
                        m_tmp = type(model)(**model.get_params())
                        if mname in ['xgb', 'lgb']:
                            Xtr_s = scaler.transform(X_tr)
                            Xval_s = scaler.transform(X_val)
                            m_tmp.fit(Xtr_s, y_tr, sample_weight=sw_tr)
                            pred_v = m_tmp.predict(Xval_s[-1:].reshape(1,-1))[0]
                        else:
                            m_tmp.fit(X_tr, y_tr, sample_weight=sw_tr)
                            pred_v = m_tmp.predict(X_val.iloc[[-1]])[0]
                        errs.append(abs(float(y_val.iloc[-1]) - float(pred_v)))
                    except:
                        continue
                if errs:
                    model_errors[mname] = np.mean(errs)

        cv_error = np.mean(list(model_errors.values())) if model_errors else 2.0

        result = {
            'models': models, 'scaler': scaler, 'feature_cols': feature_cols,
            'cv_error': cv_error, 'model_errors': model_errors,
            'last_X': X.iloc[-1:] if len(X) > 0 else None,
            'last_X_scaled': scaler.transform(X.iloc[-1:]) if len(X) > 0 else None
        }
        with _model_cache_lock:
            _model_cache[cache_key] = result
        return result

    def predict(self, model_data: dict, stat: str) -> Optional[dict]:
        if not model_data:
            return None
        models = model_data['models']
        last_X = model_data['last_X']
        last_X_scaled = model_data['last_X_scaled']
        model_errors = model_data.get('model_errors', {})

        predictions = {}
        for name, model in models.items():
            try:
                if name in ['xgb', 'lgb']:
                    pred = model.predict(last_X_scaled.reshape(1, -1))[0]
                else:
                    pred = model.predict(last_X)[0]
                predictions[name] = max(0, float(pred))
            except Exception as e:
                log.debug(f"Prediction failed for {name}: {e}")
        if not predictions:
            return None

        # Dinamik ağırlık: CV hatası daha düşük model → daha yüksek ağırlık
        if model_errors and all(k in model_errors for k in predictions.keys()):
            inv_err = {k: 1.0 / (model_errors[k] + 0.5) for k in predictions}
            total_inv = sum(inv_err.values())
            weights = {k: v / total_inv for k, v in inv_err.items()}
        else:
            weights = {k: MODEL_WEIGHTS.get(k, 0.2) for k in predictions.keys()}
            total_w = sum(weights.values())
            weights = {k: v/total_w for k,v in weights.items()}

        ensemble = sum(p * weights[m] for m, p in predictions.items())
        disagreement = np.std(list(predictions.values()))
        cv_err = model_data['cv_error']

        # Güven: CV hatası ve model uyumu birlikte
        if ensemble > 0:
            rel_err = cv_err / (ensemble + 1e-6)
            accuracy = max(0, 1 - rel_err)
            disag_penalty = min(disagreement / (ensemble + 1e-6) * 30, 20)
            confidence = int(min(95, max(15, accuracy * 100 - disag_penalty)))
        else:
            confidence = 30

        return {
            'pred': ensemble,
            'predictions': predictions,
            'confidence': confidence,
            'disagreement': disagreement,
            'cv_error': cv_err,
            'dyn_weights': weights
        }

ml_pipe = MLPipeline()

# ─── PREDICTION LOGIC ─────────────────────────────────────────

def calc_blowout(df, team_abbr, opp_abbr, raw):
    own_wpct = _lig_data.get(team_abbr, {}).get('W_PCT', 0.5)
    opp_wpct = _lig_data.get(opp_abbr, {}).get('W_PCT', 0.5)
    wpct_diff = own_wpct - opp_wpct
    blowout_risk = False
    blowout_mod = 1.0
    is_underdog = wpct_diff < 0
    if abs(wpct_diff) < 0.22:
        return blowout_risk, blowout_mod, is_underdog
    recent_pm = df['PLUS_MINUS'].tail(5).mean() if 'PLUS_MINUS' in df.columns else 0.0
    margin_diff = _lig_data.get(team_abbr, {}).get('AVG_MARGIN', 0.0) - _lig_data.get(opp_abbr, {}).get('AVG_MARGIN', 0.0)
    blowout_score = abs(wpct_diff)*0.50 + min(abs(margin_diff)/20, 0.30)*0.30 + min(abs(recent_pm)/15, 0.20)*0.20
    if blowout_score < 0.28:
        return blowout_risk, blowout_mod, is_underdog
    blowout_risk = True
    avg_min = raw['MIN'].mean()
    if avg_min >= 32.0: blowout_mod = 0.82 if is_underdog else 0.87
    elif avg_min >= 27.0: blowout_mod = 0.92 if is_underdog else 0.93
    elif avg_min >= 22.0: blowout_mod = 1.00
    else: blowout_mod = 1.20 if is_underdog else 1.12
    return blowout_risk, blowout_mod, is_underdog

def predict_player(pid, name, team_abbr, opp_abbr, is_home, date_str, position, odds_props: Dict = None):
    raw = get_data(pid)
    if raw.empty or len(raw) < MIN_GAMES:
        return []
    raw['GAME_DATE'] = pd.to_datetime(raw['GAME_DATE'])
    target = pd.to_datetime(date_str)
    history = raw[raw['GAME_DATE'] < target].sort_values('GAME_DATE')
    if len(history) < 6:          # 12 → 6
        return []
    if is_injured(name):
        return []
    if (target - history['GAME_DATE'].iloc[-1]).days > MAX_INJURY_GAP:
        return []
    if history.tail(3)['MIN'].mean() < MIN_RECENT_MIN:
        return []
    if raw['MIN'].mean() < MIN_AVG_MIN:
        return []
    # Son maç 0 dakika → muhtemelen DNP, atla
    if len(history) >= 1 and history['MIN'].iloc[-1] == 0:
        # Son 3 maçın 2'si de 0 ise atla, tek seferlik DNP'ye izin ver
        if len(history) >= 3 and history['MIN'].tail(3).sum() == 0:
            return []

    df_feat = create_advanced_features(history.copy())
    if df_feat.empty or len(df_feat) < 3:   # 5 → 3
        return []

    blowout_risk, blowout_mod, is_underdog = calc_blowout(df_feat, team_abbr, opp_abbr, raw)
    opp_reb_mod = _lig_data.get(opp_abbr, {}).get('REB_MOD', 1.0)
    def_mod = _lig_data.get(opp_abbr, {}).get('DEF_MOD', 1.0)
    pace_mod = _lig_data.get(opp_abbr, {}).get('PACE_MOD', 1.0)
    pos_str = str(position).upper()
    is_guard = 'G' in pos_str
    is_center = 'C' in pos_str
    rest = (target - history['GAME_DATE'].iloc[-1]).days
    norm_name = _norm_name(name)

    results = []

    for stat in ALL_STATS:
        if stat not in df_feat.columns:
            continue
        avg = df_feat[stat].mean()
        if avg < FLOOR.get(stat, 0):
            continue
        cv = df_feat[stat].std() / (avg + 0.1)
        if cv > CV_LIMITS.get(stat, 0.40):
            continue

        model_data = ml_pipe.train(df_feat, stat, pid)
        if not model_data:
            continue
        pred_result = ml_pipe.predict(model_data, stat)
        if not pred_result:
            continue

        pred = pred_result['pred']

        # Home/away modifier
        if is_home:
            home_avg = df_feat[df_feat['HOME'] == 1][stat].mean()
            if not np.isnan(home_avg) and avg > 0:
                pred *= min(max(home_avg/avg, 0.90), 1.15)
        else:
            away_avg = df_feat[df_feat['HOME'] == 0][stat].mean()
            if not np.isnan(away_avg) and avg > 0:
                pred *= min(max(away_avg/avg, 0.87), 1.10)

        # Rest modifier
        if rest <= 1: pred *= 0.94
        elif rest >= 3: pred *= 1.03

        pred *= blowout_mod

        # H2H
        h2h = df_feat[df_feat['OPP'] == opp_abbr][stat]
        if len(h2h) >= 2:
            pred = pred * 0.82 + h2h.mean() * 0.18

        # Position weight
        pw = STAT_POSITION_WEIGHT.get(stat, (1.0, 1.0, 1.0))
        pos_mult = pw[0] if is_guard else (pw[2] if is_center else pw[1])
        pred *= (def_mod ** pos_mult) * (1 + (pace_mod - 1) * 0.45)

        if stat in ('REB', 'PRA', 'P+R', 'A+R'):
            pred *= (2.0 - opp_reb_mod)

        # Rakip pozisyon bazlı savunma faktörü
        opp_def_factor = get_opp_def_factor(opp_abbr, stat, position)
        pred *= (0.7 + opp_def_factor * 0.3)  # Hafif uygula

        # Trend tespiti
        trend_info = detect_trend(df_feat, stat)
        # HOT oyuncu için pred'i hafifçe artır
        if trend_info['trend'] == 'HOT':
            pred *= 1.04
        elif trend_info['trend'] == 'COLD':
            pred *= 0.96

        # Market line
        market_line = None
        best_bookmaker = None
        market_odds = None
        all_lines = {}

        if odds_props:
            client = get_odds_client()
            if client:
                best_odds = client.find_best_line(odds_props, norm_name, stat)
                if best_odds:
                    market_line = best_odds['line']
                    best_bookmaker = best_odds['bookmaker']
                    market_odds = best_odds['odds']
                    all_lines = best_odds.get('all_lines', {})

        if market_line is None or market_line == 0:
            market_line = round(pred * 0.94, 1)
            market_line = max(market_line, 0.1)
            best_bookmaker = 'Model'
            market_odds = 1.90

        edge = pred - market_line
        edge_pct = ((pred - market_line) / market_line) * 100 if market_line > 0 else 0

        # Gerçekçi Kelly
        kelly_frac = kelly_criterion(pred, market_line, market_odds, stat)

        # Risk
        base_risk = cv * 65
        model_gap_risk = pred_result['disagreement'] * 30
        rest_risk = 6 if rest <= 1 else 0
        market_risk = 5 if abs(edge) < 1 else 0
        trend_risk = -5 if trend_info['trend'] in ('HOT','COLD') else 0  # Güçlü trend = daha az risk
        total_risk = min(95, base_risk + model_gap_risk + rest_risk + market_risk + trend_risk)

        results.append({
            'player': str(name),
            'pid': int(pid),
            'team': str(team_abbr),
            'opp': str(opp_abbr),
            'stat': str(stat),
            'pred': float(round(pred, 1)),
            'avg': float(round(avg, 1)),
            'floor': float(round(df_feat[stat].quantile(0.20), 1)),
            'ceiling': float(round(df_feat[stat].quantile(0.80), 1)),
            'risk': float(round(total_risk, 1)),
            'conf': int(pred_result['confidence']),
            'disagreement': round(pred_result['disagreement'], 3),
            'models': list(pred_result['predictions'].keys()),
            'b2b': bool(rest <= 1),
            'home': bool(is_home),
            'blowout': bool(blowout_risk),
            'underdog': bool(is_underdog),
            'line': float(market_line),
            'edge': float(round(edge, 1)),
            'edge_pct': float(round(edge_pct, 1)),
            'best_bookmaker': best_bookmaker,
            'market_odds': market_odds,
            'all_lines': all_lines,
            'kelly': round(kelly_frac * 100, 2),
            'cv': round(cv, 2),
            'last10': [float(v) for v in df_feat[stat].tail(10).tolist()],
            'has_market_odds': best_bookmaker != 'Model',
            'trend': trend_info['trend'],
            'trend_pct': trend_info['pct'],
            'trend_label': trend_info['label'],
            'position': position,
            'h2h_games': int(len(h2h)),
            'h2h_avg': float(round(h2h.mean(), 1)) if len(h2h) > 0 else None,
        })

    return results

# ─── LEAGUE DATA ──────────────────────────────────────────────

def _load_lig(season):
    global _lig_data
    try:
        dfs_adv = nba_request(leaguedashteamstats.LeagueDashTeamStats,
                               season=season, measure_type_detailed_defense='Advanced')
        dfs_base = nba_request(leaguedashteamstats.LeagueDashTeamStats,
                                season=season, measure_type_detailed_defense='Base')
        if not dfs_adv or not dfs_base:
            return
        df, df2 = dfs_adv[0], dfs_base[0]
        id2abbr = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}
        avg_def = df['DEF_RATING'].mean()
        avg_pace = df['PACE'].mean()
        avg_reb = df['REB_PCT'].mean() if 'REB_PCT' in df.columns else 0.50
        pm_map = dict(zip(df2['TEAM_ID'], df2['PLUS_MINUS'])) if 'PLUS_MINUS' in df2.columns else {}

        recent_def_map, recent_pace_map = {}, {}
        try:
            dfs5 = nba_request(leaguedashteamstats.LeagueDashTeamStats,
                                season=season, measure_type_detailed_defense='Advanced', last_n_games=5)
            if dfs5:
                df5 = dfs5[0]
                avg_def5 = df5['DEF_RATING'].mean()
                avg_pace5 = df5['PACE'].mean() if 'PACE' in df5.columns else avg_pace
                for _, r5 in df5.iterrows():
                    ab = id2abbr.get(r5['TEAM_ID'])
                    if ab:
                        recent_def_map[ab] = r5['DEF_RATING'] / avg_def5
                        if 'PACE' in r5:
                            recent_pace_map[ab] = r5['PACE'] / avg_pace5
        except Exception as e:
            log.warning(f"Recent league data failed: {e}")

        for _, r in df.iterrows():
            abbr = id2abbr.get(r['TEAM_ID'])
            if not abbr:
                continue
            season_def = r['DEF_RATING'] / avg_def
            season_pace = r['PACE'] / avg_pace
            _lig_data[abbr] = {
                'DEF_MOD': 0.60 * recent_def_map.get(abbr, season_def) + 0.40 * season_def,
                'PACE_MOD': 0.60 * recent_pace_map.get(abbr, season_pace) + 0.40 * season_pace,
                'W_PCT': r['W_PCT'],
                'REB_MOD': (r['REB_PCT'] / avg_reb) if 'REB_PCT' in r else 1.0,
                'AVG_MARGIN': pm_map.get(r['TEAM_ID'], 0.0),
            }
        log.info(f"Loaded league data for {len(_lig_data)} teams")
        # Rakip savunma profili arka planda yükle
        threading.Thread(target=build_opp_def_profiles, args=(season,), daemon=True).start()
    except Exception as e:
        log.warning(f"League data load failed: {e}")

# ─── BACKTEST ENGINE (GERÇEK DOĞRULAMA) ───────────────────────

def fetch_box_score(game_id: str) -> pd.DataFrame:
    """NBA API'den box score çek"""
    try:
        dfs = nba_request(boxscoretraditionalv2.BoxScoreTraditionalV2, game_id=game_id)
        if dfs and len(dfs) > 0:
            return dfs[0]
    except Exception as e:
        log.debug(f"Box score fetch failed for {game_id}: {e}")
    return pd.DataFrame()

def run_backtest(date_str: str, home_id: int = None, away_id: int = None, team_id=None):
    """
    Gerçek backtest — normal predict ile aynı mantık:
    1. Seçilen maç/takım için tahmin yap (get_data normal çalışır)
    2. O günün NBA box score'unu çek
    3. Tahmin vs gerçek karşılaştır → Hit/Miss, MAE, Win Rate
    team_id=None veya 'BOTH' → tüm maçtaki iki takım
    """
    log.info(f"Backtest: {date_str} | home={home_id} away={away_id} team={team_id}")
    prog_set(5, 'Maçlar alınıyor...')

    curr_s, prev_s = seasons(date_str)
    global _curr_s, _prev_s
    _curr_s, _prev_s = curr_s, prev_s

    abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}

    # Hangi çiftler analiz edilecek
    if home_id and away_id:
        if str(team_id) == 'BOTH' or team_id is None:
            pairs = [(int(home_id), int(away_id), True), (int(away_id), int(home_id), False)]
        else:
            is_home = int(team_id) == int(home_id)
            opp_id = int(away_id) if is_home else int(home_id)
            pairs = [(int(team_id), opp_id, is_home)]
    else:
        # Tüm günün maçları
        try:
            dfs = nba_request(scoreboardv2.ScoreboardV2, game_date=date_str)
            if not dfs or dfs[0].empty:
                return {'error': 'No games found'}
            sb = dfs[0]
            pairs = []
            for _, row in sb.iterrows():
                hid, vid = int(row['HOME_TEAM_ID']), int(row['VISITOR_TEAM_ID'])
                pairs += [(hid, vid, True), (vid, hid, False)]
        except Exception as e:
            return {'error': str(e)}

    # Tahminleri normal predict_player ile üret
    prog_set(10, 'Tahminler hesaplanıyor...')
    all_preds = _run_preds(pairs, date_str)

    if not all_preds:
        return {'error': 'No predictions generated'}

    prog_set(75, 'Box score alınıyor...')

    # O günün game_id'lerini al
    game_ids = []
    try:
        dfs_sb = nba_request(scoreboardv2.ScoreboardV2, game_date=date_str)
        if dfs_sb and not dfs_sb[0].empty:
            sb_today = dfs_sb[0]
            if 'GAME_ID' in sb_today.columns:
                game_ids = sb_today['GAME_ID'].tolist()
    except:
        pass

    # Gerçek istatistikleri topla
    actual_stats = {}  # {player_name_norm: {stat: value}}
    for game_id in game_ids:
        try:
            box_df = fetch_box_score(str(game_id))
            if box_df.empty:
                continue
            for _, row in box_df.iterrows():
                p_name = str(row.get('PLAYER_NAME', ''))
                if not p_name:
                    continue
                norm = _norm_name(p_name)
                if norm not in actual_stats:
                    actual_stats[norm] = {}
                for col in ['PTS','REB','AST','STL','BLK']:
                    v = row.get(col, 0)
                    if pd.notna(v):
                        actual_stats[norm][col] = float(v)
                pts = actual_stats[norm].get('PTS', 0)
                reb = actual_stats[norm].get('REB', 0)
                ast = actual_stats[norm].get('AST', 0)
                stl = actual_stats[norm].get('STL', 0)
                blk = actual_stats[norm].get('BLK', 0)
                actual_stats[norm]['PRA'] = pts + reb + ast
                actual_stats[norm]['P+R'] = pts + reb
                actual_stats[norm]['P+A'] = pts + ast
                actual_stats[norm]['A+R'] = ast + reb
                actual_stats[norm]['S+B'] = stl + blk
        except Exception as e:
            log.debug(f"Box score processing error for {game_id}: {e}")

    prog_set(90, 'Sonuçlar hesaplanıyor...')

    # Her tahmini gerçekle karşılaştır
    hits = 0
    total_verified = 0
    abs_errors = []
    bt_preds = []

    for p in all_preds:
        norm = _norm_name(p['player'])
        actual_val = actual_stats.get(norm, {}).get(p['stat'])
        entry = {
            'player': p['player'], 'team': p['team'], 'opp': p['opp'],
            'stat': p['stat'], 'predicted': p['pred'], 'line': p['line'],
            'edge': p['edge'], 'conf': p['conf'],
            'trend': p.get('trend',''), 'trend_label': p.get('trend_label',''),
            'best_bookmaker': p.get('best_bookmaker',''),
            'market_odds': p.get('market_odds'),
            'all_lines': p.get('all_lines', {}),
            'has_market_odds': p.get('has_market_odds', False),
            'actual': None, 'hit': None, 'abs_error': None
        }
        if actual_val is not None:
            entry['actual'] = round(actual_val, 1)
            entry['abs_error'] = round(abs(actual_val - p['pred']), 1)
            entry['hit'] = 1 if actual_val > p['line'] else 0
            hits += entry['hit']
            total_verified += 1
            abs_errors.append(entry['abs_error'])
        bt_preds.append(entry)

    # DB kaydet
    try:
        with sqlite3.connect(DB) as conn:
            for entry in bt_preds:
                if entry.get('actual') is not None:
                    conn.execute("""
                        INSERT INTO backtest_results
                        (TestDate, TrainUntil, Oyuncu, Takim, Rakip, Stat,
                         Tahmin, Gercek, Barem, Hit, AbsError, Timestamp)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (date_str, date_str, entry['player'], entry['team'], entry['opp'],
                          entry['stat'], entry['predicted'], entry['actual'], entry['line'],
                          entry['hit'], entry['abs_error'],
                          datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
        threading.Thread(target=update_hit_rates, daemon=True).start()
    except Exception as e:
        log.warning(f"Backtest DB save error: {e}")

    prog_done('Backtest tamamlandı')

    win_rate = round((hits / total_verified) * 100, 1) if total_verified > 0 else 0
    avg_error = round(np.mean(abs_errors), 2) if abs_errors else 0
    roi = round((win_rate / 100 * 1.90 - 1) * 100, 1) if total_verified > 0 else 0

    return {
        'total_predictions': len(bt_preds),
        'verified': total_verified,
        'unverified': len(bt_preds) - total_verified,
        'hits': hits,
        'win_rate': win_rate,
        'avg_error': avg_error,
        'roi_sim': roi,
        'avg_edge': round(np.mean([r['edge'] for r in bt_preds]), 2) if bt_preds else 0,
        'avg_conf': round(np.mean([r['conf'] for r in bt_preds]), 1) if bt_preds else 0,
        'target_date': date_str,
        'predictions': sorted(
            [p for p in bt_preds if p.get('actual') is not None],
            key=lambda x: x.get('abs_error', 99)
        )[:200] + [p for p in bt_preds if p.get('actual') is None][:50]
    }

# ─── RUN PREDICTIONS ──────────────────────────────────────────

def _run_preds(pairs, date_str):
    abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}
    all_preds = []
    total = 0
    rosters = {}

    # Odds prefetch
    odds_data = {}
    client = get_odds_client()
    if client:
        try:
            events = client.get_events(date_str)
            for event in events[:10]:
                props = client.get_player_props(event['id'])
                odds_data.update(props)
            log.info(f"Fetched odds for {len(odds_data)} players")
        except Exception as e:
            log.error(f"Odds fetch error: {e}")

    for (tid, opp_id, is_home) in pairs:
        try:
            dfs = nba_request(commonteamroster.CommonTeamRoster, team_id=tid)
            if not dfs:
                continue
            ros = dfs[0]
            rosters[(tid, opp_id, is_home)] = ros
            total += len(ros)
            ta = abbr_map.get(tid, '???')
            if ta and ta != '???':
                with _rosters_lock:
                    _team_rosters[ta] = [str(r['PLAYER']) for _, r in ros.iterrows()]
        except:
            rosters[(tid, opp_id, is_home)] = None

    prog_set(5, f'{total} oyuncu analiz ediliyor', 0, total)
    done = 0

    for (tid, opp_id, is_home), ros in rosters.items():
        if ros is None:
            continue
        ta = abbr_map.get(tid, '???')
        oa = abbr_map.get(opp_id, '???')
        tasks = [
            (r['PLAYER_ID'], r['PLAYER'], ta, oa, is_home, date_str, r.get('POSITION', ''))
            for _, r in ros.iterrows()
        ]
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
            futs = {ex.submit(predict_player, *t, odds_data): t for t in tasks}
            for f in as_completed(futs):
                try:
                    res = f.result()
                    if res:
                        all_preds.extend(res)
                except Exception as e:
                    log.debug(f"predict_player error: {e}")
                finally:
                    done += 1
                    prog_set(5 + int(done / max(total, 1) * 90), f'{done}/{total} oyuncu', done, total)

    return all_preds

# ─── FLASK APP ────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = 'nba_predictor_v11_secret'
CORS(app, origins=["http://localhost:5050", "http://127.0.0.1:5050", "null"], supports_credentials=True)

@app.errorhandler(Exception)
def handle_exception(e):
    log.error(f"Hata: {e}", exc_info=True)
    return jsonify({'error': str(e)}), 500

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ─── CONFIG ENDPOINT ──────────────────────────────────────────

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        data = request.get_json()
        if 'odds_api_key' in data:
            RUNTIME_CONFIG['odds_api_key'] = data['odds_api_key']
            log.info("Odds API Key updated")
        if 'default_bookmakers' in data:
            RUNTIME_CONFIG['default_bookmakers'] = data['default_bookmakers']
        return jsonify({'status': 'saved', 'odds_configured': bool(RUNTIME_CONFIG['odds_api_key'])})

    key = RUNTIME_CONFIG.get('odds_api_key', '')
    return jsonify({
        'odds_configured': bool(key),
        'odds_api_key_preview': key[:4] + '****' if key else '',
        'default_bookmakers': RUNTIME_CONFIG['default_bookmakers'],
        'advanced_ml': ADVANCED_ML
    })

# ─── PROGRESS ─────────────────────────────────────────────────

@app.route('/api/progress')
def api_progress():
    with _prog_lock:
        return jsonify(dict(_prog))

# ─── ODDS ─────────────────────────────────────────────────────

@app.route('/api/odds_status')
def api_odds_status():
    key = RUNTIME_CONFIG.get('odds_api_key', '')
    return jsonify({
        'enabled': bool(key),
        'api_key_set': bool(key),
        'client_ready': bool(key)
    })

@app.route('/api/odds/<date_str>')
def api_get_odds(date_str):
    client = get_odds_client()
    if not client:
        return jsonify({'error': 'Odds API not configured'})
    try:
        events = client.get_events(date_str)
        all_props = {}
        for event in events[:5]:
            props = client.get_player_props(event['id'])
            all_props.update(props)
        return jsonify({
            'events_count': len(events),
            'players_with_props': len(all_props),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── GAMES ────────────────────────────────────────────────────

@app.route('/api/games')
def api_games():
    global _curr_s, _prev_s, _lig_data, _cache
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    new_curr, new_prev = seasons(date_str)
    if new_curr != _curr_s:
        _lig_data.clear()
        _cache.clear()
    _curr_s, _prev_s = new_curr, new_prev
    if not _lig_data:
        _load_lig(_curr_s)

    threading.Thread(target=fetch_injury_report, args=(date_str,), daemon=True).start()
    client = get_odds_client()
    if client:
        threading.Thread(target=client.get_events, args=(date_str,), daemon=True).start()

    try:
        dfs = nba_request(scoreboardv2.ScoreboardV2, game_date=date_str)
        if not dfs:
            return jsonify({'error': 'NBA API timeout'}), 503
        sb = dfs[0]
    except Exception as e:
        return jsonify({'error': f'NBA API: {str(e)}'}), 503

    if sb.empty:
        return jsonify({'games': [], 'date': date_str})

    tm = {t['id']: t['full_name'] for t in nba_teams.get_teams()}
    ab = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}
    games = []
    for i, (_, r) in enumerate(sb.iterrows()):
        hid, vid = int(r['HOME_TEAM_ID']), int(r['VISITOR_TEAM_ID'])
        games.append({
            'idx': i,
            'game_id': str(r.get('GAME_ID', '')),
            'home_id': hid, 'away_id': vid,
            'home': tm.get(hid, '?'), 'away': tm.get(vid, '?'),
            'homeAbbr': ab.get(hid, ''), 'awayAbbr': ab.get(vid, '')
        })

    return jsonify({
        'games': games, 'season': _curr_s, 'date': date_str,
        'odds_enabled': bool(RUNTIME_CONFIG.get('odds_api_key'))
    })

# ─── PREDICT ──────────────────────────────────────────────────

@app.route('/api/predict', methods=['POST'])
def api_predict():
    db_init()
    d = request.get_json(force=True)
    date_str = d.get('date', datetime.now().strftime('%Y-%m-%d'))
    home_id = d.get('home_id')
    away_id = d.get('away_id')
    team_id = d.get('team_id')

    if not all([date_str, home_id, away_id, team_id]):
        return jsonify({'error': 'Missing parameters'}), 400

    if str(team_id) == 'BOTH':
        pairs = [(int(home_id), int(away_id), True), (int(away_id), int(home_id), False)]
    else:
        is_home = int(team_id) == int(home_id)
        opp_id = int(away_id) if is_home else int(home_id)
        pairs = [(int(team_id), opp_id, is_home)]

    prog_set(2, 'Başlatılıyor...')
    all_preds = _run_preds(pairs, date_str)
    prog_set(97, 'Sıralanıyor...')

    if not all_preds:
        prog_done('Sonuç bulunamadı')
        return jsonify({'preds': [], 'summary': {}})

    all_preds.sort(
        key=lambda x: (x.get('edge', 0) * x['conf']) if x.get('has_market_odds') else x['conf'],
        reverse=True
    )
    prog_done(f'Tamamlandı: {len(all_preds)} tahmin')

    try:
        with sqlite3.connect(DB) as conn:
            for p in all_preds:
                conn.execute("""
                    INSERT INTO predictions
                    (Tarih, Oyuncu, Takim, Rakip, Stat, Tahmin, Barem, Risk, Guven,
                     Models, MarketLine, Edge, BestBookmaker, Trend)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    date_str, p['player'], p['team'], p['opp'], p['stat'],
                    p['pred'], p['line'], p['risk'], p['conf'],
                    json.dumps(p.get('models', [])),
                    p.get('line'), p.get('edge'), p.get('best_bookmaker'),
                    p.get('trend', 'NEUTRAL')
                ))
            conn.commit()
    except Exception as e:
        log.warning(f"DB insert error: {e}")

    hot_count = len([p for p in all_preds if p.get('trend') == 'HOT'])
    cold_count = len([p for p in all_preds if p.get('trend') == 'COLD'])

    return jsonify({
        'preds': all_preds,
        'summary': {
            'total': len(all_preds),
            'players': len({p['player'] for p in all_preds}),
            'avg_conf': round(np.mean([p['conf'] for p in all_preds]), 1),
            'avg_risk': round(np.mean([p['risk'] for p in all_preds]), 1),
            'ml_enabled': ADVANCED_ML,
            'odds_enabled': bool(RUNTIME_CONFIG.get('odds_api_key')),
            'with_market_odds': len([p for p in all_preds if p.get('has_market_odds')]),
            'hot_players': hot_count,
            'cold_players': cold_count,
        }
    })

# ─── SCAN ─────────────────────────────────────────────────────

@app.route('/api/scan', methods=['POST'])
def api_scan():
    db_init()
    d = request.get_json(force=True)
    date_str = d.get('date', datetime.now().strftime('%Y-%m-%d'))

    global _curr_s, _prev_s, _cache, _lig_data
    new_curr, new_prev = seasons(date_str)
    if new_curr != _curr_s:
        _lig_data.clear()
        _cache.clear()
        _load_lig(new_curr)
    _curr_s, _prev_s = new_curr, new_prev

    fetch_injury_report(date_str)

    try:
        dfs = nba_request(scoreboardv2.ScoreboardV2, game_date=date_str)
        if not dfs:
            return jsonify({'error': 'NBA API timeout'}), 503
        sb = dfs[0]
    except Exception as e:
        return jsonify({'error': str(e)}), 503

    if sb.empty:
        return jsonify({'preds': [], 'summary': {}, 'games_scanned': 0})

    abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}
    all_preds = []
    games_scanned = 0

    odds_data = {}
    client = get_odds_client()
    if client:
        try:
            events = client.get_events(date_str)
            for event in events:
                props = client.get_player_props(event['id'])
                odds_data.update(props)
        except Exception as e:
            log.error(f"Odds prefetch error: {e}")

    for _, row in sb.iterrows():
        hid = int(row['HOME_TEAM_ID'])
        vid = int(row['VISITOR_TEAM_ID'])
        games_scanned += 1

        for (tid, opp_id, is_home) in [(hid, vid, True), (vid, hid, False)]:
            ta = abbr_map.get(tid, '???')
            oa = abbr_map.get(opp_id, '???')
            try:
                dfs_ros = nba_request(commonteamroster.CommonTeamRoster, team_id=tid)
                if not dfs_ros:
                    continue
                ros = dfs_ros[0]
            except:
                continue

            if ta and ta != '???':
                with _rosters_lock:
                    _team_rosters[ta] = [str(r['PLAYER']) for _, r in ros.iterrows()]

            tasks = [
                (r['PLAYER_ID'], r['PLAYER'], ta, oa, is_home, date_str, r.get('POSITION', ''))
                for _, r in ros.iterrows()
            ]
            with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
                for f in as_completed({ex.submit(predict_player, *t, odds_data): t for t in tasks}):
                    try:
                        res = f.result()
                        if res:
                            all_preds.extend(res)
                    except:
                        pass

    if not all_preds:
        return jsonify({'preds': [], 'summary': {}, 'games_scanned': games_scanned})

    all_preds.sort(
        key=lambda x: (x.get('edge', 0) * x['conf']) if x.get('has_market_odds') else x['conf'],
        reverse=True
    )

    hot_count = len([p for p in all_preds if p.get('trend') == 'HOT'])
    cold_count = len([p for p in all_preds if p.get('trend') == 'COLD'])

    return jsonify({
        'preds': all_preds,
        'games_scanned': games_scanned,
        'summary': {
            'total': len(all_preds),
            'players': len({p['player'] for p in all_preds}),
            'avg_conf': round(np.mean([p['conf'] for p in all_preds]), 1),
            'avg_risk': round(np.mean([p['risk'] for p in all_preds]), 1),
            'ml_enabled': ADVANCED_ML,
            'odds_enabled': bool(RUNTIME_CONFIG.get('odds_api_key')),
            'with_market_odds': len([p for p in all_preds if p.get('has_market_odds')]),
            'hot_players': hot_count,
            'cold_players': cold_count,
        }
    })

# ─── BACKTEST ─────────────────────────────────────────────────

@app.route('/api/backtest', methods=['POST'])
def api_backtest():
    data = request.get_json()
    date_str = data.get('date', datetime.now().strftime('%Y-%m-%d'))
    home_id  = data.get('home_id')
    away_id  = data.get('away_id')
    team_id  = data.get('team_id')   # None → tüm gün, 'BOTH' → iki takım, int → tek takım

    global _curr_s, _prev_s, _lig_data, _cache
    new_curr, new_prev = seasons(date_str)
    if new_curr != _curr_s:
        _lig_data.clear(); _cache.clear()
        _load_lig(new_curr)
    _curr_s, _prev_s = new_curr, new_prev

    prog_set(3, 'Backtest başlatılıyor...')
    result = run_backtest(date_str, home_id, away_id, team_id)
    return jsonify(result)

@app.route('/api/backtest/history')
def api_backtest_history():
    """Geçmiş backtest sonuçları"""
    db_init()
    try:
        with sqlite3.connect(DB) as conn:
            rows = conn.execute("""
                SELECT TestDate, Stat,
                    COUNT(*) as total, SUM(Hit) as hits,
                    AVG(AbsError) as avg_err,
                    AVG(Tahmin) as avg_pred
                FROM backtest_results
                WHERE Hit IS NOT NULL
                GROUP BY TestDate, Stat
                ORDER BY TestDate DESC
                LIMIT 200
            """).fetchall()
            hit_rows = conn.execute(
                "SELECT Stat, HitRate, AvgError, Total FROM hit_rates ORDER BY HitRate DESC"
            ).fetchall()
        return jsonify({
            'results': [
                {'date': r[0], 'stat': r[1], 'total': r[2],
                 'hits': r[3], 'win_rate': round(r[3]/r[2]*100,1) if r[2] else 0,
                 'avg_error': round(r[4],2) if r[4] else 0, 'avg_pred': round(r[5],1) if r[5] else 0}
                for r in rows
            ],
            'hit_rates': [
                {'stat': r[0], 'hit_rate': r[1], 'avg_error': r[2], 'total': r[3]}
                for r in hit_rows
            ]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── OYUNCU KARŞILAŞTIRMA ─────────────────────────────────────

@app.route('/api/compare', methods=['POST'])
def api_compare():
    """İki oyuncuyu karşılaştır"""
    data = request.get_json()
    player1 = data.get('player1', '')
    player2 = data.get('player2', '')
    preds = data.get('preds', [])

    if not preds or not player1 or not player2:
        return jsonify({'error': 'Missing data'}), 400

    p1_preds = [p for p in preds if p['player'] == player1]
    p2_preds = [p for p in preds if p['player'] == player2]

    def summarize(player_preds):
        if not player_preds:
            return {}
        by_stat = {}
        for p in player_preds:
            by_stat[p['stat']] = {
                'pred': p['pred'], 'line': p['line'], 'edge': p['edge'],
                'conf': p['conf'], 'trend': p.get('trend', 'NEUTRAL'),
                'trend_label': p.get('trend_label', ''),
                'kelly': p.get('kelly', 0),
                'avg': p.get('avg', 0),
                'last10': p.get('last10', [])
            }
        return by_stat

    return jsonify({
        'player1': {'name': player1, 'stats': summarize(p1_preds)},
        'player2': {'name': player2, 'stats': summarize(p2_preds)},
        'common_stats': list(set(p['stat'] for p in p1_preds) & set(p['stat'] for p in p2_preds))
    })

# ─── CSV EXPORT ───────────────────────────────────────────────

@app.route('/api/export/csv', methods=['POST'])
def api_export_csv():
    data = request.get_json()
    preds = data.get('preds', [])
    if not preds:
        return jsonify({'error': 'No data'}), 400

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'player','team','opp','stat','pred','line','edge','edge_pct',
        'conf','risk','trend','kelly','best_bookmaker','market_odds',
        'avg','floor','ceiling','b2b','home','blowout'
    ])
    writer.writeheader()
    for p in preds:
        writer.writerow({k: p.get(k, '') for k in writer.fieldnames})

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=nba_preds_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'}
    )

# ─── RAKIP SAVUNMA PROFİLİ ────────────────────────────────────

@app.route('/api/defense/<team_abbr>')
def api_defense_profile(team_abbr):
    """Takımın rakip savunma profili"""
    with _def_profile_lock:
        profile = _opp_def_profile.get(team_abbr.upper(), {})

    if not profile:
        return jsonify({'error': 'No data', 'team': team_abbr})

    # Tüm takımların ortalamasıyla karşılaştır
    all_pts = [p.get('opp_pts', 0) for p in _opp_def_profile.values() if p.get('opp_pts', 0) > 0]
    avg_pts = round(np.mean(all_pts), 1) if all_pts else 0

    return jsonify({
        'team': team_abbr,
        'opp_pts': profile.get('opp_pts', 0),
        'opp_reb': profile.get('opp_reb', 0),
        'opp_ast': profile.get('opp_ast', 0),
        'league_avg_pts': avg_pts,
        'pts_factor': round(profile.get('opp_pts', avg_pts) / avg_pts, 3) if avg_pts else 1.0
    })

# ─── SLIPS ────────────────────────────────────────────────────

@app.route('/api/save_slip', methods=['POST'])
def api_save_slip():
    db_init()
    d = request.get_json(force=True)
    preds = d.get('preds', [])
    name = d.get('name', '')
    date_str = d.get('date', datetime.now().strftime('%Y-%m-%d'))
    if not preds:
        return jsonify({'error': 'Empty slip'}), 400
    avg_edge = round(sum(p.get('edge', 0) for p in preds) / len(preds), 2)
    avg_conf = round(sum(p.get('conf', 0) for p in preds) / len(preds), 1)
    avg_value = round(sum(p.get('edge_pct', 0) for p in preds) / len(preds), 2)
    try:
        with sqlite3.connect(DB) as conn:
            conn.execute("""
                INSERT INTO slips (Tarih, KuponAdi, Icerik, ToplamSecim, OrtEdge, OrtGuven, OrtValue, Timestamp)
                VALUES (?,?,?,?,?,?,?,?)
            """, (date_str, name, json.dumps(preds, ensure_ascii=False), len(preds),
                  avg_edge, avg_conf, avg_value, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            slip_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        return jsonify({'ok': True, 'slip_id': int(slip_id)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/slips')
def api_slips():
    db_init()
    try:
        with sqlite3.connect(DB) as conn:
            rows = conn.execute("""
                SELECT id, Tarih, KuponAdi, ToplamSecim, OrtEdge, OrtGuven, OrtValue, Timestamp
                FROM slips ORDER BY id DESC LIMIT 30
            """).fetchall()
        return jsonify({'slips': [
            {'id': r[0], 'tarih': r[1], 'ad': r[2], 'secim': r[3],
             'avg_edge': r[4], 'avg_guven': r[5], 'avg_value': r[6], 'zaman': r[7]}
            for r in rows
        ]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─── INJURIES ─────────────────────────────────────────────────

@app.route('/api/injuries')
def api_injuries():
    with _injury_lock:
        out = {k: v for k, v in _injury_cache.items() if v.lower() in ('out', 'doubtful')}
        q = {k: v for k, v in _injury_cache.items() if v.lower() in ('questionable', 'day-to-day')}
    return jsonify({'out': out, 'questionable': q, 'date': _injury_date, 'total': len(_injury_cache)})

# ─── MODEL INFO ───────────────────────────────────────────────

@app.route('/api/model_info')
def api_model_info():
    with _hit_rate_lock:
        hr = dict(_hit_rate_cache)
    return jsonify({
        'advanced_ml': ADVANCED_ML,
        'models': list(MODEL_WEIGHTS.keys()),
        'weights': MODEL_WEIGHTS,
        'features': 'Advanced (EMA, Lag, Trend, Momentum, Defense Profile)',
        'odds_api': bool(RUNTIME_CONFIG.get('odds_api_key')),
        'hit_rates': hr,
        'timestamp': datetime.now().isoformat()
    })

# ─── HTML FRONTEND ────────────────────────────────────────────

HTML_PAGE = r'''<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NBA Predictor v12.0</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#07070f;--s1:#0c0c18;--s2:#111120;--s3:#181828;--s4:#1f1f2e;
  --border:#ffffff0d;--border2:#ffffff15;--border3:#ffffff22;
  --text:#eeeeff;--muted:#5a5a78;--dim:#2e2e48;
  --green:#00e5a0;--blue:#4d9fff;--amber:#ffb647;--red:#ff5e5e;
  --purple:#a78bfa;--gold:#ffd700;--hot:#ff6b35;--cold:#60a5fa;
  --font:'Segoe UI',system-ui,sans-serif;
  --mono:'Cascadia Code','Fira Code',ui-monospace,monospace;
}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh}
.app{max-width:1440px;margin:0 auto;padding:0 20px 80px}
header{display:flex;align-items:center;justify-content:space-between;padding:22px 0 18px;border-bottom:1px solid var(--border2);margin-bottom:22px;flex-wrap:wrap;gap:10px}
.brand{display:flex;align-items:center;gap:12px}
.bdot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 12px var(--green);animation:pulse 2.5s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.3;transform:scale(.8)}}
.bname{font-size:17px;font-weight:700}.bsub{font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:.2em;margin-top:1px}
.nav-btns{display:flex;gap:6px;flex-wrap:wrap}
.nav-btn{font-family:var(--mono);font-size:10px;padding:6px 12px;background:var(--s2);border:1px solid var(--border);border-radius:4px;color:var(--muted);cursor:pointer;transition:all .15s}
.nav-btn:hover{border-color:var(--blue);color:var(--blue)}
.nav-btn.active{border-color:var(--green);color:var(--green);background:rgba(0,229,160,.05)}
.hdr-status{font-family:var(--mono);font-size:9px;color:var(--muted);text-align:right}
.layout{display:grid;grid-template-columns:1fr 310px;gap:18px;align-items:start}
@media(max-width:860px){.layout{grid-template-columns:1fr}}
.col-main{min-width:0}.col-side{position:sticky;top:14px;display:flex;flex-direction:column;gap:10px}
/* Section tabs */
.section{display:none}.section.active{display:block}
/* Date bar */
.date-bar{display:flex;gap:7px;align-items:center;margin-bottom:18px;flex-wrap:wrap}
.dqb{font-family:var(--mono);font-size:10px;padding:6px 13px;border:1px solid var(--border2);border-radius:4px;background:var(--s1);color:var(--muted);cursor:pointer;transition:all .15s}
.dqb:hover,.dqb.on{border-color:var(--green);color:var(--green);background:rgba(0,229,160,.05)}
input[type=date].di{font-family:var(--mono);font-size:11px;padding:6px 9px;border:1px solid var(--border2);border-radius:4px;background:var(--s1);color:var(--text);outline:none}
.btn{font-size:12px;font-weight:700;padding:7px 16px;border:none;border-radius:4px;cursor:pointer;transition:all .15s}
.btn-green{background:var(--green);color:#000}.btn-green:hover{background:#00ffb3}
.btn-purple{background:var(--purple);color:#000}.btn-purple:hover{background:#c4b5fd}
.btn-gold{background:var(--gold);color:#000}.btn-gold:hover{background:#ffed4e}
.btn-blue{background:var(--blue);color:#000}.btn-blue:hover{background:#6ab3ff}
.btn:disabled{background:var(--dim);color:var(--muted);cursor:not-allowed}
/* Games */
.slbl{font-family:var(--mono);font-size:9px;color:var(--muted);letter-spacing:.2em;text-transform:uppercase;margin-bottom:8px}
.games-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:7px;margin-bottom:18px}
.game-card{background:var(--s1);border:1px solid var(--border);border-radius:6px;padding:11px 13px;cursor:pointer;transition:all .15s}
.game-card:hover{border-color:var(--border2);transform:translateY(-1px)}.game-card.active{border-color:var(--green);background:rgba(0,229,160,.03)}
.game-num{font-family:var(--mono);font-size:8px;color:var(--dim);margin-bottom:5px}
.game-away{font-size:11px;color:var(--muted)}.game-vs{font-family:var(--mono);font-size:8px;color:var(--dim);margin:2px 0}.game-home{font-size:13px;font-weight:700}
/* Teams */
.team-row{display:flex;gap:7px;margin-bottom:14px;flex-wrap:wrap}
.team-btn{flex:1;min-width:100px;padding:11px;background:var(--s1);border:1px solid var(--border2);border-radius:6px;cursor:pointer;text-align:center;transition:all .15s}
.team-btn:hover{border-color:var(--blue)}.team-btn.active{border-color:var(--green);background:rgba(0,229,160,.05)}.team-btn.active .tabbr{color:var(--green)}.team-btn.both.active{border-color:var(--amber)}.team-btn.both.active .tabbr{color:var(--amber)}
.tabbr{font-size:18px;font-weight:800;display:block;margin-bottom:3px}.tname{font-family:var(--mono);font-size:8px;color:var(--muted)}
/* Progress */
.prog-wrap{background:var(--s1);border:1px solid var(--border);border-radius:8px;padding:26px;margin-bottom:18px}
.prog-title{font-size:14px;font-weight:700;margin-bottom:3px}.prog-sub{font-family:var(--mono);font-size:10px;color:var(--muted);margin-bottom:16px}
.pbar{height:2px;background:var(--s3);border-radius:1px;overflow:hidden;margin-bottom:7px}.pfill{height:100%;background:var(--green);transition:width .4s ease}
.pinfo{display:flex;justify-content:space-between}.plbl,.ppct{font-family:var(--mono);font-size:9px;color:var(--muted)}.ppct{color:var(--green)}
/* Results */
.res-header{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:12px;flex-wrap:wrap;gap:8px}
.res-title{font-size:20px;font-weight:800;letter-spacing:-.02em}.res-meta{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:2px}
.sum-row{display:grid;grid-template-columns:repeat(6,1fr);gap:7px;margin-bottom:16px}
.sum-box{background:var(--s1);border:1px solid var(--border);border-radius:6px;padding:10px 12px}
.sum-val{font-size:18px;font-weight:800;display:block;margin-bottom:1px}.sum-lbl{font-family:var(--mono);font-size:8px;color:var(--muted);letter-spacing:.12em;text-transform:uppercase}
.back-btn{font-family:var(--mono);font-size:10px;padding:6px 13px;background:transparent;border:1px solid var(--border2);border-radius:4px;color:var(--muted);cursor:pointer;transition:all .15s}.back-btn:hover{border-color:var(--red);color:var(--red)}
/* Filters */
.filter-bar{display:flex;gap:4px;margin-bottom:10px;flex-wrap:wrap}
.fg{display:flex;gap:2px;padding:2px 7px;background:var(--s1);border:1px solid var(--border);border-radius:5px;align-items:center}
.fglbl{font-family:var(--mono);font-size:8px;color:var(--dim);padding-right:5px;border-right:1px solid var(--border);margin-right:2px}
.ftab{font-family:var(--mono);font-size:9px;padding:2px 7px;border:1px solid transparent;border-radius:20px;color:var(--muted);cursor:pointer;background:transparent;transition:all .12s}
.ftab:hover{color:var(--text)}.ftab.on{background:var(--s3);color:var(--text);border-color:var(--border2)}
.sel-bar{display:flex;align-items:center;gap:10px;padding:6px 11px;background:var(--s2);border:1px solid var(--border2);border-radius:5px;margin-bottom:8px}
.sel-bar label{font-family:var(--mono);font-size:10px;color:var(--muted);cursor:pointer;display:flex;align-items:center;gap:5px}
.sel-cnt{font-family:var(--mono);font-size:10px;color:var(--amber);margin-left:auto}
/* Player blocks */
.player-block{background:var(--s1);border:1px solid var(--border);border-radius:8px;margin-bottom:8px;overflow:hidden;transition:border-color .15s}
.player-block:hover{border-color:var(--border2)}.player-block.has-sel{border-color:rgba(0,229,160,.3)}
.player-head{display:flex;align-items:center;gap:10px;padding:10px 14px;background:var(--s2);cursor:pointer;user-select:none}
.ph-av{width:30px;height:30px;border-radius:50%;background:var(--s3);border:1px solid var(--border2);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:var(--muted);flex-shrink:0}
.ph-info{flex:1;min-width:0}.ph-name{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ph-sub{font-family:var(--mono);font-size:9px;color:var(--muted);margin-top:1px}
.ph-right{display:flex;gap:5px;align-items:center;flex-shrink:0}
.ph-cnt{font-family:var(--mono);font-size:8px;color:var(--muted);background:var(--s3);padding:2px 7px;border-radius:10px}
.ph-top{font-family:var(--mono);font-size:9px;font-weight:700;padding:2px 6px;background:var(--s3);border-radius:10px}
.ph-arr{font-size:10px;color:var(--dim);transition:transform .2s;flex-shrink:0}.ph-arr.open{transform:rotate(180deg)}
/* Stat rows */
.stat-rows{padding:2px 0}
.stat-hr{display:grid;grid-template-columns:24px 60px 1fr 50px 80px 60px 68px 62px;gap:5px;padding:4px 14px;border-bottom:1px solid var(--border)}
.stat-hr span{font-family:var(--mono);font-size:8px;color:var(--dim);letter-spacing:.1em;text-transform:uppercase}
.stat-hr span:not(:first-child):not(:nth-child(2)):not(:nth-child(3)){text-align:right}
.stat-row{display:grid;grid-template-columns:24px 60px 1fr 50px 80px 60px 68px 62px;align-items:center;gap:5px;padding:7px 14px;cursor:pointer;border-left:2px solid transparent;transition:background .1s,border-color .1s}
.stat-row:hover{background:var(--s2)}.stat-row.ck{background:rgba(0,229,160,.03);border-left-color:var(--green)}
.sr-chk{width:13px;height:13px;accent-color:var(--green);cursor:pointer;flex-shrink:0}
.stag{font-family:var(--mono);font-size:9px;font-weight:600;padding:2px 6px;border-radius:3px;letter-spacing:.06em;white-space:nowrap}
.barem-wrap{display:flex;align-items:center;gap:4px}
.barem-val{font-family:var(--mono);font-size:11px;font-weight:600;min-width:34px}
.bmk-tag{font-family:var(--mono);font-size:7px;padding:1px 4px;background:var(--s3);border-radius:3px;color:var(--amber);margin-left:2px}
.diff-cell{font-family:var(--mono);font-size:10px;font-weight:700;text-align:right}
.pred-cell{font-family:var(--mono);font-size:13px;font-weight:600;text-align:right}
.range-cell{font-family:var(--mono);font-size:8px;color:var(--muted);text-align:right;line-height:1.7}
.risk-wrap{display:flex;align-items:center;gap:3px;justify-content:flex-end}
.risk-track{flex:1;height:2px;background:var(--s3);border-radius:1px;overflow:hidden}.risk-fill{height:100%;border-radius:1px}
.risk-num{font-family:var(--mono);font-size:9px;min-width:26px;text-align:right}
.conf-cell{font-family:var(--mono);font-size:9px;font-weight:600;padding:2px 6px;border-radius:10px;white-space:nowrap;text-align:right}
/* Stat colors */
.t-pts{background:rgba(77,159,255,.12);color:#4d9fff}.t-reb{background:rgba(167,139,250,.12);color:#a78bfa}.t-ast{background:rgba(255,182,71,.12);color:#ffb647}.t-stl{background:rgba(0,229,160,.10);color:#00e5a0}.t-blk{background:rgba(45,212,191,.10);color:#2dd4bf}.t-tov{background:rgba(255,94,94,.12);color:#ff5e5e}.t-pf{background:rgba(148,163,184,.10);color:#94a3b8}.t-fg3m{background:rgba(251,191,36,.12);color:#fbbf24}.t-fgm{background:rgba(129,140,248,.12);color:#818cf8}.t-ftm{background:rgba(52,211,153,.12);color:#34d399}.t-fta{background:rgba(52,211,153,.08);color:#6ee7b7}.t-fga{background:rgba(0,229,160,.08);color:#00e5a0}.t-fg3a{background:rgba(251,191,36,.08);color:#fde68a}.t-pra{background:rgba(255,94,94,.10);color:#ff5e5e}.t-pr{background:rgba(77,159,255,.08);color:#7bb8ff}.t-pa{background:rgba(255,182,71,.08);color:#ffc96b}.t-ar{background:rgba(167,139,250,.08);color:#c4b5fd}.t-sb{background:rgba(45,212,191,.08);color:#5eead4}
/* Badges */
.badge{font-family:var(--mono);font-size:8px;padding:1px 5px;border-radius:3px}
.b-b2b{background:rgba(255,94,94,.12);color:#ff5e5e}.b-hot{background:rgba(255,107,53,.15);color:#ff6b35}.b-cold{background:rgba(96,165,250,.15);color:#60a5fa}.b-blow{background:rgba(167,139,250,.10);color:#a78bfa}.b-value{background:rgba(0,229,160,.15);color:var(--green)}
/* Panels */
.panel{background:var(--s1);border:1px solid var(--border2);border-radius:9px;overflow:hidden}
.panel-head{padding:10px 13px;border-bottom:1px solid var(--border);background:var(--s2);display:flex;align-items:center;justify-content:space-between;cursor:pointer;user-select:none}
.panel-head.static{cursor:default}
.panel-title{font-size:12px;font-weight:700}.panel-arr{color:var(--muted);font-size:10px}
/* Slip */
.slip-empty{padding:24px;text-align:center;font-family:var(--mono);font-size:10px;color:var(--dim)}
.slip-list{max-height:360px;overflow-y:auto}
.slip-item{display:flex;align-items:center;gap:7px;padding:8px 11px;border-bottom:1px solid var(--border)}
.si-info{flex:1;min-width:0}.si-name{font-size:11px;font-weight:700}.si-det{font-family:var(--mono);font-size:8px;color:var(--muted);margin-top:1px}
.si-right{text-align:right;flex-shrink:0}.si-pred{font-family:var(--mono);font-size:12px;color:var(--green)}.si-conf{font-family:var(--mono);font-size:8px;color:var(--muted)}
.si-rm{background:none;border:none;color:var(--dim);cursor:pointer;font-size:13px;padding:0 2px}.si-rm:hover{color:var(--red)}
.slip-foot{padding:10px 13px;border-top:1px solid var(--border);background:var(--s2)}
.slip-stat{display:flex;justify-content:space-between;font-family:var(--mono);font-size:9px;color:var(--muted);margin-bottom:4px}.slip-stat span:last-child{color:var(--text)}
.slip-save{width:100%;margin-top:7px;font-size:12px;font-weight:700;padding:9px;background:var(--amber);color:#000;border:none;border-radius:5px;cursor:pointer}.slip-save:hover{background:#ffd080}
.slip-clear{width:100%;margin-top:4px;font-family:var(--mono);font-size:10px;padding:5px;background:transparent;border:1px solid var(--border2);border-radius:3px;color:var(--muted);cursor:pointer}.slip-clear:hover{border-color:var(--red);color:var(--red)}
/* History */
.hist-list{max-height:240px;overflow-y:auto}
.hist-item{display:flex;align-items:center;gap:7px;padding:8px 11px;border-bottom:1px solid var(--border)}
.hi-info{flex:1;min-width:0}.hi-name{font-size:11px;font-weight:600}.hi-meta{font-family:var(--mono);font-size:8px;color:var(--muted);margin-top:1px}
.hi-edge{font-family:var(--mono);font-size:10px;font-weight:600}
/* Settings panel */
.settings-form{padding:16px}
.form-row{margin-bottom:12px}
.form-label{font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px;display:block}
.form-input{width:100%;padding:8px 10px;background:var(--s3);border:1px solid var(--border2);border-radius:4px;color:var(--text);font-family:var(--mono);font-size:11px;outline:none}
.form-input:focus{border-color:var(--blue)}
.form-btn-save{width:100%;padding:10px;background:var(--green);color:#000;border:none;border-radius:4px;font-weight:700;cursor:pointer}
/* Backtest */
.bt-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
.stats-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:16px 0}
.stat-card{background:var(--s2);border:1px solid var(--border);border-radius:6px;padding:12px;text-align:center}
.stat-card-val{font-size:20px;font-weight:800;color:var(--green);margin-bottom:2px}
.stat-card-lbl{font-family:var(--mono);font-size:8px;color:var(--muted);text-transform:uppercase}
.bt-table{width:100%;border-collapse:collapse;font-size:11px;margin-top:12px}
.bt-table th{font-family:var(--mono);font-size:8px;color:var(--muted);text-align:left;padding:6px;border-bottom:1px solid var(--border)}
.bt-table td{padding:8px 6px;border-bottom:1px solid var(--border2)}
.bt-table tr:hover{background:var(--s2)}
.hit-yes{color:var(--green)}.hit-no{color:var(--red)}.hit-unknown{color:var(--dim)}
/* Compare */
.cmp-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px}
.cmp-card{background:var(--s2);border:1px solid var(--border2);border-radius:7px;padding:12px}
.cmp-name{font-size:14px;font-weight:700;margin-bottom:10px}
.cmp-row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--border);font-size:11px}
.cmp-stat{font-family:var(--mono);font-size:9px;color:var(--muted)}
.cmp-val{font-family:var(--mono);font-weight:700}
/* Modal */
.modal-bg{position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:100;display:flex;align-items:center;justify-content:center;padding:20px}
.modal-box{background:var(--s1);border:1px solid var(--border2);border-radius:10px;width:100%;max-width:520px;max-height:85vh;overflow-y:auto}
.modal-top{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--s1)}
.modal-title{font-size:14px;font-weight:700}.modal-close{background:none;border:none;color:var(--muted);cursor:pointer;font-size:17px;padding:0 3px}.modal-close:hover{color:var(--text)}
.modal-body{padding:16px}
.exp-item{display:flex;align-items:center;gap:7px;padding:7px 9px;background:var(--s2);border:1px solid var(--border);border-radius:5px;margin-bottom:4px}
.exp-num{font-family:var(--mono);font-size:9px;color:var(--dim);width:14px}.exp-player{font-size:11px;font-weight:700;flex:1;min-width:0}
.exp-right{text-align:right}.exp-over{font-family:var(--mono);font-size:11px;color:var(--amber);font-weight:700}.exp-diff{font-family:var(--mono);font-size:8px}
.modal-sum{font-family:var(--mono);font-size:10px;line-height:2;color:var(--muted);background:var(--s2);padding:9px 11px;border-radius:5px;margin:10px 0}
.copy-btn{width:100%;font-size:12px;font-weight:700;padding:9px;background:var(--s3);color:var(--text);border:1px solid var(--border2);border-radius:5px;cursor:pointer}.copy-btn:hover{border-color:var(--green);color:var(--green)}
.odds-indicator{font-family:var(--mono);font-size:7px;padding:1px 4px;border-radius:2px;background:var(--s3);color:var(--green);margin-left:4px}
.odds-missing{color:var(--dim)}
/* Odds panel under each player */
.odds-panel{border-top:1px solid var(--border2);background:var(--s2);padding:4px 0 8px}
.odds-panel-hdr{font-family:var(--mono);font-size:8px;color:var(--muted);padding:6px 14px 4px;text-transform:uppercase;letter-spacing:.1em}
.odds-row{display:flex;align-items:center;gap:4px;padding:4px 14px;flex-wrap:wrap}
.bk-pills{display:flex;gap:4px;flex-wrap:wrap}
.bk-pill{display:flex;align-items:center;background:var(--s3);border:1px solid var(--border2);border-radius:4px;overflow:hidden;font-family:var(--mono)}
.bk-name{font-size:7px;color:var(--muted);padding:2px 4px;border-right:1px solid var(--border)}
.bk-val{font-size:10px;font-weight:700;color:var(--text);padding:2px 5px}
.hidden{display:none!important}
@keyframes fup{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:translateY(0)}}
.fup{animation:fup .2s ease}
::-webkit-scrollbar{width:3px}::-webkit-scrollbar-track{background:var(--bg)}::-webkit-scrollbar-thumb{background:var(--dim);border-radius:2px}
</style>
</head>
<body>
<div class="app">
<header>
  <div class="brand">
    <div class="bdot"></div>
    <div><div class="bname">NBA Predictor</div><div class="bsub">v11.0 · ML+ODDS+BACKTEST</div></div>
  </div>
  <div class="nav-btns">
    <button class="nav-btn active" onclick="showSection('predict')" id="nav-predict">📊 Tahmin</button>
    <button class="nav-btn" onclick="showSection('backtest')" id="nav-backtest">📈 Backtest</button>
    <button class="nav-btn" onclick="showSection('compare')" id="nav-compare">⚖️ Karşılaştır</button>
    <button class="nav-btn" onclick="showSection('settings')" id="nav-settings">⚙️ Ayarlar</button>
  </div>
  <div class="hdr-status">
    <div id="ml-status">Yükleniyor...</div>
    <div id="odds-api-status" style="margin-top:2px">Odds API: kontrol ediliyor...</div>
  </div>
</header>

<div class="layout">
<div class="col-main">

  <!-- ═══ TAHMİN SEKSİYONU ═══ -->
  <div id="sec-predict" class="section active">
    <div class="date-bar">
      <button class="dqb on" onclick="setDay('today',this)">Bugün</button>
      <button class="dqb" onclick="setDay('tmrw',this)">Yarın</button>
      <input type="date" class="di" id="datepick" onchange="sDate=this.value">
      <button class="btn btn-green" id="btn-load" onclick="loadGames()">Maçları Getir</button>
      <button class="btn btn-purple" id="btn-scan" onclick="runScan()">🔍 Geceyi Tara</button>
      <button class="btn btn-gold" id="btn-odds" onclick="refreshOdds()" title="Odds API'den veri çek">🔄 Odds</button>
      <button class="btn btn-blue" id="btn-csv" onclick="exportCSV()" style="display:none">⬇️ CSV</button>
    </div>
    <div id="sec-games" class="hidden">
      <div class="slbl" id="games-lbl">Maçlar</div>
      <div class="games-grid" id="games-grid"></div>
    </div>
    <div id="sec-team" class="hidden">
      <div class="slbl">Takım Seç</div>
      <div class="team-row" id="team-row"></div>
      <div id="sec-predict-btn" class="hidden">
        <button class="btn btn-green" style="width:100%;padding:11px;font-size:13px;margin-bottom:18px" onclick="runPredict()">TAHMİN ET →</button>
      </div>
    </div>
    <div id="sec-progress" class="hidden">
      <div class="prog-wrap">
        <div class="prog-title">Analiz Ediliyor...</div>
        <div class="prog-sub" id="prog-sub"></div>
        <div class="pbar"><div class="pfill" id="pfill" style="width:0%"></div></div>
        <div class="pinfo"><span class="plbl" id="prog-lbl">Başlatılıyor...</span><span class="ppct" id="prog-pct">0%</span></div>
      </div>
    </div>
    <div id="sec-results" class="hidden">
      <div class="res-header">
        <div><div class="res-title" id="res-title">—</div><div class="res-meta" id="res-meta"></div></div>
        <button class="back-btn" onclick="resetResults()">← Geri</button>
      </div>
      <div class="sum-row" id="res-stats"></div>
      <div class="filter-bar">
        <div class="fg"><span class="fglbl">TÜM</span><button class="ftab on" onclick="filt('ALL',this)">Tümü</button></div>
        <div class="fg"><span class="fglbl">TEMEL</span>
          <button class="ftab" onclick="filt('PTS',this)">PTS</button>
          <button class="ftab" onclick="filt('REB',this)">REB</button>
          <button class="ftab" onclick="filt('AST',this)">AST</button></div>
        <div class="fg"><span class="fglbl">DEF</span>
          <button class="ftab" onclick="filt('STL',this)">STL</button>
          <button class="ftab" onclick="filt('BLK',this)">BLK</button></div>
        <div class="fg"><span class="fglbl">KOMBİ</span>
          <button class="ftab" onclick="filt('PRA',this)">PRA</button>
          <button class="ftab" onclick="filt('P+R',this)">P+R</button>
          <button class="ftab" onclick="filt('P+A',this)">P+A</button></div>
        <div class="fg"><span class="fglbl">TREND</span>
          <button class="ftab" onclick="filtTrend('HOT',this)">🔥 HOT</button>
          <button class="ftab" onclick="filtTrend('COLD',this)">❄️ COLD</button></div>
        <div class="fg"><span class="fglbl">VALUE</span>
          <button class="ftab" onclick="filtValue()">High Edge</button></div>
      </div>
      <div class="sel-bar">
        <label><input type="checkbox" id="chk-all" onchange="toggleAll(this)"> Tümünü Seç</label>
        <span class="sel-cnt" id="sel-cnt">0 seçili</span>
      </div>
      <div id="results-body"></div>
    </div>
  </div>

  <!-- ═══ BACKTEST SEKSİYONU ═══ -->
  <div id="sec-backtest" class="section">
    <!-- Backtest: Tahmin bölümüyle aynı maç/takım seçici -->
    <div class="date-bar">
      <button class="dqb on" onclick="setBtDay('today',this)">Bugün</button>
      <button class="dqb" onclick="setBtDay('yest',this)">Dün</button>
      <input type="date" class="di" id="bt-datepick" onchange="btDate=this.value">
      <button class="btn btn-green" id="btn-bt-load" onclick="loadBtGames()">Maçları Getir</button>
      <button class="btn btn-purple" id="btn-bt-all" onclick="runBtAll()">🔍 Tüm Günü Test Et</button>
    </div>
    <div id="bt-games-wrap" class="hidden">
      <div class="slbl" id="bt-games-lbl">Maçlar</div>
      <div class="games-grid" id="bt-games-grid"></div>
    </div>
    <div id="bt-team-wrap" class="hidden">
      <div class="slbl">Takım Seç</div>
      <div class="team-row" id="bt-team-row"></div>
      <div id="bt-run-wrap" class="hidden">
        <button class="btn btn-green" style="width:100%;padding:11px;font-size:13px;margin-bottom:18px" onclick="runBtGame()">BACKTEST BAŞLAT →</button>
      </div>
    </div>

    <!-- Progress -->
    <div id="bt-progress" class="hidden">
      <div class="prog-wrap">
        <div class="prog-title">Backtest Çalışıyor...</div>
        <div class="prog-sub" id="bt-prog-sub"></div>
        <div class="pbar"><div class="pfill" id="bt-pfill" style="width:0%"></div></div>
        <div class="pinfo"><span class="plbl" id="bt-prog-lbl">Başlatılıyor...</span><span class="ppct" id="bt-prog-pct">0%</span></div>
      </div>
    </div>

    <!-- Sonuçlar -->
    <div id="bt-results" class="hidden">
      <div class="stats-grid">
        <div class="stat-card"><div class="stat-card-val" id="bt-total">0</div><div class="stat-card-lbl">Tahmin</div></div>
        <div class="stat-card"><div class="stat-card-val" id="bt-verified" style="color:var(--blue)">0</div><div class="stat-card-lbl">Doğrulanan</div></div>
        <div class="stat-card"><div class="stat-card-val" id="bt-winrate" style="color:var(--amber)">-%</div><div class="stat-card-lbl">Win Rate</div></div>
        <div class="stat-card"><div class="stat-card-val" id="bt-roi" style="color:var(--green)">-%</div><div class="stat-card-lbl">Sim. ROI</div></div>
        <div class="stat-card"><div class="stat-card-val" id="bt-avgerr" style="color:var(--purple)">-</div><div class="stat-card-lbl">Ort. Hata</div></div>
        <div class="stat-card"><div class="stat-card-val" id="bt-avgconf">-</div><div class="stat-card-lbl">Ort. Güven</div></div>
        <div class="stat-card"><div class="stat-card-val" id="bt-hits" style="color:var(--green)">-</div><div class="stat-card-lbl">Hit / Miss</div></div>
        <div class="stat-card"><div class="stat-card-val" id="bt-avgedge">-</div><div class="stat-card-lbl">Ort. Edge</div></div>
      </div>
      <div class="panel">
        <div class="panel-head" onclick="togPanel('bt-table-wrap','bt-arr')">
          <span class="panel-title">Detaylı Sonuçlar (Tahmin vs Gerçek)</span>
          <span class="panel-arr" id="bt-arr">▼</span>
        </div>
        <div id="bt-table-wrap" style="overflow-x:auto">
          <table class="bt-table">
            <thead><tr>
              <th>Oyuncu</th><th>Takım</th><th>Stat</th>
              <th>Tahmin</th><th>Gerçek</th><th>Line</th>
              <th>Hata</th><th>Hit</th><th>Güven</th><th>Odds</th>
            </tr></thead>
            <tbody id="bt-tbody"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Hit rate geçmişi -->
    <div class="panel" style="margin-top:14px">
      <div class="panel-head" onclick="togPanel('hr-body','hr-arr');loadHitRates()">
        <span class="panel-title">📊 Stat Bazlı Hit Rate Geçmişi</span>
        <span class="panel-arr" id="hr-arr">▶</span>
      </div>
      <div id="hr-body" class="hidden" style="padding:14px">
        <table class="bt-table">
          <thead><tr><th>Stat</th><th>Hit Rate</th><th>Ort. Hata</th><th>Toplam</th></tr></thead>
          <tbody id="hr-tbody"><tr><td colspan="4" style="color:var(--dim);text-align:center;padding:12px">Yükleniyor...</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ═══ KARŞILAŞTIRMA SEKSİYONU ═══ -->
  <div id="sec-compare" class="section">
    <div style="margin-bottom:16px">
      <div style="font-family:var(--mono);font-size:9px;color:var(--muted);margin-bottom:8px">Önce tahmin çalıştırın, sonra karşılaştırmak istediğiniz oyuncuları seçin</div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <select id="cmp-p1" class="form-input" style="flex:1;max-width:220px">
          <option value="">Oyuncu 1...</option>
        </select>
        <select id="cmp-p2" class="form-input" style="flex:1;max-width:220px">
          <option value="">Oyuncu 2...</option>
        </select>
        <button class="btn btn-green" onclick="runCompare()">Karşılaştır</button>
      </div>
    </div>
    <div id="cmp-results" class="hidden">
      <div class="cmp-grid" id="cmp-grid"></div>
    </div>
  </div>

  <!-- ═══ AYARLAR SEKSİYONU ═══ -->
  <div id="sec-settings" class="section">
    <div class="panel" style="max-width:500px">
      <div class="panel-head static"><span class="panel-title">⚙️ API Ayarları</span></div>
      <div class="settings-form">
        <div class="form-row">
          <label class="form-label">The Odds API Key</label>
          <input type="password" class="form-input" id="settings-odds-key" placeholder="API key girin...">
          <small style="color:var(--muted);font-size:9px;display:block;margin-top:4px">
            <a href="https://the-odds-api.com" target="_blank" style="color:var(--blue)">the-odds-api.com</a>'dan ücretsiz alabilirsiniz
          </small>
        </div>
        <button class="form-btn-save" onclick="saveSettings()">💾 Kaydet</button>
        <div id="settings-status" style="margin-top:8px;font-size:10px;color:var(--green);display:none">✓ Kaydedildi!</div>

        <div style="margin-top:20px;padding-top:14px;border-top:1px solid var(--border)">
          <div class="form-label">MEVCUT DURUM</div>
          <div style="font-size:11px;line-height:2">
            <div>ML Modelleri: <span id="cfg-ml" style="color:var(--green)">-</span></div>
            <div>Odds API: <span id="cfg-odds" style="color:var(--red)">Yapılandırılmamış</span></div>
            <div>Hit Rate Verisi: <span id="cfg-hr" style="color:var(--muted)">-</span></div>
          </div>
        </div>
      </div>
    </div>
  </div>

</div><!-- col-main -->

<!-- ═══ SAĞ PANEL ═══ -->
<div class="col-side">
  <div class="panel">
    <div class="panel-head static">
      <span class="panel-title">🎫 Kupon <span id="slip-badge" style="font-family:var(--mono);font-size:9px;color:var(--amber);margin-left:5px">0 seçim</span></span>
    </div>
    <div id="slip-empty" class="slip-empty">Sol taraftan tahmin seç</div>
    <div id="slip-list" class="slip-list hidden"></div>
    <div id="slip-foot" class="slip-foot hidden">
      <div class="slip-stat"><span>Seçim</span><span id="sf-n">0</span></div>
      <div class="slip-stat"><span>Ort. Edge</span><span id="sf-edge">—</span></div>
      <div class="slip-stat"><span>Ort. Güven</span><span id="sf-conf">—</span></div>
      <button class="slip-save" onclick="saveSlip()">💾 Kuponu Kaydet</button>
      <button class="slip-clear" onclick="clearSlip()">Temizle</button>
    </div>
  </div>

  <div class="panel">
    <div class="panel-head" onclick="togPanel('hist-body','hist-arr')">
      <span class="panel-title">📂 Kayıtlı Kuponlar</span>
      <span class="panel-arr" id="hist-arr">▶</span>
    </div>
    <div class="hist-list hidden" id="hist-body"></div>
  </div>

  <div class="panel">
    <div class="panel-head" onclick="togPanel('inj-body','inj-arr')">
      <span class="panel-title">🏥 Sakatlık Raporu</span>
      <span class="panel-arr" id="inj-arr">▶</span>
    </div>
    <div class="hist-list hidden" id="inj-body">
      <div style="padding:12px;font-family:var(--mono);font-size:9px">
        <div style="color:var(--red);margin-bottom:6px">Out / Doubtful</div>
        <div id="inj-out">-</div>
        <div style="color:var(--amber);margin:10px 0 6px">Questionable</div>
        <div id="inj-quest">-</div>
      </div>
    </div>
  </div>
</div>
</div><!-- layout -->
</div><!-- app -->

<!-- MODAL -->
<div class="modal-bg hidden" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal-box">
    <div class="modal-top">
      <div class="modal-title">📋 Kupon Detayı</div>
      <button class="modal-close" onclick="closeModal()">×</button>
    </div>
    <div class="modal-body">
      <div id="modal-items"></div>
      <div class="modal-sum" id="modal-sum"></div>
      <button class="copy-btn" onclick="copySlip()">📋 Kopyala</button>
    </div>
  </div>
</div>

<script>
const API = 'http://localhost:5050/api';
let sDate='', sGame=null, sTeam=null, allP=[], curFilt='ALL', sel=new Set(), _pi=null;

const SCOL = {
  PTS:'t-pts',REB:'t-reb',AST:'t-ast',STL:'t-stl',BLK:'t-blk',TOV:'t-tov',PF:'t-pf',
  FG3M:'t-fg3m',FGM:'t-fgm',FTM:'t-ftm',FTA:'t-fta',FGA:'t-fga',FG3A:'t-fg3a',
  PRA:'t-pra','P+R':'t-pr','P+A':'t-pa','A+R':'t-ar','S+B':'t-sb'
};
const SORD = ['PTS','REB','AST','STL','BLK','TOV','PF','FGM','FGA','FG3M','FG3A','FTM','FTA','PRA','P+R','P+A','A+R','S+B'];

document.addEventListener('DOMContentLoaded', () => {
  const d = new Date(); sDate = fmt(d);
  document.getElementById('datepick').value = sDate;
  // Backtest default: dün (sonuçlar çekilebilsin)
  const yest = new Date(d); yest.setDate(yest.getDate()-1);
  btDate = fmt(yest);
  document.getElementById('bt-datepick').value = btDate;
  checkStatus();
  loadHist();
  loadInjuries();
  loadHitRates();
});

function fmt(d){ return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0'); }
function setDay(m,el){ document.querySelectorAll('.dqb').forEach(b=>b.classList.remove('on')); el.classList.add('on'); const d=new Date(); if(m==='tmrw') d.setDate(d.getDate()+1); sDate=fmt(d); document.getElementById('datepick').value=sDate; }

function showSection(sec){
  document.querySelectorAll('.section').forEach(s=>s.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('sec-'+sec).classList.add('active');
  document.getElementById('nav-'+sec).classList.add('active');
}

async function checkStatus(){
  try {
    const d = await fetch(`${API}/model_info`).then(r=>r.json());
    document.getElementById('ml-status').innerHTML = d.advanced_ml
      ? `ML: <span style="color:var(--green)">${d.models.join('+').toUpperCase()}</span>`
      : 'ML: <span style="color:var(--amber)">STANDARD</span>';
    const od = await fetch(`${API}/odds_status`).then(r=>r.json());
    document.getElementById('odds-api-status').innerHTML = od.enabled
      ? 'Odds API: <span style="color:var(--green)">CONNECTED</span>'
      : 'Odds API: <span style="color:var(--dim)">OFFLINE</span>';
    // Settings page
    document.getElementById('cfg-ml').textContent = d.advanced_ml ? d.models.join('+').toUpperCase() : 'STANDARD';
    document.getElementById('cfg-odds').textContent = od.enabled ? 'Bağlı ✓' : 'Yapılandırılmamış';
    document.getElementById('cfg-odds').style.color = od.enabled ? 'var(--green)' : 'var(--red)';
    const hrCount = Object.keys(d.hit_rates || {}).length;
    document.getElementById('cfg-hr').textContent = hrCount > 0 ? `${hrCount} stat için veri var` : 'Henüz backtest yok';
  } catch(e){ console.error('Status check failed:', e); }
}

// ─── GAMES ───
async function loadGames(){
  sDate = document.getElementById('datepick').value || fmt(new Date());
  const btn = document.getElementById('btn-load');
  btn.disabled=true; btn.textContent='Yükleniyor...';
  try {
    const data = await fetch(`${API}/games?date=${sDate}`).then(r=>r.json());
    if(data.error){ alert(data.error); return; }
    const games = data.games || [];
    if(!games.length){ alert(sDate+' tarihinde maç yok.'); return; }
    const dObj = new Date(sDate+'T12:00:00');
    document.getElementById('games-lbl').textContent =
      dObj.toLocaleDateString('tr-TR',{weekday:'long',day:'numeric',month:'long'}) +
      ' · ' + games.length + ' maç' + (data.odds_enabled ? ' · 📊Odds Aktif' : '');
    const grid = document.getElementById('games-grid');
    grid.innerHTML = '';
    games.forEach((g,i) => {
      const el = document.createElement('div');
      el.className = 'game-card';
      el.innerHTML = `<div class="game-num">${String(i+1).padStart(2,'0')}</div><div class="game-away">${g.away}</div><div class="game-vs">@</div><div class="game-home">${g.home}</div>`;
      el.onclick = () => pickGame(g, el);
      grid.appendChild(el);
    });
    show('sec-games'); hide('sec-team'); hide('sec-predict-btn'); hide('sec-results');
  } catch(e){ alert('Bağlantı hatası: '+e.message); }
  finally { btn.disabled=false; btn.textContent='Maçları Getir'; }
}

function pickGame(g, el){
  document.querySelectorAll('.game-card').forEach(c=>c.classList.remove('active'));
  el.classList.add('active'); sGame=g; sTeam=null;
  const row = document.getElementById('team-row'); row.innerHTML='';
  [{id:g.home_id,isHome:true,abbr:g.homeAbbr,name:g.home,sub:'Ev',cls:''},
   {id:g.away_id,isHome:false,abbr:g.awayAbbr,name:g.away,sub:'Dep',cls:''},
   {id:'BOTH',isHome:null,abbr:'HER',name:'İki Takım',sub:'Tümü',cls:'both'}
  ].forEach(t => {
    const btn = document.createElement('div');
    btn.className = 'team-btn'+(t.cls?' '+t.cls:'');
    const col = t.isHome===true?'var(--green)':t.isHome===false?'var(--muted)':'var(--amber)';
    btn.innerHTML = `<span class="tabbr">${t.abbr}</span><span class="tname">${t.name}<br><span style="font-size:8px;color:${col}">${t.sub}</span></span>`;
    btn.onclick = (function(id,isHome){ return function(){ pickTeam(id,isHome,btn); }; })(t.id,t.isHome);
    row.appendChild(btn);
  });
  show('sec-team'); hide('sec-predict-btn');
}

function pickTeam(id, isHome, el){
  document.querySelectorAll('.team-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active'); sTeam={id,isHome}; show('sec-predict-btn');
}

// ─── PREDICT ───
async function runPredict(){
  if(!sGame||!sTeam) return;
  startProg();
  try {
    const data = await fetch(`${API}/predict`,{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({date:sDate,home_id:sGame.home_id,away_id:sGame.away_id,team_id:sTeam.id})
    }).then(r=>r.json());
    stopProg();
    if(data.error){ alert(data.error); return; }
    showResults(data, sGame.awayAbbr+' @ '+sGame.homeAbbr);
  } catch(e){ stopProg(); alert('Hata: '+e.message); }
}

async function runScan(){
  sDate = document.getElementById('datepick').value || fmt(new Date());
  sGame=null; sTeam=null;
  if(!document.getElementById('games-grid').children.length) await loadGames();
  startProg(); hide('sec-games'); hide('sec-team');
  try {
    const data = await fetch(`${API}/scan`,{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({date:sDate})
    }).then(r=>r.json());
    stopProg();
    if(data.error){ alert(data.error); return; }
    showResults(data, '🔍 Gece Taraması — '+sDate, data.games_scanned);
  } catch(e){ stopProg(); alert('Hata: '+e.message); }
}

function startProg(){
  hide('sec-results'); show('sec-progress');
  document.getElementById('pfill').style.width='0%';
  document.getElementById('prog-pct').textContent='0%';
  document.getElementById('prog-lbl').textContent='Başlatılıyor...';
  document.getElementById('prog-sub').textContent='';
  _pi = setInterval(()=>{
    fetch(API+'/progress').then(r=>r.json()).then(d=>{
      const p = Math.min(d.pct||0,99);
      document.getElementById('pfill').style.width=p+'%';
      document.getElementById('prog-pct').textContent=p+'%';
      if(d.msg) document.getElementById('prog-lbl').textContent=d.msg;
      if(d.total>0) document.getElementById('prog-sub').textContent=d.done+' / '+d.total+' oyuncu';
    }).catch(()=>{});
  }, 500);
}

function stopProg(){
  clearInterval(_pi);
  document.getElementById('pfill').style.width='100%';
  document.getElementById('prog-pct').textContent='100%';
  setTimeout(()=>hide('sec-progress'),600);
}

// ─── SHOW RESULTS ───
function showResults(data, title, gs){
  allP = data.preds || [];
  sel.clear();
  if(!allP.length){ alert('Sonuç bulunamadı.'); return; }
  const s = data.summary || {};
  document.getElementById('res-title').textContent = title;
  document.getElementById('res-meta').textContent =
    sDate + (gs?' · '+gs+' maç':'') + ' · '+s.players+' oyuncu' +
    (s.hot_players?' · 🔥'+s.hot_players:'') + (s.cold_players?' · ❄️'+s.cold_players:'');
  const rc = s.avg_risk>=40?'var(--red)':s.avg_risk>=25?'var(--amber)':'var(--green)';
  document.getElementById('res-stats').innerHTML =
    `<div class="sum-box"><span class="sum-val" style="color:var(--blue)">${s.total}</span><span class="sum-lbl">Tahmin</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:var(--purple)">${s.players}</span><span class="sum-lbl">Oyuncu</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:var(--green)">${s.avg_conf}%</span><span class="sum-lbl">Ort. Güven</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:${rc}">${s.avg_risk}%</span><span class="sum-lbl">Ort. Risk</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:var(--hot)">${s.hot_players||0}</span><span class="sum-lbl">🔥 HOT</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:var(--cold)">${s.cold_players||0}</span><span class="sum-lbl">❄️ COLD</span></div>`;

  // Compare dropdowns güncelle
  const players = [...new Set(allP.map(p=>p.player))].sort();
  ['cmp-p1','cmp-p2'].forEach(id=>{
    const sel2 = document.getElementById(id);
    sel2.innerHTML = '<option value="">Oyuncu seç...</option>';
    players.forEach(p=>{ const opt=document.createElement('option'); opt.value=opt.textContent=p; sel2.appendChild(opt); });
  });

  show('sec-results');
  document.getElementById('btn-csv').style.display='';
  render('ALL');
  updateSlip();
}

// ─── RENDER ───
function render(filter){
  curFilt = filter;
  const body = document.getElementById('results-body');
  body.innerHTML = '';
  let fp = allP;
  if(filter==='HOT') fp=allP.filter(p=>p.trend==='HOT'||p.trend==='WARM');
  else if(filter==='COLD') fp=allP.filter(p=>p.trend==='COLD'||p.trend==='COOLING');
  else if(filter==='VALUE') fp=allP.filter(p=>p.edge>2&&p.conf>80).sort((a,b)=>b.edge*b.conf-a.edge*a.conf);
  else if(filter!=='ALL') fp=allP.filter(p=>p.stat===filter);

  const pm={};
  fp.forEach(p=>{
    p._i=allP.indexOf(p);
    if(!pm[p.player]) pm[p.player]={info:p,stats:[]};
    pm[p.player].stats.push(p);
  });

  const players = Object.values(pm).sort((a,b)=>
    Math.max(...b.stats.map(s=>s.edge||0))-Math.max(...a.stats.map(s=>s.edge||0))
  );

  players.forEach(({info,stats})=>{
    const hasS = stats.some(s=>sel.has(s._i));
    const key = info.player.replace(/[\s.']/g,'_');
    const av = (info.player.split(' ')[0]?.[0]||'')+(info.player.split(' ')[1]?.[0]||'');
    const b2b = info.b2b?'<span class="badge b-b2b">B2B</span>':'';
    const blw = info.blowout?`<span class="badge b-blow">${info.underdog?'🐶':'🏆'}</span>`:'';
    const trendBadge = info.trend==='HOT'?'<span class="badge b-hot">🔥 HOT</span>':
                       info.trend==='COLD'?'<span class="badge b-cold">❄️ COLD</span>':'';
    const odTag = info.has_market_odds
      ?'<span class="odds-indicator">LIVE</span>'
      :'<span class="odds-indicator odds-missing">SIM</span>';
    const maxEdge = Math.max(...stats.map(s=>s.edge||0));
    const edgeClass = maxEdge>2?'value-high':maxEdge>1?'value-med':'value-low';

    // ── Odds panel: bu oyuncunun gerçek market verisi olan statları ──
    const liveStats = stats.filter(s=>s.has_market_odds && s.all_lines && Object.keys(s.all_lines).length>0);
    let oddsHtml = '';
    if(liveStats.length>0){
      const rows = liveStats.map(s=>{
        const pills = Object.entries(s.all_lines)
          .map(([bk,ln])=>`<span class="bk-pill"><span class="bk-name">${bk.toUpperCase()}</span><span class="bk-val">${ln}</span></span>`)
          .join('');
        const dc=s.edge>0?'var(--green)':'var(--red)';
        const impliedPct = s.market_odds ? ((1/s.market_odds)*100).toFixed(0)+'%' : '';
        return `<div class="odds-row">
          <span class="stag ${SCOL[s.stat]||''}" style="font-size:8px;margin-right:6px;flex-shrink:0">${s.stat}</span>
          <div class="bk-pills">${pills}</div>
          <div style="margin-left:auto;padding-right:14px;text-align:right;flex-shrink:0">
            <span style="font-family:var(--mono);font-size:10px;color:${dc}">${s.edge>0?'+':''}${s.edge.toFixed(1)}</span>
            <span style="font-family:var(--mono);font-size:9px;color:var(--amber);margin-left:6px">${s.best_bookmaker} ${s.market_odds?s.market_odds.toFixed(2):''}</span>
            ${impliedPct?`<span style="font-family:var(--mono);font-size:8px;color:var(--muted);margin-left:4px">(imp. ${impliedPct})</span>`:''}
          </div>
        </div>`;
      }).join('');
      oddsHtml = `<div class="odds-panel">
        <div class="odds-panel-hdr">📊 Market Lines — ${liveStats.length} prop</div>
        ${rows}
      </div>`;
    }

    const block = document.createElement('div');
    block.className = 'player-block fup'+(hasS?' has-sel':'');
    block.id = 'pb_'+key;
    block.innerHTML =
      `<div class="player-head" onclick="togBlock('${key}',this)">
        <div class="ph-av">${av}</div>
        <div class="ph-info">
          <div class="ph-name">${info.player}${odTag}</div>
          <div class="ph-sub">${info.team} vs ${info.opp} · ${info.position||'-'}</div>
        </div>
        <div class="ph-right">${b2b}${blw}${trendBadge}<span class="ph-cnt">${stats.length} stat</span><span class="ph-top ${edgeClass}">+${maxEdge.toFixed(1)}</span></div>
        <span class="ph-arr open" id="arr_${key}">▾</span>
      </div>
      <div class="stat-rows" id="sr_${key}">
        <div class="stat-hr"><span></span><span>STAT</span><span>LINE</span><span style="text-align:right">EDGE</span><span style="text-align:right">TAHMİN</span><span style="text-align:right">RANGE</span><span style="text-align:right">RİSK</span><span style="text-align:right">GÜVEN</span></div>
        <div id="srl_${key}"></div>
        ${oddsHtml}
      </div>`;
    body.appendChild(block);

    const list = document.getElementById('srl_'+key);
    stats.sort((a,b)=>SORD.indexOf(a.stat)-SORD.indexOf(b.stat));
    stats.forEach(p=>{
      const sc=SCOL[p.stat]||'';
      const diff=p.edge;
      const dc=diff>0?'var(--green)':diff<0?'var(--red)':'var(--muted)';
      const ds=(diff>0?'+':'')+diff.toFixed(1);
      const rc=p.risk>=40?'var(--red)':p.risk>=25?'var(--amber)':'var(--green)';
      const cc=p.conf>=90?'var(--green)':p.conf>=85?'var(--blue)':'var(--amber)';
      const cb=p.conf>=90?'rgba(0,229,160,.1)':p.conf>=85?'rgba(77,159,255,.1)':'rgba(255,182,71,.08)';
      // Bookmaker + odds — gerçek veri varsa renkli göster
      const bmk=p.has_market_odds&&p.best_bookmaker
        ?`<span class="bmk-tag" style="color:var(--green)">${p.best_bookmaker} ${p.market_odds?p.market_odds.toFixed(2):''}</span>`
        :`<span class="bmk-tag">SIM</span>`;
      const tl=p.trend_label?`<span style="font-size:10px;margin-left:2px">${p.trend_label}</span>`:'';
      const ck=sel.has(p._i);
      const row=document.createElement('div');
      row.className='stat-row'+(ck?' ck':'');
      row.dataset.i=p._i;
      row.onclick=()=>togSel(p._i);
      row.innerHTML=`<input class="sr-chk" type="checkbox"${ck?' checked':''} onclick="event.stopPropagation();togSel(${p._i})">
        <span class="stag ${sc}">${p.stat}</span>
        <div class="barem-wrap">${p.line.toFixed(1)}${bmk}${tl}</div>
        <div class="diff-cell" style="color:${dc}">${ds}</div>
        <div class="pred-cell" style="color:${cc}">${p.pred.toFixed(1)}</div>
        <div class="range-cell">${p.floor.toFixed(1)}–${p.ceiling.toFixed(1)}</div>
        <div class="risk-wrap"><div class="risk-track"><div class="risk-fill" style="width:${p.risk}%;background:${rc}"></div></div><span class="risk-num" style="color:${rc}">${p.risk}%</span></div>
        <span class="conf-cell" style="color:${cc};background:${cb}">%${p.conf}</span>`;
      list.appendChild(row);
    });
  });
  syncChk();
}

function filtTrend(trend,el){ document.querySelectorAll('.ftab').forEach(b=>b.classList.remove('on')); el.classList.add('on'); render(trend); }
function filtValue(){ document.querySelectorAll('.ftab').forEach(b=>b.classList.remove('on')); render('VALUE'); }
function filt(s,el){ document.querySelectorAll('.ftab').forEach(b=>b.classList.remove('on')); el.classList.add('on'); render(s); }
function togBlock(key,h){ const b=document.getElementById('sr_'+key); const a=document.getElementById('arr_'+key); if(!b)return; const op=!b.classList.contains('hidden'); b.classList.toggle('hidden',op); if(a)a.classList.toggle('open',!op); }

// ─── SELECTION ───
function togSel(i){
  if(sel.has(i)) sel.delete(i); else sel.add(i);
  document.querySelectorAll(`.stat-row[data-i="${i}"]`).forEach(c=>{
    c.classList.toggle('ck',sel.has(i));
    const ch=c.querySelector('.sr-chk'); if(ch) ch.checked=sel.has(i);
  });
  updateSlip(); syncChk();
}
function toggleAll(m){
  const vis=getVis();
  if(m.checked) vis.forEach(i=>sel.add(i)); else vis.forEach(i=>sel.delete(i));
  document.querySelectorAll('.stat-row').forEach(c=>{
    const i=parseInt(c.dataset.i); c.classList.toggle('ck',sel.has(i));
    const ch=c.querySelector('.sr-chk'); if(ch) ch.checked=sel.has(i);
  });
  updateSlip(); syncChk();
}
function getVis(){ return Array.from(document.querySelectorAll('.stat-row')).map(r=>parseInt(r.dataset.i)).filter(i=>!isNaN(i)); }
function syncChk(){
  const vis=getVis();
  const m=document.getElementById('chk-all'); if(m) m.checked=vis.length>0&&vis.every(i=>sel.has(i));
  const c=document.getElementById('sel-cnt'); if(c) c.textContent=sel.size+' seçili';
}

// ─── SLIP ───
function updateSlip(){
  const items=Array.from(sel).map(i=>allP[i]).filter(x=>x);
  const badge=document.getElementById('slip-badge'); if(badge) badge.textContent=items.length+' seçim';
  const emp=document.getElementById('slip-empty'),lst=document.getElementById('slip-list'),foot=document.getElementById('slip-foot');
  if(!items.length){ emp.classList.remove('hidden'); lst.classList.add('hidden'); foot.classList.add('hidden'); return; }
  emp.classList.add('hidden'); lst.classList.remove('hidden'); foot.classList.remove('hidden');
  lst.innerHTML='';
  items.forEach(p=>{
    const dc=p.edge>0?'var(--green)':p.edge<0?'var(--red)':'var(--muted)';
    const ds=(p.edge>0?'+':'')+p.edge.toFixed(1);
    const sc=SCOL[p.stat]||'';
    const tl=p.trend_label?` ${p.trend_label}`:'';
    const oddsInfo=p.has_market_odds?`<span style="color:var(--amber);font-size:8px">${p.best_bookmaker} ${p.market_odds?p.market_odds.toFixed(2):''}</span> `:'';
    const el=document.createElement('div'); el.className='slip-item';
    el.innerHTML=`<div class="si-info"><div class="si-name">${p.player}${tl}</div><div class="si-det"><span class="stag ${sc}" style="padding:1px 4px;font-size:8px">${p.stat}</span> Over <b>${p.line.toFixed(1)}</b> ${oddsInfo}<span style="color:${dc}">${ds}</span></div></div><div class="si-right"><div class="si-pred">${p.pred.toFixed(1)}</div><div class="si-conf">%${p.conf}</div></div><button class="si-rm" onclick="rmSel(${allP.indexOf(p)})">×</button>`;
    lst.appendChild(el);
  });
  const ae=items.reduce((s,p)=>s+(p.edge||0),0)/items.length;
  const ac=items.reduce((s,p)=>s+p.conf,0)/items.length;
  document.getElementById('sf-n').textContent=items.length;
  document.getElementById('sf-edge').textContent=(ae>0?'+':'')+ae.toFixed(1);
  document.getElementById('sf-edge').style.color=ae>0?'var(--green)':'var(--red)';
  document.getElementById('sf-conf').textContent='%'+ac.toFixed(1);
}
function rmSel(i){ sel.delete(i); document.querySelectorAll(`.stat-row[data-i="${i}"]`).forEach(c=>{ c.classList.remove('ck'); const ch=c.querySelector('.sr-chk'); if(ch) ch.checked=false; }); updateSlip(); syncChk(); }
function clearSlip(){ sel.clear(); document.querySelectorAll('.stat-row').forEach(c=>{ c.classList.remove('ck'); const ch=c.querySelector('.sr-chk'); if(ch) ch.checked=false; }); updateSlip(); syncChk(); }

async function saveSlip(){
  const items=Array.from(sel).map(i=>allP[i]).filter(x=>x); if(!items.length) return;
  const defN=(sGame?sGame.awayAbbr+'@'+sGame.homeAbbr:'Tarama')+' — '+sDate;
  const name=prompt('Kupon adı:',defN); if(name===null) return;
  const btn=document.querySelector('.slip-save'); btn.disabled=true; btn.textContent='⏳ Kaydediliyor...';
  try {
    const data=await fetch(`${API}/save_slip`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preds:items,name:name||defN,date:sDate})}).then(r=>r.json());
    if(data.error){ alert('Hata: '+data.error); return; }
    btn.textContent='✓ Kaydedildi!'; btn.style.background='var(--green)';
    setTimeout(()=>{ btn.disabled=false; btn.textContent='💾 Kuponu Kaydet'; btn.style.background=''; },2500);
    loadHist(); showModal(items,name||defN,data.slip_id);
  } catch(e){ alert('Hata: '+e.message); btn.disabled=false; btn.textContent='💾 Kuponu Kaydet'; }
}

async function loadHitRates(){
  try {
    const data=await fetch(`${API}/backtest/history`).then(r=>r.json());
    const tbody=document.getElementById('hr-tbody'); if(!tbody) return;
    const hr=data.hit_rates||[];
    if(!hr.length){ tbody.innerHTML='<tr><td colspan="4" style="color:var(--dim);text-align:center;padding:12px">Henüz backtest verisi yok</td></tr>'; return; }
    tbody.innerHTML=hr.map(r=>{
      const c=r.hit_rate>=0.6?'var(--green)':r.hit_rate>=0.5?'var(--amber)':'var(--red)';
      return `<tr><td>${r.stat}</td><td style="color:${c};font-weight:700">${(r.hit_rate*100).toFixed(1)}%</td><td>${r.avg_error}</td><td>${r.total}</td></tr>`;
    }).join('');
  } catch(e){ console.error('loadHitRates error',e); }
}

// ─── COMPARE ───
async function runCompare(){
  const p1=document.getElementById('cmp-p1').value;
  const p2=document.getElementById('cmp-p2').value;
  if(!p1||!p2||p1===p2){ alert('İki farklı oyuncu seçin'); return; }
  try {
    const data=await fetch(`${API}/compare`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player1:p1,player2:p2,preds:allP})}).then(r=>r.json());
    if(data.error){ alert(data.error); return; }
    const grid=document.getElementById('cmp-grid'); grid.innerHTML='';
    [data.player1,data.player2].forEach(pd=>{
      const card=document.createElement('div'); card.className='cmp-card';
      const stats=pd.stats||{};
      const statRows=Object.entries(stats).sort((a,b)=>SORD.indexOf(a[0])-SORD.indexOf(b[0])).map(([stat,s])=>{
        const dc=s.edge>0?'var(--green)':s.edge<0?'var(--red)':'var(--muted)';
        const tl=s.trend_label||'';
        return `<div class="cmp-row"><span class="stag ${SCOL[stat]||''}" style="font-size:8px">${stat}</span><div><span class="cmp-val">${s.pred.toFixed(1)}</span><span style="font-family:var(--mono);font-size:8px;color:${dc};margin-left:4px">${s.edge>0?'+':''}${s.edge.toFixed(1)}</span><span style="margin-left:4px">${tl}</span></div><span style="font-family:var(--mono);font-size:9px;color:var(--muted)">%${s.conf}</span></div>`;
      }).join('');
      card.innerHTML=`<div class="cmp-name">${pd.name}</div>${statRows}`;
      grid.appendChild(card);
    });
    document.getElementById('cmp-results').classList.remove('hidden');
  } catch(e){ alert('Hata: '+e.message); }
}

// ─── CSV EXPORT ───
async function exportCSV(){
  if(!allP.length){ alert('Önce tahmin çalıştırın'); return; }
  const btn=document.getElementById('btn-csv'); btn.disabled=true; btn.textContent='⏳';
  try {
    const resp=await fetch(`${API}/export/csv`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preds:allP})});
    const blob=await resp.blob();
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a'); a.href=url; a.download=`nba_preds_${sDate}.csv`; a.click();
    URL.revokeObjectURL(url);
  } catch(e){ alert('Export hatası: '+e.message); }
  finally { btn.disabled=false; btn.textContent='⬇️ CSV'; }
}

// ─── ODDS ───
async function refreshOdds(){
  const btn=document.getElementById('btn-odds'); btn.disabled=true; btn.textContent='⏳';
  try {
    const data=await fetch(`${API}/odds/${sDate}`).then(r=>r.json());
    if(data.error) alert('Odds hatası: '+data.error);
    else alert(`${data.players_with_props} oyuncu için odds güncellendi!`);
  } catch(e){ alert('Hata: '+e.message); }
  finally { btn.disabled=false; btn.textContent='🔄 Odds'; }
}

// ─── SETTINGS ───
async function saveSettings(){
  const key=document.getElementById('settings-odds-key').value;
  if(!key){ alert('API Key girin'); return; }
  const r=await fetch(`${API}/config`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({odds_api_key:key})}).then(r=>r.json());
  if(r.status==='saved'){
    const s=document.getElementById('settings-status'); s.style.display='block';
    setTimeout(()=>s.style.display='none',2500);
    checkStatus();
  }
}

// ─── HISTORY & INJURIES ───
async function loadHist(){
  try {
    const data=await fetch(`${API}/slips`).then(r=>r.json());
    const el=document.getElementById('hist-body'); if(!el) return;
    const slips=data.slips||[];
    if(!slips.length){ el.innerHTML='<div style="padding:12px;font-family:var(--mono);font-size:9px;color:var(--dim)">Henüz kupon yok</div>'; return; }
    el.innerHTML=slips.map(s=>{
      const c=s.avg_edge>=0?'var(--green)':'var(--red)';
      return `<div class="hist-item"><div class="hi-info"><div class="hi-name">${s.ad||'—'}</div><div class="hi-meta">${s.tarih} · ${s.secim} seçim</div></div><div class="hi-edge" style="color:${c}">${s.avg_edge>=0?'+':''}${s.avg_edge?.toFixed(1)}</div></div>`;
    }).join('');
  } catch(e){ console.error('loadHist error',e); }
}

async function loadInjuries(){
  try {
    const data=await fetch(`${API}/injuries`).then(r=>r.json());
    const outEl=document.getElementById('inj-out'), questEl=document.getElementById('inj-quest');
    const out=data.out||{}, q=data.questionable||{};
    outEl.innerHTML=Object.keys(out).length?Object.entries(out).slice(0,5).map(([n,s])=>`<div>${n}: <span style="color:var(--red)">${s}</span></div>`).join('')+(Object.keys(out).length>5?`<div style="color:var(--dim)">+${Object.keys(out).length-5} daha</div>`:''):'<span style="color:var(--dim)">Yok</span>';
    questEl.innerHTML=Object.keys(q).length?Object.entries(q).slice(0,3).map(([n,s])=>`<div>${n}: <span style="color:var(--amber)">${s}</span></div>`).join(''):'<span style="color:var(--dim)">Yok</span>';
  } catch(e){ console.error('loadInjuries error',e); }
}

// ─── MODAL ───
function showModal(items,name,sid){
  let html='';
  items.forEach((p,i)=>{
    const dc=p.edge>0?'var(--green)':p.edge<0?'var(--red)':'var(--muted)';
    const sc=SCOL[p.stat]||'';
    html+=`<div class="exp-item"><span class="exp-num">${i+1}</span><div style="flex:1;min-width:0"><div class="exp-player">${p.player}</div><div style="font-family:var(--mono);font-size:8px;color:var(--muted)">${p.team} vs ${p.opp}</div></div><span class="stag ${sc}" style="padding:1px 5px;font-size:8px">${p.stat}</span><div class="exp-right"><div class="exp-over">OVER ${p.line.toFixed(1)}</div><div class="exp-diff" style="color:${dc}">${p.edge>0?'+':''}${p.edge.toFixed(1)}</div></div></div>`;
  });
  document.getElementById('modal-items').innerHTML=html;
  const ae=items.reduce((s,p)=>s+(p.edge||0),0)/items.length;
  const ac=items.reduce((s,p)=>s+p.conf,0)/items.length;
  document.getElementById('modal-sum').innerHTML=
    `<span style="color:var(--text)">Kupon:</span> ${name}<br><span style="color:var(--text)">Seçim:</span> ${items.length}<br><span style="color:var(--text)">Ort. Edge:</span> <span style="color:${ae>0?'var(--green)':'var(--red)'}">${ae>0?'+':''}${ae.toFixed(1)}</span><br><span style="color:var(--text)">Ort. Güven:</span> %${ac.toFixed(1)}<br><span style="color:var(--green)">✓ Kaydedildi (ID:${sid})</span>`;
  document.getElementById('modal').classList.remove('hidden');
}

function closeModal(){ document.getElementById('modal').classList.add('hidden'); }

function copySlip(){
  const items=Array.from(sel).map(i=>allP[i]).filter(x=>x);
  const txt=items.map((p,i)=>`${i+1}. ${p.player} | ${p.stat} OVER ${p.line.toFixed(1)} | Edge:${p.edge>0?'+':''}${p.edge.toFixed(1)} | Tahmin:${p.pred.toFixed(1)}${p.trend_label?' '+p.trend_label:''}`).join('\n');
  navigator.clipboard.writeText(`NBA Predictor v11 — ${sDate}\n${'─'.repeat(44)}\n${txt}`).then(()=>{
    const b=document.querySelector('.copy-btn'); b.textContent='✓ Kopyalandı!'; setTimeout(()=>b.textContent='📋 Kopyala',2000);
  });
}

// ─── UTILS ───
function togPanel(bId,aId){ const b=document.getElementById(bId),a=document.getElementById(aId); const op=!b.classList.contains('hidden'); b.classList.toggle('hidden',op); if(a) a.textContent=op?'▶':'▼'; }
function show(id){ const e=document.getElementById(id); if(e){ e.classList.remove('hidden'); e.classList.add('fup'); } }
function hide(id){ const e=document.getElementById(id); if(e) e.classList.add('hidden'); }
function resetResults(){ hide('sec-results'); hide('sec-team'); hide('sec-predict-btn'); hide('sec-progress'); document.querySelectorAll('.game-card').forEach(c=>c.classList.remove('active')); sGame=null; sTeam=null; allP=[]; sel.clear(); document.getElementById('btn-csv').style.display='none'; document.getElementById('pfill').style.width='0%'; const grid=document.getElementById('games-grid'); if(grid&&grid.children.length>0) show('sec-games'); updateSlip(); }

// ─── BACKTEST GAME/TEAM PICKER ───
let btDate='', btGame=null, btTeam=null, _btPi=null;

function setBtDay(m,el){
  document.querySelectorAll('#sec-backtest .dqb').forEach(b=>b.classList.remove('on')); el.classList.add('on');
  const d=new Date();
  if(m==='yest') d.setDate(d.getDate()-1);
  btDate=fmt(d); document.getElementById('bt-datepick').value=btDate;
}

async function loadBtGames(){
  btDate=document.getElementById('bt-datepick').value||fmt(new Date());
  const btn=document.getElementById('btn-bt-load'); btn.disabled=true; btn.textContent='Yükleniyor...';
  try{
    const data=await fetch(`${API}/games?date=${btDate}`).then(r=>r.json());
    if(data.error){alert(data.error);return;}
    const games=data.games||[];
    if(!games.length){alert(btDate+' tarihinde maç yok.');return;}
    document.getElementById('bt-games-lbl').textContent=btDate+' · '+games.length+' maç';
    const grid=document.getElementById('bt-games-grid'); grid.innerHTML='';
    games.forEach((g,i)=>{
      const el=document.createElement('div'); el.className='game-card';
      el.innerHTML=`<div class="game-num">${String(i+1).padStart(2,'0')}</div><div class="game-away">${g.away}</div><div class="game-vs">@</div><div class="game-home">${g.home}</div>`;
      el.onclick=()=>pickBtGame(g,el);
      grid.appendChild(el);
    });
    show('bt-games-wrap'); hide('bt-team-wrap'); hide('bt-run-wrap'); hide('bt-results');
  }catch(e){alert('Hata: '+e.message);}
  finally{btn.disabled=false; btn.textContent='Maçları Getir';}
}

function pickBtGame(g,el){
  document.querySelectorAll('#bt-games-grid .game-card').forEach(c=>c.classList.remove('active'));
  el.classList.add('active'); btGame=g; btTeam=null;
  const row=document.getElementById('bt-team-row'); row.innerHTML='';
  [{id:g.home_id,abbr:g.homeAbbr,name:g.home,sub:'Ev',cls:''},{id:g.away_id,abbr:g.awayAbbr,name:g.away,sub:'Dep',cls:''},{id:'BOTH',abbr:'HER',name:'İki Takım',sub:'Tümü',cls:'both'}].forEach(t=>{
    const btn=document.createElement('div'); btn.className='team-btn'+(t.cls?' '+t.cls:'');
    btn.innerHTML=`<span class="tabbr">${t.abbr}</span><span class="tname">${t.name}</span>`;
    btn.onclick=(function(id){return function(){pickBtTeam(id,btn);};})(t.id);
    row.appendChild(btn);
  });
  show('bt-team-wrap'); hide('bt-run-wrap');
}

function pickBtTeam(id,el){
  document.querySelectorAll('#bt-team-row .team-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active'); btTeam=id; show('bt-run-wrap');
}

async function runBtGame(){
  if(!btGame||!btTeam) return;
  startBtProg();
  try{
    const data=await fetch(`${API}/backtest`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({date:btDate,home_id:btGame.home_id,away_id:btGame.away_id,team_id:btTeam})
    }).then(r=>r.json());
    stopBtProg(); if(data.error){alert(data.error);return;}
    showBtResults(data);
  }catch(e){stopBtProg();alert('Hata: '+e.message);}
}

async function runBtAll(){
  btDate=document.getElementById('bt-datepick').value||fmt(new Date());
  startBtProg();
  try{
    const data=await fetch(`${API}/backtest`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({date:btDate})
    }).then(r=>r.json());
    stopBtProg(); if(data.error){alert(data.error);return;}
    showBtResults(data);
  }catch(e){stopBtProg();alert('Hata: '+e.message);}
}

function startBtProg(){
  hide('bt-results'); show('bt-progress');
  document.getElementById('bt-pfill').style.width='0%';
  _btPi=setInterval(()=>{
    fetch(API+'/progress').then(r=>r.json()).then(d=>{
      const p=Math.min(d.pct||0,99);
      document.getElementById('bt-pfill').style.width=p+'%';
      document.getElementById('bt-prog-pct').textContent=p+'%';
      if(d.msg) document.getElementById('bt-prog-lbl').textContent=d.msg;
      if(d.total>0) document.getElementById('bt-prog-sub').textContent=d.done+'/'+d.total+' oyuncu';
    }).catch(()=>{});
  },600);
}

function stopBtProg(){
  clearInterval(_btPi);
  document.getElementById('bt-pfill').style.width='100%';
  setTimeout(()=>hide('bt-progress'),500);
}

function showBtResults(data){
  document.getElementById('bt-results').classList.remove('hidden');
  document.getElementById('bt-total').textContent=data.total_predictions;
  document.getElementById('bt-verified').textContent=data.verified;
  const wrc=data.win_rate>=55?'var(--green)':data.win_rate>=50?'var(--amber)':'var(--red)';
  document.getElementById('bt-winrate').textContent=data.win_rate+'%';
  document.getElementById('bt-winrate').style.color=wrc;
  const rc=data.roi_sim>=0?'var(--green)':'var(--red)';
  document.getElementById('bt-roi').textContent=(data.roi_sim>=0?'+':'')+data.roi_sim+'%';
  document.getElementById('bt-roi').style.color=rc;
  document.getElementById('bt-avgerr').textContent=data.avg_error;
  document.getElementById('bt-avgconf').textContent=data.avg_conf+'%';
  document.getElementById('bt-hits').textContent=(data.hits||0)+'/'+(data.verified||0);
  document.getElementById('bt-avgedge').textContent=(data.avg_edge>=0?'+':'')+data.avg_edge;

  const tbody=document.getElementById('bt-tbody'); tbody.innerHTML='';
  (data.predictions||[]).forEach(p=>{
    const hitCls=p.hit===1?'hit-yes':p.hit===0?'hit-no':'hit-unknown';
    const hitTxt=p.hit===1?'✓ HIT':p.hit===0?'✗ MISS':'?';
    const tl=p.trend_label||'';
    const oddsCell=p.has_market_odds
      ?`<span style="color:var(--green);font-family:var(--mono);font-size:9px">${p.best_bookmaker} ${p.market_odds?p.market_odds.toFixed(2):''}</span>`
      :'<span style="color:var(--dim);font-size:9px">SIM</span>';
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><strong>${p.player}</strong>${tl?` <span>${tl}</span>`:''}</td><td>${p.team}</td><td>${p.stat}</td><td>${p.predicted}</td><td style="font-weight:700">${p.actual!==null?p.actual:'?'}</td><td>${p.line}</td><td>${p.abs_error!==null&&p.abs_error!==undefined?p.abs_error:'?'}</td><td class="${hitCls}" style="font-weight:700">${hitTxt}</td><td>%${p.conf}</td><td>${oddsCell}</td>`;
    tbody.appendChild(tr);
  });
  loadHitRates();
}
</script>
</body>
</html>'''

@app.route('/')
def index():
    resp = Response(HTML_PAGE, mimetype='text/html; charset=utf-8')
    resp.headers['Cache-Control'] = 'no-store'
    return resp

if __name__ == '__main__':
    db_init()
    # Hit rate'leri başlangıçta yükle
    with _hit_rate_lock:
        _hit_rate_cache.update(load_hit_rates())
    log.info(f'NBA Predictor v12.0 [{"ADVANCED ML" if ADVANCED_ML else "STANDARD"}] -> http://localhost:5050')
    app.run(host='0.0.0.0', port=5050, debug=False, threaded=True)
