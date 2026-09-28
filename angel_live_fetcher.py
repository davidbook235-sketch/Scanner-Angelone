"""
Angel One SmartWebSocketV2 se real-time data fetch karta hai.
5-minute candles build karke indicators ke liye ready karta hai.
"""
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from datetime import datetime
import pandas as pd
import threading
import pytz

IST = pytz.timezone('Asia/Kolkata')


class AngelLiveFetcher:
    def __init__(self, auth_token: str, api_key: str,
                 client_id: str, feed_token: str):
        self.auth_token = auth_token
        self.api_key = api_key
        self.client_id = client_id
        self.feed_token = feed_token

        self.live_candles = {}      # {symbol: DataFrame}
        self.symbol_tokens = {}     # {symbol: token}
        self.token_to_symbol = {}   # {token: symbol}
        self.lock = threading.Lock()
        self.sws = None

    def load_historical(self, auth: 'AngelAuth', symbols: list,
                        token_map: dict, days: int = 30):
        """
        Initial 5-min candles load karta hai (REST se).
        token_map: {symbol: symboltoken}
        """
        for sym in symbols:
            token = token_map.get(sym)
            if not token:
                continue
            self.symbol_tokens[sym] = token
            self.token_to_symbol[token] = sym

            df = auth.get_historical_candles(token, "FIVE_MINUTE", days)
            if df is not None and len(df) > 50:
                with self.lock:
                    self.live_candles[sym] = df

        print(f"✅ Historical loaded for {len(self.live_candles)} symbols")

    def start_streaming(self, on_tick_callback=None):
        """
        SmartWebSocketV2 connect karke live ticks receive karta hai.
        """
        # Token list prepare karein (exchangeType 1 = NSE)
        token_list = [{
            "exchangeType": 1,
            "tokens": list(self.symbol_tokens.values())
        }]

        # WebSocket initialize
        self.sws = SmartWebSocketV2(
            self.auth_token, self.api_key,
            self.client_id, self.feed_token,
            max_retry_attempt=3,       # Auto-reconnect
            retry_strategy=1,          # Exponential backoff
            retry_delay=5,             # 5 sec initial delay
            retry_multiplier=2         # Double every retry
        )

        def on_data(wsapp, message):
            """Har tick pe candle update karein."""
            try:
                token = str(message.get('token', ''))
                ltp = message.get('last_traded_price', 0) / 100  # paise → rupees
                volume = message.get('volume_trade_for_the_day', 0)

                sym = self.token_to_symbol.get(token)
                if not sym or ltp <= 0:
                    return

                self._update_candle(sym, ltp, volume)

                if on_tick_callback:
                    on_tick_callback(sym, {'ltp': ltp, 'volume': volume})
            except Exception as e:
                print(f"⚠️ Tick processing error: {e}")

        def on_open(wsapp):
            print("🔌 WebSocket connected")
            self.sws.subscribe("live_feed", 1, token_list)

        def on_error(wsapp, error):
            print(f"⚠️ WebSocket error: {error}")

        def on_close(wsapp):
            print("🔌 WebSocket closed")

        def on_control_message(wsapp, message):
            if isinstance(message, dict) and 'error' in message:
                print(f"⚠️ Control: {message}")

        # Callbacks assign karein
        self.sws.on_open = on_open
        self.sws.on_data = on_data
        self.sws.on_error = on_error
        self.sws.on_close = on_close
        self.sws.on_control_message = on_control_message

        # Background thread mein start
        t = threading.Thread(target=self.sws.connect, daemon=True)
        t.start()
        print("🚀 Live streaming started")

    def stop_streaming(self):
        if self.sws:
            try:
                self.sws.close_connection()
            except:
                pass

    def _update_candle(self, symbol: str, ltp: float, volume: int):
        """Tick se 5-min candle build/update karta hai."""
        now = datetime.now(IST)
        bucket_min = (now.minute // 5) * 5
        bucket_time = now.replace(minute=bucket_min, second=0, microsecond=0)

        with self.lock:
            df = self.live_candles.get(symbol)
            if df is None or df.empty:
                return

            last_time = df.iloc[-1]['Date']
            if last_time.tzinfo is None:
                last_time = last_time.tz_localize(IST)

            if last_time >= bucket_time:
                idx = df.index[-1]
                df.at[idx, 'High'] = max(df.at[idx, 'High'], ltp)
                df.at[idx, 'Low'] = min(df.at[idx, 'Low'], ltp)
                df.at[idx, 'Close'] = ltp
                df.at[idx, 'Volume'] = volume
            else:
                new_row = {
                    'Date': bucket_time,
                    'Open': ltp, 'High': ltp,
                    'Low': ltp, 'Close': ltp, 'Volume': volume
                }
                self.live_candles[symbol] = pd.concat(
                    [df, pd.DataFrame([new_row])], ignore_index=True
                )

    def get_candles(self, symbol: str) -> pd.DataFrame:
        with self.lock:
            df = self.live_candles.get(symbol)
            return df.copy() if df is not None else None
