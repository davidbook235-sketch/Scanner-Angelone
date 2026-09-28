"""
Live candles par indicators calculate karke signals generate karta hai.
Har 5-minute candle close pe scanner run hota hai.
"""
import pandas as pd
from datetime import datetime, time as dtime
import pytz
from indicators import calculate_indicators, generate_signals

IST = pytz.timezone('Asia/Kolkata')
MARKET_OPEN  = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)


def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def scan_live(data_fetcher, symbols: list, min_score: int = 3) -> pd.DataFrame:
    results = []
    for sym in symbols:
        df = data_fetcher.get_candles(sym)
        if df is None or len(df) < 50:
            continue
        df = calculate_indicators(df)
        df = generate_signals(df)
        latest = df.iloc[-1]
        if latest['Score'] >= min_score:
            results.append({
                'Symbol':   sym,
                'Signal':   latest['Signal'],
                'Score':    int(latest['Score']),
                'Entry':    round(latest['Entry'], 2),
                'StopLoss': round(latest['StopLoss'], 2),
                'Target':   round(latest['Target'], 2),
                'RSI':      round(latest['RSI'], 1),
                'Volume':   int(latest['Volume']),
                'Time':     datetime.now(IST).strftime('%H:%M:%S'),
                'Reasons':  _build_reasons(latest)
            })
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    df = df.sort_values(['Score', 'Symbol'], ascending=[False, True])
    return df.reset_index(drop=True)


def _build_reasons(row) -> str:
    r = []
    if row['EMA20'] > row['EMA50']:        r.append('EMA20>EMA50')
    if row['RSI'] > 55:                     r.append('RSI>55')
    if row['MACD'] > row['MACD_Signal']:    r.append('MACD bullish')
    if row['Close'] > row['High20']:        r.append('20D breakout')
    if row['Volume'] > 1.5 * row['Vol_SMA20']: r.append('Volume spike')
    return ', '.join(r)


def detect_new_signals(prev_df: pd.DataFrame, curr_df: pd.DataFrame) -> pd.DataFrame:
    if prev_df.empty:
        return curr_df[curr_df['Signal'] == 'BUY']
    prev_buy = set(prev_df[prev_df['Signal'] == 'BUY']['Symbol'])
    return curr_df[
        (curr_df['Signal'] == 'BUY') &
        (~curr_df['Symbol'].isin(prev_buy))
  ]
