import time
import threading
import requests
import numpy as np
import pandas as pd
from typing import Dict
from collections import deque

from nba_api.stats.endpoints import (
    playergamelog, leaguedashteamstats, boxscoretraditionalv2, commonteamroster
)
from nba_api.stats.static import teams as nba_teams
from nba_api.stats.endpoints import scoreboardv3

from app.core.config import log
import app.core.state as state
from app.core.utils import _norm_name
from nba_api.stats.endpoints import leaguedashplayerstats

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
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
                now = time.time()
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


def _parse_game_code_tricodes(game_code: str):
    """Örn. 20250115/NYKPHI -> (NYK, PHI) = deplasman, ev sahibi (NBA gameCode biçimi)."""
    if not game_code or '/' not in game_code:
        return None, None
    tail = game_code.split('/')[-1].strip().upper().replace(' ', '')
    if len(tail) < 6:
        return None, None
    return tail[:3], tail[3:6]


def scoreboard_games_for_date(date_str: str):
    """
    Günlük NBA fikstürü — ScoreboardV3 (V2'ye göre güncel ve SofaScore / resmi takvimle daha uyumlu).
    date_str: YYYY-MM-DD (NBA Stats'ın kullandığı takvim günü, pratikte ABD Doğu odaklı).
    """
    dfs = nba_request(scoreboardv3.ScoreboardV3, game_date=date_str)
    if not dfs or len(dfs) < 3:
        return []
    game_header = dfs[1]
    line_score = dfs[2]
    if game_header is None or game_header.empty or line_score is None or line_score.empty:
        return []

    abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}
    out = []

    for _, g in game_header.iterrows():
        gid = g['gameId']
        code = str(g.get('gameCode') or '')
        sub = line_score[line_score['gameId'] == gid]
        if len(sub) < 2:
            continue

        away_tc, home_tc = _parse_game_code_tricodes(code)
        by_tri = {str(r['teamTricode']).upper(): int(r['teamId']) for _, r in sub.iterrows()}
        hid, aid = None, None
        if away_tc and home_tc:
            aid = by_tri.get(away_tc)
            hid = by_tri.get(home_tc)

        if not hid or not aid:
            r0, r1 = sub.iloc[0], sub.iloc[1]
            hid = int(r0['teamId'])
            aid = int(r1['teamId'])
            log.debug(f"scoreboard V3: gameCode eşleşmedi, satır sırası kullanıldı gid={gid} code={code}")

        def _abbr_for(tid: int) -> str:
            row = sub[sub['teamId'] == tid]
            if not row.empty:
                tr = str(row.iloc[0]['teamTricode'])
                return abbr_map.get(tid, tr)
            return abbr_map.get(tid, str(tid))

        home_abbr = _abbr_for(hid)
        away_abbr = _abbr_for(aid)

        out.append({
            'game_id': str(gid),
            'home_id': hid,
            'away_id': aid,
            'home': home_abbr,
            'homeAbbr': home_abbr,
            'away': away_abbr,
            'awayAbbr': away_abbr,
        })

    return out


def fetch_injury_report(date_str: str):
    with state._injury_lock:
        if state._injury_date == date_str and state._injury_cache:
            return
    try:
        session = state.GlobalHTTP.get_session()
        resp = session.get(state.ESPN_INJURY_URL, timeout=10)
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
        with state._injury_lock:
            state._injury_cache.clear()
            state._injury_cache.update(new_cache)
            state._injury_date = date_str
        log.info(f"Injury report: {len(new_cache)} players (v12.7)")
    except Exception as e:
        log.warning(f"Injury fetch failed: {e}")

def get_injury_status(name: str) -> str:
    with state._injury_lock:
        if not state._injury_cache:
            return ""
        return state._injury_cache.get(_norm_name(name), '').lower()

def is_injured(name: str) -> bool:
    status = get_injury_status(name)
    return any(x in status for x in ('out', 'doubt', 'susp'))

def get_data(pid: int) -> pd.DataFrame:
    with state._cache_lock:
        if pid in state._cache:
            return state._cache[pid].copy()
    combined = pd.DataFrame()
    for s in [state._prev_s, state._curr_s]:
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

    with state._cache_lock:
        if len(state._cache) > 200:
            for k in list(state._cache.keys())[:50]:
                del state._cache[k]
        state._cache[pid] = combined
    return combined.copy()

def build_opp_def_profiles(season: str):
    """Takımların pozisyon bazlı savunma profillerini oluştur"""
    log.info("Building opponent defense profiles...")
    abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}
    try:
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

        with state._def_profile_lock:
            state._opp_def_profile.clear()
            state._opp_def_profile.update(profiles)
        log.info(f"Dynamic DvP profiles built for {len(profiles)} teams (Last 15 games)")
    except Exception as e:
        log.warning(f"Defense profile build failed: {e}")

