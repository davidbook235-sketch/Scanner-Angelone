import pandas as pd
from data_fetcher import fetch_stock_data
from indicators import calculate_indicators, generate_signals

def run_scanner(symbols: list, period: str = "6mo"):
    results = []
    for sym in symbols:
        df = fetch_stock_data(sym, period)
        if df is None or len(df) < 50:
            continue
        df = calculate_indicators(df)
        df = generate_signals(df)
        latest = df.iloc[-1]
        if latest['Signal'] in ('BUY', 'WATCH'):
            results.append({
                'Symbol': sym,
                'Signal': latest['Signal'],
                'Score': int(latest['Score']),
                'Entry': round(latest['Entry'], 2),
                'StopLoss': round(latest['StopLoss'], 2),
                'Target': round(latest['Target'], 2),
                'RSI': round(latest['RSI'], 1)
            })
    return pd.DataFrame(results).sort_values('Score', ascending=False).reset_index(drop=True) if results else pd.DataFrame()

def backtest_symbol(df: pd.DataFrame, capital: float = 10000):
    trades = []
    in_trade = False
    entry_price = sl = target = 0
    entry_idx = 0

    for i in range(1, len(df)):
        row = df.iloc[i]
        if not in_trade and row['Signal'] == 'BUY':
            in_trade = True
            entry_price = row['Close']
            sl, target = row['StopLoss'], row['Target']
            entry_idx = i
            continue
        if in_trade:
            high, low = row['High'], row['Low']
            days = i - entry_idx
            exit_p = exit_r = None
            if high >= target: exit_p, exit_r = target, 'TARGET'
            elif low <= sl: exit_p, exit_r = sl, 'STOPLOSS'
            elif days >= 30: exit_p, exit_r = row['Close'], 'TIME'
            if exit_p:
                pnl_pct = (exit_p - entry_price) / entry_price * 100
                trades.append({
                    'PnL_%': round(pnl_pct, 2),
                    'PnL_₹': round(capital * pnl_pct / 100, 2),
                    'Exit_Reason': exit_r, 'Days': days
                })
                in_trade = False
    if not trades: return None
    tdf = pd.DataFrame(trades)
    wins, losses = tdf[tdf['PnL_%'] > 0], tdf[tdf['PnL_%'] <= 0]
    return {
        'Total_Trades': len(tdf),
        'Win_Rate_%': round(len(wins) / len(tdf) * 100, 1),
        'Total_PnL_₹': round(tdf['PnL_₹'].sum(), 2),
        'Profit_Factor': round(abs(wins['PnL_₹'].sum() / losses['PnL_₹'].sum()), 2) if len(losses) and losses['PnL_₹'].sum() != 0 else 0
          }
