import traceback
from app.core.config import RUNTIME_CONFIG
from app.core.utils import seasons
from app.data.nba_api import _load_lig, fetch_injury_report
from app.services.predict_service import predict_player
from app.ml.pipeline import ml_pipe
import app.core.state as state

try:
    d = '2026-03-25'
    curr_s, prev_s = seasons(d)
    state._curr_s, state._prev_s = curr_s, prev_s
    _load_lig(curr_s)
    fetch_injury_report(d)
    
    res = predict_player(2544, 'LeBron James', 'LAL', 'DEN', True, d, 'F')
    print("RESULT:", res)
except Exception as e:
    traceback.print_exc()
