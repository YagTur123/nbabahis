import traceback
from app.services.predict_service import get_run_preds
import app.core.state as state
from app.data.nba_api import _load_lig, fetch_injury_report
from app.core.utils import seasons

d = '2026-03-25'
curr_s, prev_s = seasons(d)
state._curr_s, state._prev_s = curr_s, prev_s
_load_lig(state._curr_s)
fetch_injury_report(d)

pairs = [(1610612747, 1610612743, True)]
print("running get_run_preds...")
try:
    preds = get_run_preds(pairs, d)
    print(f"Got {len(preds)} preds")
except Exception as e:
    traceback.print_exc()
