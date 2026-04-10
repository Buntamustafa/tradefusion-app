from flask import Flask
import yfinance as yf
import pandas as pd
import time
import threading
import schedule
import os
import logging

from telegram_bot import send_telegram

app = Flask(__name__)

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# =========================
# SETTINGS
# =========================
SYMBOLS = ["EURUSD=X", "GBPUSD=X", "XAUUSD=X"]
last_signal = {}
last_sent_time = {}

# =========================
# ROUTE (UPTIMEROBOT)
# =========================
@app.route("/")
def home():
    print("Ping received")
    return "Bot is running ✅"


# =========================
# DATA FETCH (RETRY)
# =========================
def get_data(symbol, interval="1m", period="1d"):
    for attempt in range(5):
        try:
            df = yf.download(symbol, interval=interval, period=period, progress=False)

            if df is not None and not df.empty:
                df.dropna(inplace=True)
                return df

        except Exception as e:
            logging.warning(f"{symbol} retry {attempt+1} failed: {e}")

        time.sleep(2)

    logging.error(f"{symbol} FAILED after retries")
    return pd.DataFrame()


# =========================
# TIME FILTER
# =========================
def is_kill_zone():
    hour = pd.Timestamp.utcnow().hour
    return (6 <= hour <= 10) or (12 <= hour <= 16)


def is_news_session():
    hour = pd.Timestamp.utcnow().hour
    return (7 <= hour <= 10) or (13 <= hour <= 16)


# =========================
# RSI
# =========================
def calculate_rsi(df, period=14):
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def rsi_filter(df, direction):
    df["rsi"] = calculate_rsi(df)
    rsi = df["rsi"].iloc[-1]

    if direction == "BUY" and rsi < 35:
        return True
    if direction == "SELL" and rsi > 65:
        return True

    return False


# =========================
# TREND
# =========================
def detect_trend(df):
    df["ema50"] = df["Close"].ewm(span=50).mean()
    df["ema200"] = df["Close"].ewm(span=200).mean()

    if df["ema50"].iloc[-1] > df["ema200"].iloc[-1]:
        return "BUY"
    elif df["ema50"].iloc[-1] < df["ema200"].iloc[-1]:
        return "SELL"
    return None


# =========================
# STRUCTURE
# =========================
def break_of_structure(df):
    high = df["High"].rolling(10).max().iloc[-2]
    low = df["Low"].rolling(10).min().iloc[-2]

    if df["Close"].iloc[-1] > high:
        return "BUY"
    elif df["Close"].iloc[-1] < low:
        return "SELL"
    return None


def liquidity_sweep(df):
    if df["High"].iloc[-1] > df["High"].iloc[-2]:
        return "SELL"
    elif df["Low"].iloc[-1] < df["Low"].iloc[-2]:
        return "BUY"
    return None


def order_block(df):
    last = df.iloc[-2]
    curr = df.iloc[-1]

    if last["Close"] < last["Open"] and curr["Close"] > curr["Open"]:
        return "BUY"
    elif last["Close"] > last["Open"] and curr["Close"] < curr["Open"]:
        return "SELL"
    return None


# =========================
# ENTRY FILTERS
# =========================
def sniper_entry(df):
    c = df.iloc[-1]
    body = abs(c["Close"] - c["Open"])
    wick = c["High"] - c["Low"]

    if wick == 0:
        return False

    return (body / wick) > 0.7


def volatility_filter(df):
    df["range"] = df["High"] - df["Low"]
    avg = df["range"].rolling(10).mean().iloc[-1]
    current = df["range"].iloc[-1]

    return current > avg


def is_scalp(df):
    df["range"] = df["High"] - df["Low"]
    current = df["range"].iloc[-1]
    avg = df["range"].rolling(20).mean().iloc[-1]

    return current > avg * 1.5


