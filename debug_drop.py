import sys
sys.path.insert(0, '.')

from app.core.utils import seasons
from app.data.nba_api import _load_lig, get_data, is_injured, get_opp_def_factor, nba_request
import app.core.state as state
from nba_api.stats.endpoints import commonteamroster, scoreboardv2
from nba_api.stats.static import teams as nba_teams
from app.ml.features import create_advanced_features
from app.ml.pipeline import detect_trend, ml_pipe
from app.core.config import MIN_GAMES, MIN_AVG_MIN, MIN_RECENT_MIN, MAX_INJURY_GAP, ALL_STATS
import pandas as pd, numpy as np

d = '2026-04-03'
curr, prev = seasons(d)
state._curr_s, state._prev_s = curr, prev
_load_lig(curr)

abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}

# get first game
dfs = nba_request(scoreboardv2.ScoreboardV2, game_date=d)
if dfs and not dfs[0].empty:
    hid = int(dfs[0]['HOME_TEAM_ID'].iloc[0])
    vid = int(dfs[0]['VISITOR_TEAM_ID'].iloc[0])
    team_abbr = abbr_map.get(hid, '???')
    opp_abbr  = abbr_map.get(vid, '???')
    print(f"Testing: {team_abbr} vs {opp_abbr}")

    ros_dfs = nba_request(commonteamroster.CommonTeamRoster, team_id=hid)
    ros = ros_dfs[0] if ros_dfs else None
    if ros is not None:
        total = 0
        for _, row in ros.iterrows():
            pid = int(row['PLAYER_ID'])
            name = str(row['PLAYER'])
            position = str(row.get('POSITION', ''))
            raw = get_data(pid)
            
            if raw.empty or len(raw) < MIN_GAMES:
                print(f"  DROP {name}: insufficient data ({len(raw)} games)")
                continue

            raw['GAME_DATE'] = pd.to_datetime(raw['GAME_DATE'])
            target = pd.to_datetime(d)
            history = raw[raw['GAME_DATE'] < target].sort_values('GAME_DATE')
            if len(history) < 1:
                print(f"  DROP {name}: no history before target date")
                continue

            status = is_injured(name)
            if status in ('out', 'doubtful'):
                print(f"  DROP {name}: injured ({status})")
                continue

            avg_min = history['MIN'].mean()
            recent_min = history['MIN'].tail(3).mean()
            if avg_min < MIN_AVG_MIN or recent_min < MIN_RECENT_MIN:
                print(f"  DROP {name}: low minutes avg={avg_min:.1f} recent={recent_min:.1f}")
                continue

            last_game_min = history['MIN'].iloc[-1]
            if last_game_min == 0:
                print(f"  DROP {name}: 0 mins last game")
                continue

            rest = (target - history['GAME_DATE'].iloc[-1]).days
            if rest > MAX_INJURY_GAP:
                print(f"  DROP {name}: rest gap {rest} days")
                continue

            df_feat = create_advanced_features(history.copy())
            if df_feat.empty:
                print(f"  DROP {name}: empty features")
                continue

            print(f"  OK {name}: {len(history)} games, pos={position}, avg_min={avg_min:.1f}")
            total += 1
            if total >= 5:
                break
        print(f"Total OK: {total}/{len(ros)}")
