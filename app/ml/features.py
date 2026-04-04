import pandas as pd
import numpy as np
from datetime import timedelta

def create_advanced_features(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 3:
        return df
    df = df.sort_values('GAME_DATE').reset_index(drop=True)
    df['GAME_DATE'] = pd.to_datetime(df['GAME_DATE'])
    df['REST_DAYS'] = df['GAME_DATE'].diff().dt.days.fillna(7)
    df['OPP'] = df['MATCHUP'].apply(lambda x: x.split()[-1])
    df['HOME'] = df['MATCHUP'].apply(lambda x: 1 if 'vs.' in x else 0)
    df['SEASON_PART'] = np.where(df.index >= len(df)//2, 1, 0)
    
    core_stats = ['PTS','REB','AST','STL','BLK','TOV','MIN','FGA','FGM','FTA','FTM']
    for col in core_stats:
        if col not in df.columns:
            continue
        for span in [3, 5, 10, 20]:
            df[f'{col}_EMA_{span}'] = df[col].ewm(span=span, adjust=False).mean()
        for window in [3, 5, 10, 15]:
            if len(df) >= window:
                df[f'{col}_ROLL_{window}'] = df[col].rolling(window, min_periods=1).mean()
                df[f'{col}_ROLL_STD_{window}'] = df[col].rolling(window, min_periods=1).std().fillna(0)
                # Volatility Momentum: Is the player getting more or less volatile?
                df[f'{col}_VOL_MOM_{window}'] = df[col].rolling(window).std() / (df[col].rolling(window*2).std() + 1e-6)
        for lag in [1, 2]:
            df[f'{col}_LAG_{lag}'] = df[col].shift(lag)
            
    if 'MIN' in df.columns and 'FGA' in df.columns:
        # v13.0: Professional USG% Proxy
        # USG% = 100 * ((FGA + 0.44 * FTA + TOV) * (Team_MP / 5)) / (MP * ...)
        # We use a 36-minute normalized estimate with TOV and FTA inclusion.
        df['USAGE_RATE'] = (df['FGA'] + 0.44 * df.get('FTA', 0) + df.get('TOV', 0)) / (df['MIN'] + 1e-6) * 36
        df['TS_PCT'] = df['PTS'] / (2 * (df['FGA'] + 0.44 * df.get('FTA', 0)) + 1e-6)
        df['USAGE_VOL_5'] = df['USAGE_RATE'].rolling(5).std().fillna(0)
        
    df['B2B'] = (df['REST_DAYS'] <= 1).astype(int)
    
    games_last_7 = []
    for i, row in df.iterrows():
        curr_date = row['GAME_DATE']
        count = df[(df['GAME_DATE'] >= curr_date - timedelta(days=7)) &
                   (df['GAME_DATE'] < curr_date)].shape[0]
        games_last_7.append(count)
    df['GAMES_LAST_7'] = games_last_7
    df['REST_HOME_INT'] = df['REST_DAYS'] * df['HOME']
    
    return df.fillna(0)
