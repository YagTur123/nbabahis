import numpy as np
import pandas as pd
from typing import Dict, Optional

from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

from app.core.config import ADVANCED_ML, MODEL_WEIGHTS, log
import app.core.state as state
import joblib
import os
import time

if ADVANCED_ML:
    import xgboost as xgb
    import lightgbm as lgb
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    from app.data.database import load_optuna_params, save_optuna_params

def detect_trend(df: pd.DataFrame, stat: str) -> dict:
    """HOT/COLD/NEUTRAL trend tespiti"""
    if stat not in df.columns or len(df) < 8:
        return {'trend': 'NEUTRAL', 'pct': 0, 'label': ''}

    season_avg = df[stat].mean()
    recent_avg = df[stat].tail(5).mean()

    if season_avg == 0:
        return {'trend': 'NEUTRAL', 'pct': 0, 'label': ''}

    pct_diff = ((recent_avg - season_avg) / season_avg) * 100
    above_avg = (df[stat].tail(5) > season_avg).sum()

    if pct_diff >= 20 and above_avg >= 4:
        return {'trend': 'HOT', 'pct': round(pct_diff, 1), 'label': '🔥'}
    elif pct_diff <= -20 and above_avg <= 1:
        return {'trend': 'COLD', 'pct': round(pct_diff, 1), 'label': '❄️'}
    elif pct_diff >= 12 and above_avg >= 3:
        return {'trend': 'WARM', 'pct': round(pct_diff, 1), 'label': '📈'}
    elif pct_diff <= -12 and above_avg <= 2:
        return {'trend': 'COOLING', 'pct': round(pct_diff, 1), 'label': '📉'}
    else:
        return {'trend': 'NEUTRAL', 'pct': round(pct_diff, 1), 'label': ''}

def kelly_criterion(pred: float, line: float, market_odds: float, stat: str) -> float:
    """Gerçekçi Kelly fraction hesapla"""
    if market_odds <= 1 or line <= 0:
        return 0

    with state._hit_rate_lock:
        stat_data = state._hit_rate_cache.get(stat, {})
    our_prob = stat_data.get('hit_rate', 0.52)

    edge_ratio = (pred - line) / (line + 1e-6)
    if edge_ratio > 0.1:
        our_prob = min(0.72, our_prob + edge_ratio * 0.5)
    elif edge_ratio < -0.05:
        our_prob = max(0.35, our_prob + edge_ratio * 0.3)

    b = market_odds - 1
    kelly = ((b * our_prob) - (1 - our_prob)) / b if b > 0 else 0
    
    # İstatistiğin volatilitesine göre muhafazakar katsayı uygula
    variance_multiplier = 1.0
    if stat in ('BLK', 'STL', 'S+B', 'FG3M'):
        variance_multiplier = 0.6  # Blok/Çalma gibi yüksek sapmalı işlerde daha az bas
    elif stat in ('TOV', 'PF', 'FG3A'):
        variance_multiplier = 0.8
        
    return max(0, min(kelly * 0.25 * variance_multiplier, 0.05))  

