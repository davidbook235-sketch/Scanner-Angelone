"""
Angel One SmartAPI login module.
TOTP auto-generate karta hai — roz manually token nahi banana padta.
"""
import pyotp
from SmartApi import SmartConnect
import pandas as pd
import requests
import json
import os


class AngelAuth:
    def __init__(self, api_key: str, client_id: str,
                 password: str, totp_secret: str):
        self.api_key = api_key
        self.client_id = client_id
        self.password = password
        self.totp_secret = totp_secret
        self.smart_api = None
        self.auth_token = None
        self.feed_token = None

    def login(self) -> bool:
        """
        TOTP generate karke session create karta hai.
        Success pe True return karta hai.
        """
        try:
            self.smart_api = SmartConnect(api_key=self.api_key)

            # TOTP auto-generate (30-second window)
            totp = pyotp.TOTP(self.totp_secret).now()

            # Session generate
            data = self.smart_api.generateSession(
                self.client_id, self.password, totp
            )

            if not data.get('status'):
                print(f"❌ Login failed: {data.get('message')}")
                return False

            self.auth_token = data['data']['jwtToken']
            self.feed_token = self.smart_api.getfeedToken()

            print(f"✅ Login successful as {self.client_id}")
            print(f"   Auth token: {self.auth_token[:20]}...")
            print(f"   Feed token: {self.feed_token[:20]}...")
            return True

        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    def get_instrument_master(self) -> pd.DataFrame:
        """
        NSE instruments ka master data fetch karta hai.
        Symbol → symboltoken mapping ke liye.
        """
        url = "https://margincalculator.angelone.in/OpenAPI_File/files/OpenAPIScripMaster.json"
        try:
            resp = requests.get(url, timeout=30)
            data = resp.json()
            df = pd.DataFrame(data)
            # Sirf NSE equity filter
            df = df[(df['exch_seg'] == 'NSE') & (df['symbol'].str.endswith('-EQ'))]
            df['tradingsymbol'] = df['symbol'].str.replace('-EQ', '', regex=False)
            df = df[['tradingsymbol', 'token', 'symbol']].drop_duplicates('tradingsymbol')
            print(f"✅ Instrument master loaded: {len(df)} NSE symbols")
            return df
        except Exception as e:
            print(f"❌ Instrument master fetch failed: {e}")
            return pd.DataFrame()

    def get_historical_candles(self, symbol_token: str, interval: str = "FIVE_MINUTE",
                               days: int = 30) -> pd.DataFrame:
        """
        Historical OHLCV candles fetch karta hai.
        interval: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE,
                  THIRTY_MINUTE, ONE_HOUR, ONE_DAY
        """
        from datetime import datetime, timedelta
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        params = {
            "exchange": "NSE",
            "symboltoken": symbol_token,
            "interval": interval,
            "fromdate": from_date.strftime("%Y-%m-%d 09:15"),
            "todate": to_date.strftime("%Y-%m-%d 15:30"),
        }

        try:
            resp = self.smart_api.getCandleData(params)
            if not resp.get('status') or not resp.get('data'):
                return None
            df = pd.DataFrame(
                resp['data'],
                columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            )
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date').reset_index(drop=True)
            return df
        except Exception as e:
            print(f"❌ Candle fetch failed for {symbol_token}: {e}")
            return None
