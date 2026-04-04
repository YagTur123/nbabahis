import pandas as pd
import numpy as np
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

from nba_api.stats.endpoints import commonteamroster
from nba_api.stats.static import teams as nba_teams

from app.core.config import (
    MIN_GAMES, MIN_AVG_MIN, MIN_RECENT_MIN, MAX_INJURY_GAP, ALL_STATS, 
    FLOOR, CV_LIMITS, STAT_POSITION_WEIGHT, MAX_THREADS, log
)
import app.core.state as state
from app.core.utils import _norm_name

from app.data.nba_api import get_data, is_injured, get_opp_def_factor, nba_request
from app.data.odds_api import get_odds_client
from app.ml.features import create_advanced_features
from app.ml.pipeline import detect_trend, kelly_criterion, ml_pipe

def calc_blowout(df, team_abbr, opp_abbr, raw):
    with state._lig_lock:
        own_wpct = state._lig_data.get(team_abbr, {}).get('W_PCT', 0.5)
        opp_wpct = state._lig_data.get(opp_abbr, {}).get('W_PCT', 0.5)
        margin_diff = state._lig_data.get(team_abbr, {}).get('AVG_MARGIN', 0.0) - state._lig_data.get(opp_abbr, {}).get('AVG_MARGIN', 0.0)
    
    wpct_diff = own_wpct - opp_wpct
    blowout_risk = False
    blowout_mod = 1.0
    is_underdog = wpct_diff < 0
    if abs(wpct_diff) < 0.22:
        return blowout_risk, blowout_mod, is_underdog
    recent_pm = df['PLUS_MINUS'].tail(5).mean() if 'PLUS_MINUS' in df.columns else 0.0
    blowout_score = abs(wpct_diff)*0.50 + min(abs(margin_diff)/20, 0.30)*0.30 + min(abs(recent_pm)/15, 0.20)*0.20
    if blowout_score < 0.28:
        return blowout_risk, blowout_mod, is_underdog
    blowout_risk = True
    avg_min = raw['MIN'].mean()
    if avg_min >= 32.0: blowout_mod = 0.82 if is_underdog else 0.87
    elif avg_min >= 27.0: blowout_mod = 0.92 if is_underdog else 0.93
    elif avg_min >= 22.0: blowout_mod = 1.00
    else: blowout_mod = 1.20 if is_underdog else 1.12
    return blowout_risk, blowout_mod, is_underdog

from app.data.advanced_stats import calc_travel_fatigue, get_missing_usage_shift