class MLPipeline:
    def get_cache_key(self, pid, stat):
        return f"{pid}_{stat}_{state._curr_s}"

    def _sample_weights(self, n: int) -> np.ndarray:
        # Aggressive recency weighting: exp(0 to 2.5) for v12.1
        w = np.exp(np.linspace(0, 2.5, n))
        return w / w.sum()

    def _select_features(self, df: pd.DataFrame, stat: str, feature_cols: list) -> list:
        stat_base = stat.split('+')[0].replace('PRA','PTS')
        priority = []
        for c in feature_cols:
            if stat_base in c or stat.replace('+','') in c:
                priority.append((0, c))
            elif any(x in c for x in ['EMA','ROLL','LAG','TREND','MOM','VOL']):
                priority.append((1, c))
            elif c in ['HOME','REST_DAYS','B2B','GAMES_LAST_7','USAGE_RATE','SEASON_PART']:
                priority.append((2, c))
            else:
                priority.append((3, c))
        priority.sort(key=lambda x: x[0])
        return [c for _, c in priority[:40]]

    def train(self, df: pd.DataFrame, stat: str, pid: int):
        cache_key = self.get_cache_key(pid, stat)
        
        # v12.9: Disk Caching / Serialization
        model_path = os.path.join('models', f"{cache_key}.joblib")
        
        with state._model_cache_lock:
            if cache_key in state._model_cache:
                return state._model_cache[cache_key]
        
        if os.path.exists(model_path):
            try:
                # 18 saatten eski modelleri tazele (Yeni gün verisi için)
                if (time.time() - os.path.getmtime(model_path)) < 18 * 3600:
                    res = joblib.load(model_path)
                    with state._model_cache_lock:
                        state._model_cache[cache_key] = res
                    return res
            except: pass

        if len(df) < 6:
            return None
        exclude = ['GAME_DATE','MATCHUP','OPP','PLAYER_ID','SEASON', stat]
        all_feature_cols = [c for c in df.columns if c not in exclude
                        and df[c].dtype in ['float64','int64','float32','int32']]
        if len(all_feature_cols) < 3:
            return None

        feature_cols = self._select_features(df, stat, all_feature_cols)

        X = df[feature_cols].iloc[:-1]
        y = df[stat].iloc[1:]
        if len(X) != len(y):
            min_len = min(len(X), len(y))
            X, y = X.iloc[:min_len], y.iloc[:min_len]

        sample_w = self._sample_weights(len(X))
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        models = {}
        if ADVANCED_ML:
            xgb_p = load_optuna_params(pid, stat, 'xgb')
            if not xgb_p:
                def obj_xgb(trial):
                    p = {
                        'n_estimators': trial.suggest_int('n_estimators', 50, 150),
                        'max_depth': trial.suggest_int('max_depth', 2, 5),
                        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1),
                        'subsample': trial.suggest_float('subsample', 0.5, 0.9),
                        'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 0.9)
                    }
                    m = xgb.XGBRegressor(**p, random_state=42, n_jobs=1)
                    
                    if len(X_scaled) < 10:
                        m.fit(X_scaled, y, sample_weight=sample_w)
                        return abs(y.iloc[-1] - m.predict(X_scaled[-1:].reshape(1,-1))[0])
                    
                    tscv = TimeSeriesSplit(n_splits=3)
                    errs = []
                    for tr_idx, val_idx in tscv.split(X_scaled):
                        X_tr, y_tr = X_scaled[tr_idx], y.iloc[tr_idx]
                        X_val, y_val = X_scaled[val_idx], y.iloc[val_idx]
                        sw_tr = sample_w[tr_idx] if sample_w is not None else None
                        try:
                            m.fit(X_tr, y_tr, sample_weight=sw_tr)
                            pred = m.predict(X_val)
                            errs.append(np.mean(np.abs(y_val - pred)))
                        except: pass
                    
                    return np.mean(errs) if errs else 999.0
                    
                study = optuna.create_study(direction="minimize")
                study.optimize(obj_xgb, n_trials=5)
                xgb_p = study.best_params
                save_optuna_params(pid, stat, 'xgb', xgb_p)

            lgb_p = load_optuna_params(pid, stat, 'lgb')
            if not lgb_p:
                def obj_lgb(trial):
                    p = {
                        'n_estimators': trial.suggest_int('n_estimators', 50, 150),
                        'max_depth': trial.suggest_int('max_depth', 2, 5),
                        'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.1),
                        'num_leaves': trial.suggest_int('num_leaves', 10, 30),
                        'subsample': trial.suggest_float('subsample', 0.5, 0.9),
                    }
                    m = lgb.LGBMRegressor(**p, random_state=42, n_jobs=1, verbose=-1)
                    
                    if len(X_scaled) < 10:
                        m.fit(X_scaled, y, sample_weight=sample_w)
                        return abs(y.iloc[-1] - m.predict(X_scaled[-1:].reshape(1,-1))[0])
                    
                    tscv = TimeSeriesSplit(n_splits=3)
                    errs = []
                    for tr_idx, val_idx in tscv.split(X_scaled):
                        X_tr, y_tr = X_scaled[tr_idx], y.iloc[tr_idx]
                        X_val, y_val = X_scaled[val_idx], y.iloc[val_idx]
                        sw_tr = sample_w[tr_idx] if sample_w is not None else None
                        try:
                            m.fit(X_tr, y_tr, sample_weight=sw_tr)
                            pred = m.predict(X_val)
                            errs.append(np.mean(np.abs(y_val - pred)))
                        except: pass
                        
                    return np.mean(errs) if errs else 999.0
                    
                study = optuna.create_study(direction="minimize")
                study.optimize(obj_lgb, n_trials=5)
                lgb_p = study.best_params
                save_optuna_params(pid, stat, 'lgb', lgb_p)

            models['xgb'] = xgb.XGBRegressor(**xgb_p, random_state=42, n_jobs=1)
            models['lgb'] = lgb.LGBMRegressor(**lgb_p, random_state=42, n_jobs=1, verbose=-1)
            
            # v12.1: Quantile Models (Median, Floor, Ceiling)
            for alpha, name in [(0.5, 'median'), (0.2, 'low'), (0.8, 'high')]:
                lgb_q_p = lgb_p.copy()
                lgb_q_p['objective'] = 'quantile'
                lgb_q_p['alpha'] = alpha
                models[f'lgb_{name}'] = lgb.LGBMRegressor(**lgb_q_p, random_state=42, n_jobs=1, verbose=-1)
        models['gbm'] = GradientBoostingRegressor(
            n_estimators=100, max_depth=3, learning_rate=0.04,
            subsample=0.8, min_samples_leaf=3, random_state=42
        )
        models['rf'] = RandomForestRegressor(
            n_estimators=100, max_depth=4, min_samples_leaf=3,
            random_state=42, n_jobs=1
        )
        
        for name, model in list(models.items()):
            try:
                if name in ['xgb', 'lgb']:
                    model.fit(X_scaled, y, sample_weight=sample_w)
                else:
                    model.fit(X, y, sample_weight=sample_w)
            except Exception as e:
                log.debug(f"Training failed for {name}: {e}")
                del models[name]

        model_errors = {}
        if len(X) > 12:
            n_splits = 3 if len(X) > 18 else 2
            tscv = TimeSeriesSplit(n_splits=n_splits)
            for mname, model in models.items():
                errs = []
                for train_idx, val_idx in tscv.split(X):
                    try:
                        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
                        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]
                        sw_tr = self._sample_weights(len(X_tr))
                        m_tmp = type(model)(**model.get_params())
                        if mname in ['xgb', 'lgb']:
                            Xtr_s = scaler.transform(X_tr)
                            Xval_s = scaler.transform(X_val)
                            m_tmp.fit(Xtr_s, y_tr, sample_weight=sw_tr)
                            pred_v = m_tmp.predict(Xval_s[-1:].reshape(1,-1))[0]
                        else:
                            m_tmp.fit(X_tr, y_tr, sample_weight=sw_tr)
                            pred_v = m_tmp.predict(X_val.iloc[[-1]])[0]
                        errs.append(abs(float(y_val.iloc[-1]) - float(pred_v)))
                    except:
                        continue
                if errs:
                    model_errors[mname] = np.mean(errs)

        cv_error = np.mean(list(model_errors.values())) if model_errors else 2.0

        result = {
            'models': models, 'scaler': scaler, 'feature_cols': feature_cols,
            'cv_error': cv_error, 'model_errors': model_errors,
            'last_X': X.iloc[-1:] if len(X) > 0 else None,
            'last_X_scaled': scaler.transform(X.iloc[-1:]) if len(X) > 0 else None
        }
        
        # v12.9 Save to disk
        try: joblib.dump(result, model_path)
        except: pass
        
        with state._model_cache_lock:
            state._model_cache[cache_key] = result
        return result

    def predict(self, model_data: dict, stat: str) -> Optional[dict]:
        if not model_data:
            return None
        models = model_data['models']
        last_X = model_data['last_X']
        last_X_scaled = model_data['last_X_scaled']
        model_errors = model_data.get('model_errors', {})

        predictions = {}
        for name, model in models.items():
            try:
                if name in ['xgb', 'lgb', 'lgb_median', 'lgb_low', 'lgb_high']:
                    pred = model.predict(last_X_scaled.reshape(1, -1))[0]
                else:
                    pred = model.predict(last_X)[0]
                predictions[name] = max(0, float(pred))
            except Exception as e:
                log.debug(f"Prediction failed for {name}: {e}")
        if not predictions:
            return None

        if model_errors and all(k in model_errors for k in predictions.keys()):
            inv_err = {k: 1.0 / (model_errors[k] + 0.5) for k in predictions}
            total_inv = sum(inv_err.values())
            weights = {k: v / total_inv for k, v in inv_err.items()}
        else:
            weights = {k: MODEL_WEIGHTS.get(k, 0.2) for k in predictions.keys()}
            total_w = sum(weights.values())
            weights = {k: v/total_w for k,v in weights.items()}

        ensemble = sum(p * weights[m] for m, p in predictions.items())
        disagreement = np.std(list(predictions.values()))
        cv_err = float(model_data['cv_error'])

        # cv_err ortalama mutlak hata (istatistik birimi). Eski (1 - cv_err) PTS gibi
        # büyük ölçeklerde negatife düşüp güveni sürekli tabana çökertiyordu.
        mag = max(abs(float(ensemble)), 0.35)
        rel_cv = min(cv_err / (mag + 0.5), 2.5)
        fit_score = max(0.0, min(1.0, 1.0 - rel_cv / 1.15))

        rel_dis = float(disagreement) / (mag + 0.35)
        disag_penalty = min(22.0, rel_dis * 52.0)

        confidence = int(min(95, max(24, fit_score * 100 - disag_penalty)))

        # v13.0: Top Feature Contributors (Insights)
        top_insights = []
        try:
            # We use XGB or LGB feature importance if available
            key_m = 'xgb' if 'xgb' in models else 'lgb'
            if key_m in models:
                imps = models[key_m].feature_importances_
                f_cols = model_data['feature_cols']
                top_idx = np.argsort(imps)[-3:][::-1]
                for idx in top_idx:
                    fname = f_cols[idx]
                    # Map technical names to user-friendly labels
                    label = fname.split('_EMA')[0].split('_ROLL')[0].split('_LAG')[0]
                    if 'DvP' in fname: label = 'Matchup Diff'
                    elif 'REST' in fname: label = 'Rest/Travel'
                    elif 'USAGE' in fname: label = 'Role/Usage'
                    elif 'VOL' in fname: label = 'Recent Form'
                    top_insights.append(label)
        except: pass

        return {
            'pred': ensemble,
            'predictions': predictions,
            'confidence': confidence,
            'disagreement': disagreement,
            'cv_error': cv_err,
            'dyn_weights': weights,
            'low_quantile': predictions.get('lgb_low', ensemble * 0.7),
            'high_quantile': predictions.get('lgb_high', ensemble * 1.3),
            'insights': top_insights[:3]
        }

def model_cleanup():
    """v13.1: 7 günden eski .joblib modellerini silerek disk dolmasını engeller."""
    try:
        if not os.path.exists('models'): return
        now = time.time()
        expiry = 7 * 24 * 3600
        count = 0
        for f in os.listdir('models'):
            if f.endswith('.joblib'):
                path = os.path.join('models', f)
                if now - os.path.getmtime(path) > expiry:
                    os.remove(path)
                    count += 1
        if count > 0:
            log.info(f"Model Maintenance: {count} stale models pruned from disk")
    except Exception as e:
        log.warning(f"Model cleanup failed: {e}")

# v13.1: Initial cleanup on startup
# threading.Thread(target=model_cleanup, daemon=True).start()

ml_pipe = MLPipeline()
