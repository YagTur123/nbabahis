import numpy as np
import pandas as pd
import threading
import sqlite3
from datetime import datetime

from nba_api.stats.static import teams as nba_teams

from app.core.config import DB, log
import app.core.state as state
from app.core.utils import _norm_name, seasons
from app.data.nba_api import fetch_box_score, scoreboard_games_for_date
from app.data.database import update_hit_rates
from app.services.predict_service import get_run_preds

def run_backtest(date_str: str, home_id: int = None, away_id: int = None, team_id=None):
    """
    Gerçek backtest — normal predict ile aynı mantık:
    """
    log.info(f"Backtest: {date_str} | home={home_id} away={away_id} team={team_id}")
    state.prog_set(5, 'Maçlar alınıyor...')

    curr_s, prev_s = seasons(date_str)
    state._curr_s, state._prev_s = curr_s, prev_s

    abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}

    sb_list = []
    if home_id and away_id:
        if str(team_id) == 'BOTH' or team_id is None:
            pairs = [(int(home_id), int(away_id), True), (int(away_id), int(home_id), False)]
        else:
            is_home = int(team_id) == int(home_id)
            opp_id = int(away_id) if is_home else int(home_id)
            pairs = [(int(team_id), opp_id, is_home)]
        try:
            sb_list = scoreboard_games_for_date(date_str)
        except Exception as e:
            return {'error': str(e)}
    else:
        try:
            sb_list = scoreboard_games_for_date(date_str)
            if not sb_list:
                return {'error': 'No games found'}
            pairs = []
            for g in sb_list:
                hid, vid = int(g['home_id']), int(g['away_id'])
                pairs += [(hid, vid, True), (vid, hid, False)]
        except Exception as e:
            return {'error': str(e)}

    state.prog_set(10, 'Tahminler hesaplanıyor...')
    all_preds = get_run_preds(pairs, date_str, use_stake=False)

    if not all_preds:
        return {'error': 'No predictions generated'}

    state.prog_set(75, 'Box score alınıyor...')

    hi, ai = (int(home_id), int(away_id)) if home_id and away_id else (None, None)
    if hi is not None and ai is not None:
        game_ids = [
            g['game_id'] for g in sb_list
            if {int(g['home_id']), int(g['away_id'])} == {hi, ai}
        ]
    else:
        game_ids = [g['game_id'] for g in sb_list]

    actual_stats = {} 
    for game_id in game_ids:
        try:
            box_df = fetch_box_score(str(game_id))
            if box_df.empty:
                continue
            for _, row in box_df.iterrows():
                p_name = str(row.get('PLAYER_NAME', ''))
                if not p_name:
                    continue
                norm = _norm_name(p_name)
                t_abbr = str(row.get('TEAM_ABBREVIATION', ''))
                key = (norm, t_abbr)
                if key not in actual_stats:
                    actual_stats[key] = {}
                for col in ['PTS','REB','AST','STL','BLK']:
                    v = row.get(col, 0)
                    if pd.notna(v):
                        actual_stats[key][col] = float(v)
                pts = actual_stats[key].get('PTS', 0)
                reb = actual_stats[key].get('REB', 0)
                ast = actual_stats[key].get('AST', 0)
                stl = actual_stats[key].get('STL', 0)
                blk = actual_stats[key].get('BLK', 0)
                actual_stats[key]['PRA'] = pts + reb + ast
                actual_stats[key]['P+R'] = pts + reb
                actual_stats[key]['P+A'] = pts + ast
                actual_stats[key]['A+R'] = ast + reb
                actual_stats[key]['S+B'] = stl + blk
        except Exception as e:
            log.debug(f"Box score processing error for {game_id}: {e}")

    state.prog_set(90, 'Sonuçlar hesaplanıyor...')

    hits = 0
    total_verified = 0
    abs_errors = []
    bt_preds = []

    for p in all_preds:
        norm = _norm_name(p['player'])
        # Match by player name AND team to handle double-headers correctly
        actual_val = actual_stats.get((norm, p['team']), {}).get(p['stat'])
        entry = {
            'player': p['player'], 'team': p['team'], 'opp': p['opp'],
            'stat': p['stat'], 'predicted': p['pred'], 'line': p['line'],
            'edge': p['edge'], 'conf': p.get('win_prob', 0),
            'trend': p.get('trend',''), 'trend_label': p.get('trend_label',''),
            'actual': None, 'hit': None, 'abs_error': None
        }
        if actual_val is not None:
            entry['actual'] = round(actual_val, 1)
            entry['abs_error'] = round(abs(actual_val - p['pred']), 1)
            
            # Draw / Push Check (v12.5)
            if abs(actual_val - p['line']) < 0.01:
                entry['hit'] = None # Push (Refund)
            else:
                if p['pred'] > p['line']:
                    entry['hit'] = 1 if actual_val > p['line'] else 0
                elif p['pred'] < p['line']:
                    entry['hit'] = 1 if actual_val < p['line'] else 0
                else:
                    entry['hit'] = 0
            
            if entry['hit'] is not None:
                hits += entry['hit']
                total_verified += 1
            abs_errors.append(entry['abs_error'])
        bt_preds.append(entry)

    try:
        with sqlite3.connect(DB) as conn:
            for entry in bt_preds:
                if entry.get('actual') is not None:
                    conn.execute("""
                        INSERT INTO backtest_results
                        (TestDate, TrainUntil, Oyuncu, Takim, Rakip, Stat,
                         Tahmin, Gercek, Barem, Hit, AbsError, 
                         WinProb, EV, Edge, Timestamp)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (date_str, date_str, entry['player'], entry['team'], entry['opp'],
                          entry['stat'], entry['predicted'], entry['actual'], entry['line'],
                          entry['hit'], entry['abs_error'],
                          entry['conf'], p.get('ev', 0), entry['edge'],
                          datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
        threading.Thread(target=update_hit_rates, daemon=True).start()
    except Exception as e:
        log.warning(f"Backtest DB save error: {e}")

    state.prog_done('Backtest tamamlandı')

    win_rate = round((hits / total_verified) * 100, 1) if total_verified > 0 else 0
    avg_error = round(np.mean(abs_errors), 2) if abs_errors else 0
    
    # Sabit 1.90 odd ile ROI
    profit = 0
    for entry in bt_preds:
        if entry.get('hit') is not None:
            if entry['hit'] == 1:
                profit += 0.90
            else:
                profit -= 1

    roi = round((profit / total_verified) * 100, 1) if total_verified > 0 else 0

    return {
        'total_predictions': len(bt_preds),
        'verified': total_verified,
        'unverified': len(bt_preds) - total_verified,
        'hits': hits,
        'win_rate': win_rate,
        'avg_error': avg_error,
        'roi': roi,
        'avg_edge': round(np.mean([r['edge'] for r in bt_preds]), 2) if bt_preds else 0,
        'avg_conf': round(np.mean([r['conf'] for r in bt_preds]), 1) if bt_preds else 0,
        'target_date': date_str,
        'predictions': sorted(
            [p for p in bt_preds if p.get('actual') is not None],
            key=lambda x: x.get('abs_error', 99)
        )[:200] + [p for p in bt_preds if p.get('actual') is None][:50]
    }
