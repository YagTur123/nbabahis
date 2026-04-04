import sqlite3
from datetime import datetime
from typing import Dict

from app.core.config import DB, log
from app.core.state import _hit_rate_lock, _hit_rate_cache

def db_init():
    with sqlite3.connect(DB) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS predictions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Tarih TEXT, Oyuncu TEXT, Takim TEXT, Rakip TEXT,
            Stat TEXT, Tahmin REAL, Barem REAL, Risk REAL, Guven INTEGER,
            Models TEXT, MarketLine REAL, Edge REAL, BestBookmaker TEXT,
            Trend TEXT, HitRate REAL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS slips(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Tarih TEXT, KuponAdi TEXT, Icerik TEXT,
            ToplamSecim INTEGER, OrtEdge REAL, OrtGuven REAL,
            OrtValue REAL, Timestamp TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS backtest_results(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            TestDate TEXT, TrainUntil TEXT, Oyuncu TEXT, Takim TEXT,
            Rakip TEXT, Stat TEXT, Tahmin REAL, Gercek REAL,
            Barem REAL, Hit INTEGER, AbsError REAL,
            WinProb REAL, EV REAL, Edge REAL,
            Timestamp TEXT)''')
        
        # v12.5 & v13.1: Auto-Migration for new audit columns
        # backtest_results table
        cursor = c.execute("PRAGMA table_info(backtest_results)")
        cols_bt = [r[1] for r in cursor.fetchall()]
        for new_col in [('WinProb', 'REAL'), ('EV', 'REAL'), ('Edge', 'REAL')]:
            if new_col[0] not in cols_bt:
                try:
                    c.execute(f"ALTER TABLE backtest_results ADD COLUMN {new_col[0]} {new_col[1]}")
                    log.info(f"Database Migration: Added {new_col[0]} to backtest_results")
                except: pass
        
        # predictions table (sync)
        cursor = c.execute("PRAGMA table_info(predictions)")
        cols_pred = [r[1] for r in cursor.fetchall()]
        for new_col in [('WinProb', 'REAL'), ('EV', 'REAL')]:
            if new_col[0] not in cols_pred:
                try:
                    c.execute(f"ALTER TABLE predictions ADD COLUMN {new_col[0]} {new_col[1]}")
                    log.info(f"Database Migration: Added {new_col[0]} to predictions")
                except: pass
        c.execute('''CREATE TABLE IF NOT EXISTS hit_rates(
            Stat TEXT PRIMARY KEY, Hits INTEGER, Total INTEGER,
            HitRate REAL, AvgError REAL, LastUpdated TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS optuna_params(
            PlayerID INTEGER, Stat TEXT, ModelName TEXT, ParamKey TEXT,
            ParamValue REAL, LastUpdated TEXT,
            PRIMARY KEY (PlayerID, Stat, ModelName, ParamKey))''')
        c.commit()

def load_optuna_params(pid: int, stat: str, model_name: str) -> Dict:
    """DB'den oyuncu ve stat için model parametrelerini yükle"""
    try:
        with sqlite3.connect(DB) as conn:
            rows = conn.execute(
                "SELECT ParamKey, ParamValue FROM optuna_params WHERE PlayerID=? AND Stat=? AND ModelName=?",
                (pid, stat, model_name)
            ).fetchall()
            res = {}
            for r in rows:
                k, v = r[0], r[1]
                if k in ['n_estimators', 'max_depth', 'num_leaves', 'min_child_samples']:
                    v = int(v)
                res[k] = v
            return res
    except:
        return {}

def save_optuna_params(pid: int, stat: str, model_name: str, params: Dict):
    """Bulunan Optuna parametrelerini DB'ye kaydet"""
    try:
        with sqlite3.connect(DB) as conn:
            for k, v in params.items():
                conn.execute("""
                    INSERT OR REPLACE INTO optuna_params (PlayerID, Stat, ModelName, ParamKey, ParamValue, LastUpdated)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (pid, stat, model_name, k, float(v), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
    except Exception as e:
        log.warning(f"Optuna params save failed: {e}")

def load_hit_rates() -> Dict:
    """DB'den geçmiş hit rate'leri yükle"""
    try:
        with sqlite3.connect(DB) as conn:
            rows = conn.execute("SELECT Stat, HitRate, AvgError FROM hit_rates").fetchall()
            return {r[0]: {'hit_rate': r[1], 'avg_error': r[2]} for r in rows}
    except:
        return {}

def update_hit_rates():
    """Backtest sonuçlarından hit rate güncelle"""
    try:
        with sqlite3.connect(DB) as conn:
            rows = conn.execute("""
                SELECT Stat,
                    COUNT(*) as total,
                    SUM(Hit) as hits,
                    AVG(AbsError) as avg_err
                FROM backtest_results
                WHERE Hit IS NOT NULL
                GROUP BY Stat
            """).fetchall()

            for stat, total, hits, avg_err in rows:
                hit_rate = (hits / total) if total > 0 else 0.52
                conn.execute("""
                    INSERT OR REPLACE INTO hit_rates (Stat, Hits, Total, HitRate, AvgError, LastUpdated)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (stat, hits or 0, total, round(hit_rate, 3), round(avg_err or 2.0, 2),
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()

        with _hit_rate_lock:
            _hit_rate_cache.clear()
            _hit_rate_cache.update(load_hit_rates())

        log.info(f"Hit rates updated for {len(rows)} stats")
    except Exception as e:
        log.warning(f"Hit rate update failed: {e}")
