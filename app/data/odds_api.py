import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from app.core.config import STAT_TO_ODDS_MARKET, log
from app.core.state import _odds_lock, _odds_cache, _odds_cache_time
from app.core.utils import _norm_name
from app.data.stake_api import get_stake_client

PP_TO_MARKET = {
    'Points': 'player_points',
    'Rebounds': 'player_rebounds',
    'Assists': 'player_assists',
    'Pts+Rebs+Asts': 'player_points_rebounds_assists',
    'Pts+Rebs': 'player_points_rebounds',
    'Pts+Asts': 'player_points_assists',
    'Rebs+Asts': 'player_rebounds_assists',
    '3-PT Made': 'player_threes',
    'Blocked Shots': 'player_blocks',
    'Steals': 'player_steals',
    'Blks+Stls': 'player_blocks_steals',
    'Turnovers': 'player_turnovers',
    'Fantasy Score': 'fantasy_score'
}

class OddsAPIClient:
    def __init__(self, fallback_api_key: str = ""):
        from app.core.config import RUNTIME_CONFIG
        self.fallback_api_key = fallback_api_key or RUNTIME_CONFIG.get('odds_api_key', '')
        self.session = requests.Session()

    def get_player_props(self, event_id: str, bookmakers: List[str] = None, use_stake: bool = True) -> Dict:
        # use_stake=False: dış piyasa yok — PrizePicks, The Odds API ve Stake'e hiç dokunma
        if not use_stake:
            return {}

        cache_key = "pp_all_props"
        with _odds_lock:
            if cache_key in _odds_cache:
                 if datetime.now() - _odds_cache_time.get(cache_key, datetime.min) < timedelta(minutes=5):
                     return _odds_cache[cache_key]

        url = "https://partner-api.prizepicks.com/projections?league_id=7&per_page=1000&single_stat=true"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        result = {}
        try:
            resp = self.session.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            players = {}
            for inc in data.get('included', []):
                if inc.get('type') == 'new_player':
                    players[inc['id']] = _norm_name(inc.get('attributes', {}).get('name', ''))

            for p in data.get('data', []):
                if p.get('type') != 'projection': continue
                
                pid = p.get('relationships', {}).get('new_player', {}).get('data', {}).get('id')
                pname = players.get(pid, '')
                if not pname: continue
                
                desc = str(p.get('attributes', {}).get('description', '')).lower()
                if any(word in desc for word in ['1st', '2nd', '3rd', '4th', 'half', 'quarter', 'qtr', 'minutes', 'min']):
                    continue
                
                stat_desc = p.get('attributes', {}).get('stat_type')
                line = p.get('attributes', {}).get('line_score')
                
                market = PP_TO_MARKET.get(stat_desc)
                if not market: continue
                
                if pname not in result:
                    result[pname] = {}
                if market not in result[pname]:
                    result[pname][market] = {}
                    
                result[pname][market]['PrizePicks'] = {
                    'line': float(line),
                    'over_odds': 1.85,
                    'bookmaker': 'PrizePicks'
                }

            with _odds_lock:
                _odds_cache[cache_key] = result
                _odds_cache_time[cache_key] = datetime.now()
                
            log.info(f"PrizePicks data loaded for {len(result)} players.")
            
        except Exception as e:
            log.error(f"PrizePicks props fetch error: {e}")

        # --- THE ODDS API FALLBACK ---
        if self.fallback_api_key:
            fb_cache_key = "theodds_all_props"
            use_fb_cache = False
            with _odds_lock:
                if fb_cache_key in _odds_cache:
                    if datetime.now() - _odds_cache_time.get(fb_cache_key, datetime.min) < timedelta(hours=4):
                        use_fb_cache = True
                        fallback_data = _odds_cache[fb_cache_key]

            if not use_fb_cache:
                fallback_data = self._fetch_all_from_the_odds()
                if fallback_data:
                    with _odds_lock:
                        _odds_cache[fb_cache_key] = fallback_data
                        _odds_cache_time[fb_cache_key] = datetime.now()

            # Merge fallback data into result
            if fallback_data:
                for pname, markets in fallback_data.items():
                    if pname not in result:
                        result[pname] = {}
                    for mkt, bms in markets.items():
                        if mkt not in result[pname]:
                            result[pname][mkt] = {}
                        # Zaten PrizePicks varsa üzerine yazdırma
                        for bm_name, bm_data in bms.items():
                            if bm_name not in result[pname][mkt]:
                                result[pname][mkt][bm_name] = bm_data

        # --- STAKE API INTEGRATION ---
        if use_stake:
            with _odds_lock:
                stake_client = get_stake_client()
                stake_data = stake_client.get_player_props()
                
            if stake_data:
                for pname, markets in stake_data.items():
                    if pname not in result:
                        result[pname] = {}
                    for mkt, bm_data in markets.items():
                        if mkt not in result[pname]:
                            result[pname][mkt] = {}
                        result[pname][mkt]['Stake'] = bm_data['Stake']
                                
        return result

    def _fetch_all_from_the_odds(self) -> Dict:
        log.info("Fetching fallback odds from The Odds API...")
        # Tum eventleri cekip tum propslari alirsak tek istek limitine takilmayiz fakat The Odds Api event id ister.
        # Nba icin bugunun eventlerini al
        ev_url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/events"
        try:
            ev_resp = self.session.get(ev_url, params={'apiKey': self.fallback_api_key}, timeout=10)
            if ev_resp.status_code != 200: return {}
            events = ev_resp.json()
            
            from app.core.config import ALL_ODDS_MARKETS
            fallback_res = {}
            for ev in events[:15]: # Bugunun ve yarinin maclari
                odds_url = f"https://api.the-odds-api.com/v4/sports/basketball_nba/events/{ev['id']}/odds"
                params = {
                    'apiKey': self.fallback_api_key,
                    'regions': 'us,eu,au', # Stake genellikle au veya eu icinde cikar
                    'markets': ','.join(ALL_ODDS_MARKETS),
                    'oddsFormat': 'decimal'
                }
                or_resp = self.session.get(odds_url, params=params, timeout=10)
                if or_resp.status_code != 200: continue
                odds_data = or_resp.json()
                
                for bm in odds_data.get('bookmakers', []):
                    bm_title = bm['title']
                    for m in bm.get('markets', []):
                        m_key = m['key']
                        for out in m.get('outcomes', []):
                            pname = _norm_name(out.get('description', ''))
                            if not pname: continue
                            
                            if pname not in fallback_res: fallback_res[pname] = {}
                            if m_key not in fallback_res[pname]: fallback_res[pname][m_key] = {}
                            
                            pt = out.get('point', 0)
                            ov = out.get('price', 0)
                            name_type = out.get('name', '').lower()
                            
                            if 'over' in name_type and pt > 0:
                                if bm_title not in fallback_res[pname][m_key]:
                                    fallback_res[pname][m_key][bm_title] = {'line': pt, 'over_odds': ov, 'bookmaker': bm_title}
                                elif fallback_res[pname][m_key][bm_title]['line'] == pt:
                                    fallback_res[pname][m_key][bm_title]['over_odds'] = max(ov, fallback_res[pname][m_key][bm_title]['over_odds'])
                                    
            log.info(f"The Odds API Fallback loaded data for {len(fallback_res)} players.")
            return fallback_res
            
        except Exception as e:
            log.error(f"The Odds API Error: {e}")
            return {}

    def find_best_line(self, props: Dict, player_norm: str, stat: str) -> Optional[Dict]:
        market = STAT_TO_ODDS_MARKET.get(stat)
        if not market:
             return None
             
        market_data = dict(props.get(player_norm, {}).get(market, {})) # avoid mutating original
        
        if not market_data:
             # DFS platformlarındaki .5 buçuklu baremleri bulmak için esnetmeler
             if stat == 'TOV': market_data = props.get(player_norm, {}).get('player_turnovers', {})
             
        if not market_data:
             return None

        best_odds = 0
        best = None
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
    # PrizePicks için API Key gerekmiyor, direkt instance dönüyoruz
    return OddsAPIClient("PRIZE_PICKS_MODE")
