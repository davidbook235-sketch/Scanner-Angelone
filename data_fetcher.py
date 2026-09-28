import yfinance as yf
import pandas as pd

def fetch_stock_data(symbol: str, period: str = "1y") -> pd.DataFrame:
    """NSE stock ka historical data fetch karta hai."""
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        df = ticker.history(period=period)
        if df.empty:
            return None
        df = df.rename(columns={
            'Open': 'Open', 'High': 'High',
            'Low': 'Low', 'Close': 'Close', 'Volume': 'Volume'
        })
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
        return df
    except Exception as e:
        print(f"❌ {symbol}: {e}")
        return None
