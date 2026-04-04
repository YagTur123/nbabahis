import sys, traceback
sys.path.insert(0, '.')

from app.core.utils import seasons
from app.data.nba_api import _load_lig, get_data, is_injured, nba_request
import app.core.state as state
from nba_api.stats.endpoints import commonteamroster, scoreboardv2
from nba_api.stats.static import teams as nba_teams
from app.ml.features import create_advanced_features
from app.ml.pipeline import ml_pipe
from app.core.config import MIN_GAMES, MIN_AVG_MIN, MIN_RECENT_MIN, MAX_INJURY_GAP, ALL_STATS
import pandas as pd, numpy as np

d = '2026-04-03'
curr, prev = seasons(d)
state._curr_s, state._prev_s = curr, prev
_load_lig(curr)

abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}
dfs = nba_request(scoreboardv2.ScoreboardV2, game_date=d)
if not dfs or dfs[0].empty:
    print('NO GAMES for', d)
    sys.exit(1)

hid = int(dfs[0]['HOME_TEAM_ID'].iloc[0])
vid = int(dfs[0]['VISITOR_TEAM_ID'].iloc[0])
team_abbr = abbr_map.get(hid, '???')
opp_abbr  = abbr_map.get(vid, '???')
print(f"Game: {team_abbr} vs {opp_abbr}")

ros_dfs = nba_request(commonteamroster.CommonTeamRoster, team_id=hid)
ros = ros_dfs[0] if ros_dfs else None
if ros is None:
    print("NO ROSTER"); sys.exit(1)

# Try first qualifying player
for _, row in ros.iterrows():
    pid = int(row['PLAYER_ID'])
    name = str(row['PLAYER'])
    pos = str(row.get('POSITION', ''))
    raw = get_data(pid)
    if raw.empty or len(raw) < MIN_GAMES:
        continue
    raw['GAME_DATE'] = pd.to_datetime(raw['GAME_DATE'])
    target = pd.to_datetime(d)
    history = raw[raw['GAME_DATE'] < target].sort_values('GAME_DATE')
    if len(history) < 6:
        continue
    if history['MIN'].mean() < MIN_AVG_MIN:
        continue
    
    print(f"\nTesting player: {name} ({len(history)} games)")
    df_feat = create_advanced_features(history.copy())
    print(f"Features shape: {df_feat.shape}")
    
    for stat in ['PTS', 'REB', 'AST']:
        if stat not in df_feat.columns:
            print(f"  {stat}: NOT IN FEATURES")
            continue
        try:
            model_data = ml_pipe.train(df_feat, stat, pid)
            if not model_data:
                print(f"  {stat}: train() returned None")
                continue
            print(f"  {stat}: train OK, models={list(model_data['models'].keys())}")
            pred_result = ml_pipe.predict(model_data, stat)
            if not pred_result:
                print(f"  {stat}: predict() returned None")
                continue
            print(f"  {stat}: pred={pred_result['pred']:.1f} conf={pred_result['confidence']}")
        except Exception as e:
            print(f"  {stat}: EXCEPTION: {e}")
            traceback.print_exc()
    break
