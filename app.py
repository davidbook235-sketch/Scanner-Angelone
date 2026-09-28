import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
from datetime import datetime
import pytz

from angel_auth import AngelAuth
from angel_live_fetcher import AngelLiveFetcher
from live_scanner import scan_live, is_market_open, detect_new_signals
from scanner import run_scanner, backtest_symbol
from data_fetcher import fetch_stock_data
from indicators import calculate_indicators, generate_signals
from telegram_bot import (
    send_telegram_message, format_signal_message,
    format_backtest_message, test_connection
)
import plotly.graph_objects as go

IST = pytz.timezone('Asia/Kolkata')

st.set_page_config(
    page_title="Nifty 250 Live Scanner",
    page_icon="📡",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.main .block-container { padding: 0.5rem; max-width: 100% !important; }
div[data-testid="stMetric"] { background:#1e1e1e; padding:10px;
    border-radius:10px; margin-bottom:8px; }
[data-testid="stHeader"] { display:none; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title("📡 Nifty 250 Live")
    page = st.radio("Navigate", [
        "📡 Live Scanner",
        "🔍 EOD Scanner",
        "📊 Backtest",
        "📈 Stock Detail",
        "🤖 Settings"
    ])

def get_creds():
    return {
        'angel_api_key': st.session_state.get('angel_api_key', ''),
        'angel_client_id': st.session_state.get('angel_client_id', ''),
        'angel_password': st.session_state.get('angel_password', ''),
        'angel_totp': st.session_state.get('angel_totp', ''),
        'tg_token': st.session_state.get('tg_token', ''),
        'tg_chat': st.session_state.get('tg_chat', '')
    }

symbols = pd.read_csv('nifty250_symbols.csv')['Symbol'].dropna().tolist()


# ═══════════════════════════════════════════
# 📡 LIVE SCANNER
# ═══════════════════════════════════════════
if page == "📡 Live Scanner":
    st.header("📡 Live Market Scanner")

    creds = get_creds()
    if not creds['angel_api_key']:
        st.warning("⚠️ Angel One credentials missing. Settings page pe set karein.")
        st.stop()

    refresh_interval = st.selectbox("Refresh (sec)", [30, 60, 120, 300], index=1)
    auto_refresh = st.toggle("🔄 Auto-refresh", value=True)
    if auto_refresh:
        st_autorefresh(interval=refresh_interval * 1000, key="live_refresh")

    if is_market_open():
        st.success(f"🟢 Market OPEN — {datetime.now(IST).strftime('%H:%M:%S IST')}")
    else:
        st.warning(f"🔴 Market CLOSED — {datetime.now(IST).strftime('%H:%M:%S IST')}")

    # Initialize Angel One session
    if 'angel_auth' not in st.session_state:
        with st.spinner("Logging into Angel One..."):
            auth = AngelAuth(
                api_key=creds['angel_api_key'],
                client_id=creds['angel_client_id'],
                password=creds['angel_password'],
                totp_secret=creds['angel_totp']
            )
            if not auth.login():
                st.error("❌ Login failed. Credentials check karein.")
                st.stop()

            # Instrument master load
            inst_df = auth.get_instrument_master()
            token_map = dict(zip(inst_df['tradingsymbol'], inst_df['token']))

            # Live fetcher initialize
            fetcher = AngelLiveFetcher(
                auth.auth_token, creds['angel_api_key'],
                creds['angel_client_id'], auth.feed_token
            )
            fetcher.load_historical(auth, symbols[:100], token_map, days=30)
            fetcher.start_streaming()

            st.session_state['angel_auth'] = auth
            st.session_state['fetcher'] = fetcher
            st.session_state['prev_scan'] = pd.DataFrame()

    fetcher = st.session_state['fetcher']

    # Scan
    scan_df = scan_live(fetcher, symbols[:100], min_score=3)
    st.session_state['live_scan'] = scan_df

    # New signals → Telegram
    prev = st.session_state.get('prev_scan', pd.DataFrame())
    new_signals = detect_new_signals(prev, scan_df)
    if not new_signals.empty and creds['tg_token'] and creds['tg_chat']:
        msg = format_signal_message(new_signals, title="🚨 LIVE ALERT — New BUY")
        send_telegram_message(creds['tg_token'], creds['tg_chat'], msg)
        st.toast(f"📩 {len(new_signals)} new signals Telegram pe!", icon="🚨")
    st.session_state['prev_scan'] = scan_df

    if not scan_df.empty:
        st.success(f"✅ {len(scan_df)} signals")
        for _, row in scan_df.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([2, 1])
                c1.markdown(f"**{row['Symbol']}**")
                c2.markdown(f"**{row['Signal']}** · {row['Score']}")
                m1, m2, m3 = st.columns(3)
                m1.metric("Entry", row['Entry'])
                m2.metric("SL", row['StopLoss'])
                m3.metric("Target", row['Target'])
                st.caption(f"🕐 {row['Time']} | RSI {row['RSI']} | {row['Reasons']}")
    else:
        st.info("Koi signal nahi. Agla refresh wait karein...")


# ═══════════════════════════════════════════
# 🔍 EOD SCANNER (Same as before)
# ═══════════════════════════════════════════
elif page == "🔍 EOD Scanner":
    st.header("🔍 End-of-Day Scanner")
    if st.button("🚀 Run EOD Scan", use_container_width=True):
        with st.spinner("Scanning..."):
            scan_df = run_scanner(symbols)
            st.session_state['eod_scan'] = scan_df
    if 'eod_scan' in st.session_state and not st.session_state['eod_scan'].empty:
        df = st.session_state['eod_scan']
        st.success(f"✅ {len(df)} signals")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("📥 Download", df.to_csv(index=False),
                          file_name="eod_scan.csv", use_container_width=True)


# ═══════════════════════════════════════════
# 📊 BACKTEST (Same as before)
# ═══════════════════════════════════════════
elif page == "📊 Backtest":
    st.header("📊 Backtest")
    period = st.selectbox("Period", ["6mo", "1y", "2y"], index=1)
    if st.button("▶️ Run Backtest", use_container_width=True):
        all_stats = []
        progress = st.progress(0)
        for i, sym in enumerate(symbols[:50]):
            df = fetch_stock_data(sym, period)
            if df is None or len(df) < 100: continue
            df = calculate_indicators(df); df = generate_signals(df)
            stats = backtest_symbol(df)
            if stats:
                stats['Symbol'] = sym; all_stats.append(stats)
            progress.progress((i+1)/50)
        if all_stats:
            bt = pd.DataFrame(all_stats).sort_values('Total_PnL_₹', ascending=False)
            st.session_state['bt_df'] = bt
    if 'bt_df' in st.session_state:
        bt = st.session_state['bt_df']
        c1, c2, c3 = st.columns(3)
        c1.metric("Trades", int(bt['Total_Trades'].sum()))
        c2.metric("Win Rate", f"{bt['Win_Rate_%'].mean():.1f}%")
        c3.metric("P&L", f"₹{bt['Total_PnL_₹'].sum():,.0f}")
        st.dataframe(bt, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════
# 📈 STOCK DETAIL (Same as before)
# ═══════════════════════════════════════════
elif page == "📈 Stock Detail":
    st.header("📈 Stock Analysis")
    symbol = st.selectbox("Stock", symbols)
    use_live = st.toggle("📡 Live chart (5-min)", value=False)

    if st.button("Load Chart", use_container_width=True):
        if use_live and 'fetcher' in st.session_state:
            df = st.session_state['fetcher'].get_candles(symbol)
        else:
            df = fetch_stock_data(symbol, "6mo")

        if df is not None:
            df = calculate_indicators(df); df = generate_signals(df)
            fig = go.Figure()
            x_axis = df['Date'] if 'Date' in df.columns else df.index
            fig.add_trace(go.Candlestick(x=x_axis, open=df['Open'],
                high=df['High'], low=df['Low'], close=df['Close'], name="Price"))
            fig.add_trace(go.Scatter(x=x_axis, y=df['EMA20'], name="EMA20",
                line=dict(color='orange')))
            fig.add_trace(go.Scatter(x=x_axis, y=df['EMA50'], name="EMA50",
                line=dict(color='blue')))
            fig.update_layout(height=400, margin=dict(l=0,r=0,t=0,b=0),
                            xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            latest = df.iloc[-1]
            c1, c2, c3 = st.columns(3)
            c1.metric("RSI", f"{latest['RSI']:.1f}")
            c2.metric("Signal", latest['Signal'])
            c3.metric("Score", int(latest['Score']))


# ═══════════════════════════════════════════
# 🤖 SETTINGS (Angel One + Telegram)
# ═══════════════════════════════════════════
elif page == "🤖 Settings":
    st.header("🔑 API Settings")

    st.subheader("📡 Angel One SmartAPI")
    st.caption("smartapi.angelone.in se API Key aur TOTP Secret lein")
    api_key = st.text_input("API Key", type="password",
        value=st.session_state.get('angel_api_key',''))
    client_id = st.text_input("Client ID",
        value=st.session_state.get('angel_client_id',''))
    password = st.text_input("Password/MPIN", type="password",
        value=st.session_state.get('angel_password',''))
    totp_secret = st.text_input("TOTP Secret", type="password",
        value=st.session_state.get('angel_totp',''))

    st.divider()
    st.subheader("🤖 Telegram")
    tg_token = st.text_input("Bot Token", type="password",
        value=st.session_state.get('tg_token',''))
    tg_chat = st.text_input("Chat ID",
        value=st.session_state.get('tg_chat',''))

    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Save", use_container_width=True):
            st.session_state['angel_api_key'] = api_key
            st.session_state['angel_client_id'] = client_id
            st.session_state['angel_password'] = password
            st.session_state['angel_totp'] = totp_secret
            st.session_state['tg_token'] = tg_token
            st.session_state['tg_chat'] = tg_chat
            st.success("Saved ✅")
    with c2:
        if st.button("🧪 Test Login", use_container_width=True):
            test_auth = AngelAuth(api_key, client_id, password, totp_secret)
            if test_auth.login():
                st.success("✅ Angel One login OK!")
            else:
                st.error("❌ Login failed")

    st.divider()
    st.caption("🔒 Streamlit Cloud pe Secrets mein daalein")
    st.code("""
# .streamlit/secrets.toml
ANGEL_API_KEY = "your_api_key"
ANGEL_CLIENT_ID = "A123456"
ANGEL_PASSWORD = "1234"
ANGEL_TOTP_SECRET = "JBSWY3DPEHPK3PXP"
TELEGRAM_BOT_TOKEN = "7123456789:AAH..."
TELEGRAM_CHAT_ID = "123456789"
    """, language="toml")
