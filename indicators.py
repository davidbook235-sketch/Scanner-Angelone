import pandas as pd
import numpy as np

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close = df['Close']
    high = df['High']
    vol = df['Volume']

    # EMA
    df['EMA20'] = close.ewm(span=20, adjust=False).mean()
    df['EMA50'] = close.ewm(span=50, adjust=False).mean()

    # RSI (14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # 20-day High (breakout)
    df['High20'] = high.rolling(20).max()

    # Volume Spike (1.5x avg)
    df['Vol_SMA20'] = vol.rolling(20).mean()

    return df

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    df['Score'] = (
        (df['EMA20'] > df['EMA50']).astype(int) +
        (df['RSI'] > 55).astype(int) +
        (df['MACD'] > df['MACD_Signal']).astype(int) +
        (df['Close'] > df['High20'].shift(1)).astype(int) +
        (df['Volume'] > 1.5 * df['Vol_SMA20']).astype(int)
    )
    df['Signal'] = 'NONE'
    df.loc[df['Score'] >= 4, 'Signal'] = 'BUY'
    df.loc[df['Score'] == 3, 'Signal'] = 'WATCH'

    df['Entry'] = df['Close']
    df['StopLoss'] = df['Close'] * 0.965
    df['Target'] = df['Close'] * 1.07
    return df