def get_opp_def_factor(opp_abbr: str, stat: str, position: str) -> float:
    """Rakip savunma faktörü döndür (1.0 = ortalama)"""
    with state._def_profile_lock:
        if not state._opp_def_profile or opp_abbr not in state._opp_def_profile:
            return 1.0

    profile = state._opp_def_profile.get(opp_abbr, {})
    stat_map = {
        'PTS': 'opp_pts', 'REB': 'opp_reb', 'AST': 'opp_ast',
        'PRA': 'opp_pts', 'P+R': 'opp_pts', 'P+A': 'opp_pts'
    }

    key = stat_map.get(stat)
    if not key or key not in profile:
        return 1.0

    all_vals = [p.get(key, 0) for p in state._opp_def_profile.values() if p.get(key, 0) > 0]
    if not all_vals:
        return 1.0

    avg = np.mean(all_vals)
    team_val = profile[key]

    if avg == 0: return 1.0
    
    base_factor = round(team_val / avg, 3) 
    # Example: base_factor = 0.90 means they allow 10% less PTS than average

    pos_str = str(position).upper()
    
    # Heuristic DvP: Certain positions are impacted heavier by certain stats
    # For Rebounds, Centers take the brunt of an elite rebounding defense
    if key == 'opp_reb':
        if 'C' in pos_str: return 1.0 + (base_factor - 1.0) * 1.4  # 40% more impact
        if 'F' in pos_str: return 1.0 + (base_factor - 1.0) * 1.1
        if 'G' in pos_str: return 1.0 + (base_factor - 1.0) * 0.7  # 30% less impact
        
    # For Assists, Point Guards face the perimeter defense
    if key == 'opp_ast':
        if 'G' in pos_str: return 1.0 + (base_factor - 1.0) * 1.35
        if 'F' in pos_str: return 1.0 + (base_factor - 1.0) * 0.8
        if 'C' in pos_str: return 1.0 + (base_factor - 1.0) * 0.6
        
    # For Points, Guards and Wings usually face perimeter defenders
    if key == 'opp_pts':
        if 'G' in pos_str: return 1.0 + (base_factor - 1.0) * 1.2
        if 'C' in pos_str: return 1.0 + (base_factor - 1.0) * 0.8
        
    return base_factor

def _load_lig(season: str):
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

        with state._lig_lock:
            state._lig_data.clear()
            for _, r in df.iterrows():
                abbr = id2abbr.get(r['TEAM_ID'])
                if abbr:
                    state._lig_data[abbr] = {
                        'W_PCT': r.get('W_PCT', 0.5),
                        'DEF_RATING': r.get('DEF_RATING', avg_def),
                        'DEF_MOD': r.get('DEF_RATING', avg_def) / max(avg_def, 1),
                        'PACE': r.get('PACE', avg_pace),
                        'PACE_MOD': r.get('PACE', avg_pace) / max(avg_pace, 1),
                        'REB_MOD': (1.0 - r.get('REB_PCT', 0.50)) / max((1.0 - avg_reb), 0.01),
                        'PLUS_MINUS': pm_map.get(r['TEAM_ID'], 0.0),
                        'AVG_MARGIN': pm_map.get(r['TEAM_ID'], 0.0),
                        'RECENT_DEF_MOD': recent_def_map.get(abbr, 1.0),
                        'RECENT_PACE_MOD': recent_pace_map.get(abbr, 1.0)
                    }
                    
        # --- PLAYER DEFENSIVE RATINGS (MATCHUP LOGIC) ---
        try:
            from nba_api.stats.endpoints import leaguedashplayerstats
            player_adv = nba_request(leaguedashplayerstats.LeagueDashPlayerStats, season=season, measure_type_detailed_defense='Advanced')
            if player_adv and not player_adv[0].empty:
                df_padv = player_adv[0]
                new_pdr = {}
                for _, pr in df_padv.iterrows():
                    pname = _norm_name(str(pr['PLAYER_NAME']))
                    new_pdr[pname] = pr.get('DEF_RATING', 113.0)
                
                with state._player_def_rating_lock:
                    state._player_def_rating.clear()
                    state._player_def_rating.update(new_pdr)
                log.info(f"Loaded Defensive Ratings for {len(new_pdr)} players.")
        except Exception as e:
            log.warning(f"Player Def Ratings failed: {e}")
            
    except Exception as e:
        log.error(f"Error loading league data: {e}")
        
        # Faz 3: Yükleme Yüzdesi (USG%) Verisinin Çekilmesi
        try:
            p_dfs = nba_request(leaguedashplayerstats.LeagueDashPlayerStats, season=season)
            if p_dfs and not p_dfs[0].empty:
                pdf = p_dfs[0]
                usage_map = {}
                for _, pr in pdf.iterrows():
                    nm = _norm_name(pr['PLAYER_NAME'])
                    # USG_PCT exists in LeagueDashPlayerStats default view
                    usage_map[nm] = pr.get('USG_PCT', 0.0) if 'USG_PCT' in pr else (pr.get('FGA', 0) / max((pr.get('MIN', 0) * 0.5), 1))
                with state._usage_lock:
                    state._player_usage.clear()
                    state._player_usage.update(usage_map)
                log.info(f"Loaded Usage% for {len(usage_map)} players")
        except Exception as e:
            log.warning(f"Player Usage load failed: {e}")

        threading.Thread(target=build_opp_def_profiles, args=(season,), daemon=True).start()
    except Exception as e:
        log.warning(f"League data load failed: {e}")

def fetch_box_score(game_id: str) -> pd.DataFrame:
    try:
        dfs = nba_request(boxscoretraditionalv2.BoxScoreTraditionalV2, game_id=game_id)
        if dfs and len(dfs) > 0:
            return dfs[0]
    except Exception as e:
        log.debug(f"Box score fetch failed for {game_id}: {e}")
    return pd.DataFrame()