# =========================
# TP / SL
# =========================
def calculate_tp_sl(df, direction):
    atr = (df["High"] - df["Low"]).rolling(14).mean().iloc[-1]
    price = df["Close"].iloc[-1]

    if direction == "BUY":
        sl = price - atr
        tp = price + (atr * 2)
    else:
        sl = price + atr
        tp = price - (atr * 2)

    return round(tp, 5), round(sl, 5)


# =========================
# ANTI OVERTRADING
# =========================
def can_send(symbol):
    now = time.time()

    if symbol not in last_sent_time:
        last_sent_time[symbol] = now
        return True

    if now - last_sent_time[symbol] > 600:
        last_sent_time[symbol] = now
        return True

    return False


# =========================
# SIGNAL ENGINE
# =========================
def generate_signal(symbol):
    df_1m = get_data(symbol, "1m")
    df_5m = get_data(symbol, "5m")
    df_15m = get_data(symbol, "15m")
    df_1h = get_data(symbol, "1h")

    if any(df.empty for df in [df_1m, df_5m, df_15m, df_1h]):
        return None

    trend_5m = detect_trend(df_5m)
    trend_15m = detect_trend(df_15m)
    trend_1h = detect_trend(df_1h)

    if not (trend_5m == trend_15m == trend_1h):
        return None

    direction = trend_5m

    bos = break_of_structure(df_1m)
    sweep = liquidity_sweep(df_1m)
    ob = order_block(df_1m)

    sniper = sniper_entry(df_1m)
    vol = volatility_filter(df_1m)
    rsi_ok = rsi_filter(df_1m, direction)

    score = 0
    confirmations = 0

    for s in [bos, sweep, ob]:
        if s == direction:
            confirmations += 1
            score += 2

    if sniper:
        score += 2
    if vol:
        score += 2
    if rsi_ok:
        score += 2
    if is_kill_zone():
        score += 1
    if is_news_session():
        score += 2

    signal_type = None

    if confirmations >= 2:
        if score >= 10:
            signal_type = "🔥 STRICT"
        elif score >= 7:
            signal_type = "⚡ MEDIUM"

    scalp_trade = is_scalp(df_1m) and is_news_session()

    if not signal_type and not scalp_trade:
        return None

    price = df_1m["Close"].iloc[-1]
    tp, sl = calculate_tp_sl(df_1m, direction)

    return f"""
🚀 SIGNAL ALERT

Pair: {symbol}
Type: {direction}
Signal: {signal_type if signal_type else "⚡ SCALP"}

Entry: {price}
TP: {tp}
SL: {sl}

⚡ Scalp: {"YES" if scalp_trade else "NO"}
📰 News Mode: {"YES" if is_news_session() else "NO"}
📊 Confirmations: {confirmations}/3
📈 RSI OK: {"YES" if rsi_ok else "NO"}
"""


# =========================
# SCANNER
# =========================
def scan_market():
    logging.info("Scanning market...")

    for symbol in SYMBOLS:
        try:
            signal = generate_signal(symbol)

            if signal and last_signal.get(symbol) != signal and can_send(symbol):
                last_signal[symbol] = signal
                logging.info(signal)
                send_telegram(signal)

            time.sleep(2)

        except Exception as e:
            logging.error(f"{symbol} error: {e}")


# =========================
# LOOP
# =========================
def run_bot():
    schedule.every(1).minutes.do(scan_market)

    while True:
        schedule.run_pending()
        time.sleep(1)


# =========================
# START (FIXED NO SPAM)
# =========================
def start_background():
    if os.environ.get("BOT_STARTED") == "1":
        return

    os.environ["BOT_STARTED"] = "1"

    logging.info("Starting bot...")

    try:
        send_telegram("🤖 Bot is LIVE (Smart Mode)")
    except:
        logging.warning("Telegram failed")

    threading.Thread(target=run_bot, daemon=True).start()


if os.environ.get("RUN_MAIN") == "true" or not app.debug:
    start_background()
