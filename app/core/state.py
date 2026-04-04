import threading
from typing import Dict, List

# ─── GLOBAL STATE ─────────────────────────────────────────────
_cache: Dict = {}
_cache_lock = threading.Lock()
_lig_data: Dict = {}
_lig_lock = threading.Lock()
_curr_s: str = ''
_prev_s: str = ''
_prog = {'pct':0,'msg':'','total':0,'done':0,'active':False}
_prog_lock = threading.Lock()
_team_rosters: Dict = {}
_rosters_lock = threading.Lock()
_player_usage: Dict = {}
_usage_lock = threading.Lock()

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
_opp_def_profile: Dict = {} 
_player_def_rating: Dict[str, float] = {}
_player_def_rating_lock = threading.Lock()
_def_profile_lock = threading.Lock()

# Hit rate geçmişi (Kelly için)
_hit_rate_cache: Dict = {} 
_hit_rate_lock = threading.Lock()

# ─── SESSION MANAGEMENT ─────────────────────────────────────────
class GlobalHTTP:
    _session: requests.Session = None
    _lock = threading.Lock()

    @classmethod
    def get_session(cls) -> requests.Session:
        with cls._lock:
            if cls._session is None:
                import requests
                cls._session = requests.Session()
                cls._session.headers.update({'User-Agent': 'Mozilla/5.0'})
            return cls._session

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

def get_prog_dict():
    with _prog_lock:
        return dict(_prog)