def predict_player(pid, name, team_abbr, opp_abbr, is_home, date_str, position, odds_props: Dict = None, usage_shifts: Dict[str, float] = None, use_market_odds: bool = True):
    # usage_shifts can be a Dict {'G': 1.1, 'F': 1.05, ...}
    usage_shifts = usage_shifts or {'G': 1.0, 'F': 1.0, 'C': 1.0, 'default': 1.0}
    raw = get_data(pid)
    if raw.empty or len(raw) < MIN_GAMES:
        return []
        
    raw['GAME_DATE'] = pd.to_datetime(raw['GAME_DATE'])
    target = pd.to_datetime(date_str)
    history = raw[raw['GAME_DATE'] < target].sort_values('GAME_DATE')
    if len(history) < 1:
        return []
    from app.data.nba_api import get_injury_status
    status = get_injury_status(name)
    if status in ('out', 'doubtful'):
        return []
    
    # v12.9: GTD (Game-Time Decision) Handling
    is_gtd = 'question' in status or 'gtd' in status
    
    df_feat = create_advanced_features(history.copy())
    if df_feat.empty or len(df_feat) < 1:
        return []

    blowout_risk, blowout_mod, is_underdog = calc_blowout(df_feat, team_abbr, opp_abbr, raw)
    with state._lig_lock:
        opp_reb_mod = state._lig_data.get(opp_abbr, {}).get('REB_MOD', 1.0)
        def_mod = state._lig_data.get(opp_abbr, {}).get('DEF_MOD', 1.0)
        pace_mod = state._lig_data.get(opp_abbr, {}).get('PACE_MOD', 1.0)
    pos_str = str(position).upper()
    is_guard = 'G' in pos_str
    is_center = 'C' in pos_str
    
    rest = (target - history['GAME_DATE'].iloc[-1]).days
    if rest > MAX_INJURY_GAP:
        log.info(f"[{name}] DROP: Too much rest ({rest} days)")
        return []

    if history['MIN'].mean() < MIN_AVG_MIN or history['MIN'].tail(3).mean() < MIN_RECENT_MIN:
        log.info(f"[{name}] DROP: Low minutes")
        return []

    if len(history) >= 1 and history['MIN'].iloc[-1] == 0:
        log.info(f"[{name}] DROP: 0 mins last game")
        return []
    if len(history) >= 3 and history['MIN'].tail(3).sum() == 0:
        log.info(f"[{name}] DROP: 0 mins last 3 games")
        return []
        
    travel_fatigue = calc_travel_fatigue(team_abbr, is_home, opp_abbr, history, date_str)
    
    results = []

    for stat in ALL_STATS:
        if stat not in df_feat.columns:
            continue
        avg = df_feat[stat].mean()
        cv = df_feat[stat].std() / (avg + 0.1)
        if pd.isna(cv): cv = 0.0

        model_data = ml_pipe.train(df_feat, stat, pid)
        if not model_data:
            continue
        pred_result = ml_pipe.predict(model_data, stat)
        if not pred_result:
            continue

        pred = pred_result['pred']

        if is_home:
            home_avg = df_feat[df_feat['HOME'] == 1][stat].mean()
            if not np.isnan(home_avg) and avg > 0:
                pred *= min(max(home_avg/avg, 0.90), 1.15)
        else:
            away_avg = df_feat[df_feat['HOME'] == 0][stat].mean()
            if not np.isnan(away_avg) and avg > 0:
                pred *= min(max(away_avg/avg, 0.87), 1.10)

        if rest <= 1: pred *= 0.94
        elif rest >= 3: pred *= 1.03

        pred *= blowout_mod
        pred *= travel_fatigue
        
        volume_stats = {'PTS','AST','REB','FGA','FG3A','FTA','FGM','FG3M','FTM','PRA','P+R','P+A','A+R','TOV','STL','BLK','S+B','PF'}
        if stat in volume_stats:
            pos_key = 'C' if 'C' in pos_str else ('F' if 'F' in pos_str else 'G')
            u_mult = usage_shifts.get(pos_key, usage_shifts.get('default', 1.0))
            pred *= u_mult

        h2h = df_feat[df_feat['OPP'] == opp_abbr][stat]
        if len(h2h) >= 2:
            pred = pred * 0.82 + h2h.mean() * 0.18

        pw = STAT_POSITION_WEIGHT.get(stat, (1.0, 1.0, 1.0))
        pos_mult = pw[0] if is_guard else (pw[2] if is_center else pw[1])
        pred *= (def_mod ** pos_mult) * (1 + (pace_mod - 1) * 0.45)

        if stat in ('REB', 'PRA', 'P+R', 'A+R'):
            pred *= (2.0 - opp_reb_mod)

        opp_def_factor = get_opp_def_factor(opp_abbr, stat, position)
        matchup_mod = 1.0
        
        # v13.4: Birebir Savunmacı Eşleşmesi (Player vs Player Matchup)
        # Sadece sayı, asist ve üçlük (turnover vb. için de geçerli)
        num_stat = stat in ['PTS', 'AST', 'FG3M', 'TOV', 'PRA', 'PR', 'PA']
        if num_stat and opp_abbr in state._team_rosters:
            opp_players = state._team_rosters[opp_abbr]
            # Kendi pozisyon grubuma yakın olan rakip oyuncuları bul
            my_pos_family = 'G' if is_guard else ('C' if is_center else 'F')
            opp_defenders = []
            
            with state._player_def_rating_lock:
                for p in opp_players:
                    # p is a dict {'name': '...', 'pos': '...'}
                    if isinstance(p, dict):
                        p_pos = p.get('pos', 'G').upper()
                        if my_pos_family in p_pos or (my_pos_family == 'F' and 'C' in p_pos):
                            p_rating = state._player_def_rating.get(_norm_name(p['name']), 113.0)
                            opp_defenders.append(p_rating)
            
            if opp_defenders:
                opp_defenders = sorted(opp_defenders)
                # En iyi 2 savunmacının ortalamasını al
                best_2_def = sum(opp_defenders[:2]) / min(2, len(opp_defenders))
                
                # Def Rating: < 108 ise elit, > 115 ise çok kötü
                # Normalize edelim: 108 -> 0.94 (bizi %6 düşürsün)
                # 116 -> 1.05 (bizi %5 artırsın)
                if best_2_def < 108.0:
                    matchup_mod = 0.94
                elif best_2_def < 111.0:
                    matchup_mod = 0.97
                elif best_2_def > 116.0:
                    matchup_mod = 1.05
                elif best_2_def > 114.0:
                    matchup_mod = 1.02

        pred *= (0.7 + opp_def_factor * 0.3) * matchup_mod

        trend_info = detect_trend(df_feat, stat)
        if trend_info['trend'] == 'HOT':
            pred *= 1.04
        elif trend_info['trend'] == 'COLD':
            pred *= 0.96
            
        # v12.9: GTD production caution (5% reduction for questionable players)
        if is_gtd:
            pred *= 0.95

        market_line = None
        best_bookmaker = None
        market_odds = None
        all_lines = {}

        if use_market_odds and odds_props:
            client = get_odds_client()
            if client:
                best_odds = client.find_best_line(odds_props, _norm_name(name), stat)
                if best_odds:
                    market_line = best_odds['line']
                    best_bookmaker = best_odds['bookmaker']
                    market_odds = best_odds['odds']
                    all_lines = best_odds.get('all_lines', {})

        # Stake/Odds kapalıyken sentetik barem ve oran üretme (sadece ham tahmin)
        if use_market_odds and (market_line is None or market_line == 0):
            market_line = round(pred * 0.94, 1)
            market_line = max(market_line, 0.1)
            best_bookmaker = 'Model'
            market_odds = 1.90

        if market_line is not None and market_line > 0:
            edge = pred - market_line
            edge_pct = ((pred - market_line) / market_line) * 100
        else:
            edge = 0.0
            edge_pct = 0.0
        
        # EV / Kelly — yalnızca geçerli barem ve oran varken
        if market_line is not None and market_odds and market_odds > 1:
            implied_prob = 1 / market_odds
            edge_ratio = abs(edge) / (market_line + 1e-6)
            prob_boost = min(0.20, edge_ratio * 0.7)
            our_est_prob = 0.50 + prob_boost if edge != 0 else 0.50
            ev = (our_est_prob * market_odds) - (1 - our_est_prob)
            kelly_frac = kelly_criterion(pred, market_line, market_odds, stat)
        else:
            implied_prob = 0.0
            ev = 0.0
            kelly_frac = 0.0

        conf = int(pred_result['confidence'])

        # Risk ve Güven Skorları (ölçek-duyarlı: ham disagreement küçük pred'lerde şişmesin)
        pred_mag = max(float(pred), 0.5)
        base_risk = min(50, cv * 48)
        rel_disagree = float(pred_result['disagreement']) / pred_mag
        model_gap_risk = min(38, rel_disagree * 22.0)
        rest_risk = 6 if rest <= 1 else 0
        market_risk = 5 if (market_line is not None and market_line > 0 and abs(edge) < 1) else 0
        trend_risk = -5 if trend_info['trend'] in ('HOT','COLD') else 0
        total_risk = min(88, base_risk + model_gap_risk + rest_risk + market_risk + trend_risk)

        import math
        std_dev = cv * max(pred, 1.0)
        z_score = (abs(edge) / max(std_dev, 0.1)) if (market_line is not None and market_line > 0) else 0.0

        # Barem/oran yok: yapay edge’e dayanmadan yalnızca model güveni
        if market_line is None or market_odds is None:
            tr = min(88, base_risk + model_gap_risk + rest_risk + trend_risk)
            sim_win_prob = min(88.0, 55.0 + (conf * 0.38))
            win_prob = max(1.0, min(99.0, (sim_win_prob * 0.5) + (conf * 0.5) - (tr / 22)))
        elif best_bookmaker == 'Model':
            sim_win_prob = min(88.0, 52.0 + (conf * 0.35) + min(z_score * 5.0, 15.0))
            win_prob = max(1.0, min(99.0, (sim_win_prob * 0.45) + (conf * 0.55) - (total_risk / 20)))
        else:
            sim_win_prob = (1 / (1 + math.exp(-z_score * 1.4))) * 100
            win_prob = max(1.0, min(99.0, (sim_win_prob * 0.65) + (conf * 0.35) - (total_risk / 9)))

        # v12.5: Model Calibration (Real-world performance audit)
        with state._hit_rate_lock:
            hist_perf = state._hit_rate_cache.get(stat, {}).get('hit_rate', 0.524)
        
        # Hist_perf / 0.524 => Gerçek performans / Beklenen performans (Breakeven)
        calib_mult = max(0.8, min(1.15, hist_perf / 0.524))
        win_prob = max(1.0, min(99.0, win_prob * calib_mult))

        is_danger = bool(market_line is not None and market_line > 0 and abs(edge_pct) > 25)

        results.append({
            'player': str(name),
            'pid': int(pid),
            'team': str(team_abbr),
            'opp': str(opp_abbr),
            'stat': str(stat),
            'expected_outcome': ('OVER' if edge > 0 else 'UNDER') if (market_line is not None) else '—',
            'is_danger': is_danger,
            'pred': float(round(pred, 1)),
            'avg': float(round(avg, 1)),
            'floor': float(round(pred_result.get('low_quantile', pred * 0.7), 1)),
            'ceiling': float(round(pred_result.get('high_quantile', pred * 1.3), 1)),
            'win_prob': float(round(win_prob, 1)),
            'ev': float(round(ev, 3)),

            'disagreement': round(pred_result['disagreement'], 3),
            'models': list(pred_result['predictions'].keys()),
            'b2b': bool(rest <= 1),
            'home': bool(is_home),
            'blowout': bool(blowout_risk),
            'underdog': bool(is_underdog),
            'line': (float(market_line) if market_line is not None else None),
            'edge': float(round(edge, 1)),
            'edge_pct': float(round(edge_pct, 1)),
            'best_bookmaker': best_bookmaker,
            'market_odds': (float(market_odds) if market_odds is not None else None),
            'all_lines': all_lines,
            'kelly': round(kelly_frac * 100, 2),
            'cv': round(cv, 2),
            'last10': [float(v) for v in df_feat[stat].tail(10).tolist()],
            'has_market_odds': bool(best_bookmaker and best_bookmaker != 'Model'),
            'trend': trend_info['trend'],
            'trend_pct': trend_info['pct'],
            'trend_label': trend_info['label'],
            'position': position,
            'h2h_games': int(len(h2h)),
            'h2h_avg': float(round(h2h.mean(), 1)) if len(h2h) > 0 else None,
        })

    return results

