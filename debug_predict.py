import traceback
from app.services.predict_service import get_run_preds, predict_player, get_data
from app.data.nba_api import _load_lig, fetch_injury_report
from app.core.utils import seasons
import app.core.state as state
from app.data.advanced_stats import calc_travel_fatigue

d = '2026-04-02'
curr_s, prev_s = seasons(d)
state._curr_s, state._prev_s = curr_s, prev_s
_load_lig(state._curr_s)

pid = 2544 # LeBron James
print("Raw count:", len(get_data(pid)))
res = predict_player(pid, "LeBron James", "LAL", "LAC", True, d, "F", {}, {})
print("Prediction for LeBron:", res)

