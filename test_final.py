import app.core.state as state
from app.services.predict_service import get_run_preds
from app.data.nba_api import _load_lig
from app.core.utils import seasons
import traceback

d = '2026-04-03'
try:
    curr, _ = seasons(d)
    state._curr_s, state._prev_s = curr, _
    _load_lig(curr)
    pairs = [(1610612747, 1610612749, True)]
    print('Calling get_run_preds...')
    preds = get_run_preds(pairs, d, use_stake=False)
    
    print('Total Returned:', len(preds))
    if len(preds) > 0:
        for p in preds[:7]:
            print(f"{p['player']} - {p['stat']}: PROB={p['win_prob']}% EDGE={p['edge']}")
    else:
        print('NO RESULTS RETURNED!')
except Exception as e:
    print('CRASHED:')
    traceback.print_exc()