def get_run_preds(pairs, date_str, use_stake=True):
    abbr_map = {t['id']: t['abbreviation'] for t in nba_teams.get_teams()}
    all_preds = []
    total = 0
    rosters = {}
    odds_data = None

    if use_stake:
        state.prog_set(4, 'Oyuncu bahis oranları (Odds) çekiliyor...')
        client = get_odds_client()
        if client:
            try:
                props = client.get_player_props("dummy", use_stake=use_stake)
                odds_data = props if props else {}
                log.info(f"Fetched odds for {len(odds_data)} players")
            except Exception as e:
                log.error(f"Odds fetch error: {e}")
                odds_data = {}
    # use_stake=False ise odds bloğu tamamen atlanır, odds_data=None kalır

    state.prog_set(4, 'Takım kadroları yükleniyor...')
    for (tid, opp_id, is_home) in pairs:
        try:
            dfs = nba_request(commonteamroster.CommonTeamRoster, team_id=tid)
            if not dfs:
                continue
            ros = dfs[0]
            rosters[(tid, opp_id, is_home)] = ros
            total += len(ros)
            ta = abbr_map.get(tid, '???')
            if ta and ta != '???':
                with state._rosters_lock:
                    state._team_rosters[ta] = [{'name': str(r['PLAYER']), 'pos': str(r.get('POSITION', 'G'))} for _, r in ros.iterrows()]
        except:
            rosters[(tid, opp_id, is_home)] = None

    # Calculate missing usage across all teams, now position-aware
    team_usage_shifts = {}
    with state._usage_lock:
        usage_copy = state._player_usage.copy()
    for (tid, opp_id, is_home), ros in rosters.items():
        if ros is None: continue
        ta = abbr_map.get(tid, '???')
        roster_info = [{'name': str(r['PLAYER']), 'pos': str(r.get('POSITION', 'G'))} for _, r in ros.iterrows()]
        team_usage_shifts[ta] = get_missing_usage_shift(ta, is_injured, roster_info, usage_copy)

    state.prog_set(5, f'{total} oyuncu analiz ediliyor', 0, total)
    done = 0

    for (tid, opp_id, is_home), ros in rosters.items():
        if ros is None:
            continue
        ta = abbr_map.get(tid, '???')
        oa = abbr_map.get(opp_id, '???')
        tasks = [
            (r['PLAYER_ID'], r['PLAYER'], ta, oa, is_home, date_str, r.get('POSITION', ''), odds_data, team_usage_shifts.get(ta), use_stake)
            for _, r in ros.iterrows()
        ]
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
            futs = {ex.submit(predict_player, *t): t for t in tasks}
            for f in as_completed(futs):
                try:
                    res = f.result()
                    if res:
                        all_preds.extend(res)
                except Exception as e:
                    log.warning(f"predict_player error: {e}")
                    log.exception(e)
                finally:
                    done += 1
                    state.prog_set(5 + int(done / max(total, 1) * 90), f'{done}/{total} oyuncu', done, total)

    return all_preds
