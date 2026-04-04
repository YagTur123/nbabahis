import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('predictor_v12.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('PredictorV12')

# ─── CONFIG ───────────────────────────────────────────────────
MAX_THREADS = 5
MIN_GAMES = 6
MIN_AVG_MIN = 10
MIN_RECENT_MIN = 8
MAX_INJURY_GAP = 30
MIN_CURR_GAMES = 3
DB = 'predictor_v12.db'

# Runtime config
RUNTIME_CONFIG = {
    'odds_api_key': os.getenv('ODDS_API_KEY', ''),
    'stake_session': os.getenv('STAKE_SESSION', ''),
    'stake_cf_clearance': os.getenv('STAKE_CF_CLEARANCE', ''),
    'default_bookmakers': ['draftkings', 'fanduel', 'betmgm', 'pinnacle', 'bet365', 'stake']
}

ODDS_API_URL = 'https://api.the-odds-api.com/v4/sports/basketball_nba'

try:
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    ADVANCED_ML = True
except ImportError as e:
    ADVANCED_ML = False
    log.warning(f"Advanced ML libs not found ({e}), using sklearn fallback")

MODEL_WEIGHTS = {
    'xgb': 0.35, 'lgb': 0.35, 'gbm': 0.20, 'rf': 0.10
} if ADVANCED_ML else {'gbm': 0.6, 'rf': 0.4}

CV_LIMITS = {
    'PTS': 0.40, 'REB': 0.50, 'AST': 0.55,
    'STL': 0.70, 'BLK': 0.75, 'TOV': 0.65, 'PF': 0.65,
    'FG3M': 0.68, 'FGM': 0.48, 'FTM': 0.65, 'FTA': 0.65,
    'FGA': 0.50, 'FG3A': 0.58,
    'PRA': 0.45, 'P+R': 0.48, 'P+A': 0.48, 'A+R': 0.55, 'S+B': 0.70,
}

FLOOR = {
    'PTS': 5.0,  'REB': 1.5,  'AST': 1.0,
    'STL': 0.2,  'BLK': 0.2,  'TOV': 0.3,  'PF': 0.5,
    'FG3M': 0.4, 'FGM': 1.2,  'FTM': 0.4,  'FTA': 0.4,
    'FGA': 3.0,  'FG3A': 0.8,
    'PRA': 7.0,  'P+R': 6.0,  'P+A': 6.0,  'A+R': 2.0,  'S+B': 0.3,
}

STAT_POSITION_WEIGHT = {
    'PTS':(1.05,1.00,1.10),'FGM':(1.05,1.00,1.10),'FGA':(1.05,1.00,1.10),
    'FG3M':(1.08,1.00,0.95),'FG3A':(1.08,1.00,0.92),'FTM':(1.00,1.00,1.05),
    'FTA':(1.00,1.00,1.05),'AST':(1.08,1.00,0.92),'REB':(0.90,1.00,1.15),
    'BLK':(0.80,1.00,1.20),'STL':(1.10,1.00,0.85),'TOV':(1.05,1.00,0.95),
    'PF':(0.90,1.00,1.10),'PRA':(1.00,1.00,1.05),'P+R':(0.98,1.00,1.08),
    'P+A':(1.05,1.00,0.95),'A+R':(0.95,1.00,1.05),'S+B':(1.00,1.00,1.05),
}

STAT_TO_ODDS_MARKET = {
    'PTS': 'player_points', 'REB': 'player_rebounds', 'AST': 'player_assists',
    'STL': 'player_steals', 'BLK': 'player_blocks',
    'P+R': 'player_points_rebounds', 'P+A': 'player_points_assists',
    'A+R': 'player_rebounds_assists', 'PRA': 'player_points_rebounds_assists',
    'FG3M': 'player_threes', 'S+B': 'player_blocks_steals'
}

ODDS_BOOKMAKER_NAMES = {
    'draftkings': 'DK', 'fanduel': 'FD', 'betmgm': 'MGM',
    'pinnacle': 'PIN', 'bet365': 'B365', 'williamhill_us': 'Caesars',
    'bovada': 'Bov', 'betus': 'BetUS', 'stake': 'Stake'
}

ALL_STATS = ['PTS','REB','AST','STL','BLK','TOV','PF',
             'FG3M','FGM','FTM','FTA','FGA','FG3A',
             'PRA','P+R','P+A','A+R','S+B']
