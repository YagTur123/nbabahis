import math
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime

# Feature Engineering / Advanced Stats Calculation

# Latitude, Longitude, Altitude (ft)
NBA_ARENAS = {
    'ATL': (33.7573, -84.3963, 1050),
    'BOS': (42.3662, -71.0621, 15),
    'BKN': (40.6826, -73.9754, 20),
    'CHA': (35.2251, -80.8392, 761),
    'CHI': (41.8807, -87.6742, 597),
    'CLE': (41.4965, -81.6881, 653),
    'DAL': (32.7905, -96.8103, 430),
    'DEN': (39.7486, -105.0075, 5280), # High altitude!
    'DET': (42.3411, -83.0550, 600),
    'GSW': (37.7680, -122.3877, 16),
    'HOU': (29.7508, -95.3621, 50),
    'IND': (39.7640, -86.1555, 715),
    'LAC': (34.0430, -118.2673, 230),
    'LAL': (34.0430, -118.2673, 230),
    'MEM': (35.1381, -90.0506, 331),
    'MIA': (25.7814, -80.1870, 10),
    'MIL': (43.0451, -87.9172, 593),
    'MIN': (44.9795, -93.2761, 830),
    'NOP': (29.9490, -90.0821, -2),
    'NYK': (40.7505, -73.9934, 33),
    'OKC': (35.4634, -97.5151, 1200),
    'ORL': (28.5392, -81.3839, 82),
    'PHI': (39.9012, -75.1720, 12),
    'PHX': (33.4457, -112.0712, 1086),
    'POR': (45.5316, -122.6668, 50),
    'SAC': (38.5802, -121.4997, 30),
    'SAS': (29.4270, -98.4375, 650),
    'TOR': (43.6435, -79.3791, 246),
    'UTA': (40.7683, -111.9011, 4226), # High altitude!
    'WAS': (38.8981, -77.0209, 23),
}

def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 3958.8 # Radius of earth in miles
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat/2) * math.sin(dLat/2) + \
        math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
        math.sin(dLon/2) * math.sin(dLon/2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def calc_travel_fatigue(team_abbr: str, is_home: bool, opp_abbr: str, history_df: pd.DataFrame, target_date: str) -> float:
    """Returns a multiplier (default 1.0) indicating travel/altitude fatigue."""
    if history_df.empty or team_abbr not in NBA_ARENAS or opp_abbr not in NBA_ARENAS:
        return 1.0
        
    target_dt = pd.to_datetime(target_date)
    last_game = history_df.iloc[-1]
    
    # Games in last 7 days
    recent_games = history_df[history_df['GAME_DATE'] >= (target_dt - pd.Timedelta(days=7))]
    games_in_7 = len(recent_games)
    
    # Distance from last game city to current city
    was_home_last = 'vs.' in str(last_game.get('MATCHUP', ''))
    last_city = team_abbr if was_home_last else str(last_game.get('MATCHUP', '')).split(' ')[-1]
    curr_city = team_abbr if is_home else opp_abbr
    
    if last_city not in NBA_ARENAS: last_city = team_abbr
    if curr_city not in NBA_ARENAS: curr_city = opp_abbr
    
    lat1, lon1, alt1 = NBA_ARENAS[last_city]
    lat2, lon2, alt2 = NBA_ARENAS[curr_city]
    
    distance = haversine(lat1, lon1, lat2, lon2)
    
    penalty = 1.0
    
    # 1. Back-to-back checks
    rest_days = (target_dt - last_game['GAME_DATE']).days
    if rest_days <= 1:
        penalty -= 0.04 # Standard B2B
        if distance > 600: penalty -= 0.02 # Long flight B2B
        if distance > 1500: penalty -= 0.03 # Extreme flight B2B
        
    # 2. 4 games in 6 nights check
    if games_in_7 >= 4:
        penalty -= 0.03
        
    # 3. Altitude check (Denver/Utah)
    if alt2 >= 4000 and alt1 < 4000:
        penalty -= 0.03 # Altitude sickness / thin air
        if rest_days <= 1:
            penalty -= 0.02 # B2B in altitude is brutal
            
    # Max penalty cap
    return max(0.85, penalty)

def get_missing_usage_shift(team_abbr: str, is_injured_func, roster_info: List[Dict], player_usage_dict: Dict[str, float]) -> Dict[str, float]:
    """
    Sakatlıklar nedeniyle eksilen USG% (Usage Rate) miktarını pozisyon bazlı hesaplar.
    Dönen sözlükte 'G', 'F', 'C' için ayrı çarpanlar bulunur.
    """
    if not team_abbr or not roster_info or not player_usage_dict:
        return {'G': 1.0, 'F': 1.0, 'C': 1.0, 'default': 1.0}
        
    missing_usg_total = 0.0
    active_usg_per_pos = {'G': 0.0, 'F': 0.0, 'C': 0.0}
    missing_usg_per_pos = {'G': 0.0, 'F': 0.0, 'C': 0.0}
    
    for item in roster_info:
        name = item['name']
        pos = str(item.get('pos', 'G')).upper()
        main_pos = 'C' if 'C' in pos else ('F' if 'F' in pos else 'G')
        
        from app.core.utils import _norm_name
        n_name = _norm_name(name)
        usg = player_usage_dict.get(n_name, 0.0)
        
        if is_injured_func(_norm_name(name)):
            missing_usg_total += usg
            missing_usg_per_pos[main_pos] += usg
        else:
            active_usg_per_pos[main_pos] += usg
            
    # Toplam ve pozisyon bazlı çarpanları hesapla
    active_total = sum(active_usg_per_pos.values())
    if active_total == 0:
        return {'G': 1.0, 'F': 1.0, 'C': 1.0, 'default': 1.0}
        
    # Genel çarpan (fallback)
    base_shift = (missing_usg_total * 0.45) / max(active_total, 1.0)
    
    shifts = {}
    for pos in ['G', 'F', 'C']:
        # Kendi pozisyonundan biri sakatlandığında daha çok etkilenir (%60 dağılım)
        # Diğer pozisyonlardan sakatlık olduğunda daha az etkilenir (%40 dağılım)
        pos_missing = missing_usg_per_pos[pos]
        other_missing = missing_usg_total - pos_missing
        
        pos_active = active_usg_per_pos[pos]
        
        if pos_active > 0:
            # Kendi pozisyonundaki eksikliği daha çok kompanse eder
            shift = 1.0 + (pos_missing * 0.55 + other_missing * 0.25) / max(pos_active, 1.0)
        else:
            shift = 1.0 + base_shift
            
        shifts[pos] = min(1.35, shift)
        
    shifts['default'] = min(1.30, 1.0 + base_shift)
    return shifts
