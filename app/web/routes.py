from flask import Blueprint, jsonify, request, render_template, Response
import threading
import pandas as pd
import sqlite3
import datetime
import io

from app.core.config import RUNTIME_CONFIG, ADVANCED_ML, DB, log
import app.core.state as state
from app.core.utils import _norm_name, seasons
from app.data.nba_api import _load_lig, fetch_injury_report, scoreboard_games_for_date
from app.data.odds_api import get_odds_client
from app.services.predict_service import get_run_preds
from app.services.backtest_service import run_backtest
from app.services.sgp_service import build_sgps

web_bp = Blueprint('web', __name__)

@web_bp.route('/')
def index():
    return render_template('index.html')

@web_bp.route('/api/status', methods=['GET'])
def api_status():
    from app.core.config import ADVANCED_ML
    return jsonify({
        'advanced_ml': ADVANCED_ML,
        'odds_configured': True  # PrizePicks için her zaman aktif
    })

@web_bp.route('/api/config', methods=['POST'])
def api_update_config():
    data = request.json
    key = data.get('odds_api_key', '').strip()
    if key:
        RUNTIME_CONFIG['odds_api_key'] = key
        log.info("Odds API Key updated at runtime")
    return jsonify({"status": "saved"})

@web_bp.route('/api/games', methods=['GET'])
def api_games():
    d = request.args.get('date', datetime.datetime.now().strftime('%Y-%m-%d'))
    try:
        games = scoreboard_games_for_date(d)
        return jsonify({
            'games': games,
            'nba_calendar_date': d,
            'hint': 'Tarih NBA Stats takvim günüdür (ABD Doğu). SofaScore’da yerel saat farkıyla ±1 gün sekmesine bakın.',
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@web_bp.route('/api/predict', methods=['POST'])
def api_predict():
    data = request.json
    use_stake = data.get('use_stake', False)
    d = data.get('date')
    hid, aid = data.get('home_id'), data.get('away_id')
    tid = data.get('team_id')

    curr_s, prev_s = seasons(d)
    if not state._lig_data or curr_s != state._curr_s:
        state._curr_s, state._prev_s = curr_s, prev_s
        if use_stake:
            state.prog_set(2, 'Lig verileri (DEF, PACE) indiriliyor...', 0, 100)
        _load_lig(curr_s)
        if use_stake:
            state.prog_set(4, 'Sakatlık raporu indiriliyor...', 0, 100)
        fetch_injury_report(d)

    if str(tid) == 'BOTH':
        pairs = [(hid, aid, True), (aid, hid, False)]
    else:
        tid = int(tid)
        is_home = (tid == hid)
        opp_id = aid if is_home else hid
        pairs = [(tid, opp_id, is_home)]

    all_preds = get_run_preds(pairs, data['date'], use_stake=use_stake)
    state.prog_done()

    if not all_preds:
        return jsonify({'error': 'Sonuç bulunamadı/yetersiz veri.'})

    sum_dict = {
        'total': len(all_preds),
        'players': len(set(p['player'] for p in all_preds)),
        'avg_win_prob': round(sum(p.get('win_prob', 0) for p in all_preds) / max(len(all_preds), 1)),
        'hot_players': len(set(p['player'] for p in all_preds if p['trend'] == 'HOT')),
        'cold_players': len(set(p['player'] for p in all_preds if p['trend'] == 'COLD')),
    }
    
    sgps = build_sgps(all_preds)
    
    return jsonify({
        'summary': sum_dict,
        'sgps': sgps,
        'preds': sorted(all_preds, key=lambda x: (x.get('edge', 0) * x.get('win_prob', 0)), reverse=True)
    })

@web_bp.route('/api/scan', methods=['POST'])
def api_scan():
    d = request.json.get('date')
    use_stake = request.json.get('use_stake', False)
    curr_s, prev_s = seasons(d)
    if not state._lig_data or curr_s != state._curr_s:
        state._curr_s, state._prev_s = curr_s, prev_s
        if use_stake:
            state.prog_set(2, 'Lig verileri indiriliyor...')
        _load_lig(curr_s)
        if use_stake:
            state.prog_set(4, 'Sakatlık raporu indiriliyor...')
        fetch_injury_report(d)

    if use_stake:
        state.prog_set(4, 'Günün maçları getiriliyor...')
    try:
        sb_list = scoreboard_games_for_date(d)
        if not sb_list:
            return jsonify({'error': 'Maç bulunamadı'})
        pairs = []
        for g in sb_list:
            hid, vid = int(g['home_id']), int(g['away_id'])
            pairs += [(hid, vid, True), (vid, hid, False)]
    except Exception as e:
        return jsonify({'error': str(e)})

    all_preds = get_run_preds(pairs, d, use_stake=use_stake)
    state.prog_done('Tarama tamamlandı')

    if not all_preds: return jsonify({'error': 'Kriterlere uyan sonuç bulunamadı'})

    sgps = build_sgps(all_preds)
    
    res = {'summary': {
        'total': len(all_preds),
        'players': len(set(p['player'] for p in all_preds)),
        'avg_win_prob': round(sum(p.get('win_prob', 0) for p in all_preds)/len(all_preds)),
        'hot_players': len(set(p['player'] for p in all_preds if p['trend'] == 'HOT')),
        'cold_players': len(set(p['player'] for p in all_preds if p['trend'] == 'COLD')),
    }, 
       'sgps': sgps,
       'preds': sorted(all_preds, key=lambda x: (x.get('edge', 0) * x.get('win_prob', 0)), reverse=True),
       'games_scanned': len(pairs)//2}
    return jsonify(res)

@web_bp.route('/api/odds/<date_str>', methods=['GET'])
def api_odds(date_str):
    client = get_odds_client()
    if not client:
        return jsonify({'error': 'İstemci yüklenemedi'})
    try:
        props = client.get_player_props("dummy")
        return jsonify({'players_with_props': len(props), 'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)})

@web_bp.route('/api/progress', methods=['GET'])
def api_progress():
    from app.core.state import get_prog_dict
    return jsonify(get_prog_dict())

@web_bp.route('/api/save_slip', methods=['POST'])
def api_save_slip():
    data = request.json
    nm = data.get('name', 'Adsız Kupon')
    dt = data.get('date', datetime.datetime.now().strftime('%Y-%m-%d'))
    items = data.get('preds', [])
    if not items: return jsonify({'error': 'Seçim yok'})
    avg_e = sum(p.get('edge', 0) for p in items) / len(items)
    avg_c = sum(p.get('win_prob', 0) for p in items) / len(items)
    
    rep = '\\n'.join([f"{p['player']} | {p['stat']} | Line:{p['line']} | Pred:{p['pred']}" for p in items])
    try:
        with sqlite3.connect(DB) as c:
            cur = c.cursor()
            cur.execute("""INSERT INTO slips(Tarih,KuponAdi,Icerik,ToplamSecim,OrtEdge,OrtGuven,Timestamp)
                           VALUES(?,?,?,?,?,?,?)""",
                        (dt, nm, rep, len(items), avg_e, avg_c, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            sid = cur.lastrowid
            c.commit()
        return jsonify({'status': 'ok', 'slip_id': sid})
    except Exception as e:
        return jsonify({'error': str(e)})

@web_bp.route('/api/slips', methods=['GET'])
def api_slips():
    try:
        with sqlite3.connect(DB) as c:
            rows = c.execute("SELECT KuponAdi,Tarih,ToplamSecim,OrtEdge,OrtGuven FROM slips ORDER BY id DESC LIMIT 50").fetchall()
        return jsonify({'slips': [{'ad': r[0], 'tarih': r[1], 'secim': r[2], 'avg_edge': r[3], 'avg_conf': r[4]} for r in rows]})
    except Exception as e:
        return jsonify({'error': str(e)})

@web_bp.route('/api/injuries', methods=['GET'])
def api_injuries_api():
    from app.core.state import _injury_cache
    out = {k: v for k, v in _injury_cache.items() if v.lower() in ('out', 'doubtful')}
    q = {k: v for k, v in _injury_cache.items() if v.lower() == 'questionable'}
    return jsonify({'out': out, 'questionable': q})

@web_bp.route('/api/compare', methods=['POST'])
def api_compare():
    req = request.json
    p1 = req.get('player1')
    p2 = req.get('player2')
    preds = req.get('preds', [])
    res1 = {p['stat']: p for p in preds if p['player'] == p1}
    res2 = {p['stat']: p for p in preds if p['player'] == p2}
    return jsonify({
        'player1': {'name': p1, 'stats': res1},
        'player2': {'name': p2, 'stats': res2}
    })

@web_bp.route('/api/backtest', methods=['POST'])
def api_backtest():
    data = request.json
    return jsonify(run_backtest(data.get('date'), data.get('home_id'), data.get('away_id'), data.get('team_id')))

@web_bp.route('/api/backtest/history', methods=['GET'])
def api_backtest_history():
    from app.core.state import _hit_rate_cache
    stats = []
    for stat, d in _hit_rate_cache.items():
        stats.append({'stat': stat, 'hit_rate': d['hit_rate'], 'avg_error': d['avg_error'], 'total': 0})
    return jsonify({'hit_rates': sorted(stats, key=lambda x: x['hit_rate'], reverse=True)})

@web_bp.route('/api/export/csv', methods=['POST'])
def api_export_csv():
    preds = request.json.get('preds', [])
    if not preds: return jsonify({'error': 'No data'})
    df = pd.DataFrame(preds)
    out = io.BytesIO()
    df.to_csv(out, index=False, encoding='utf-8')
    out.seek(0)
    return Response(out, mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=predictions.csv'})
