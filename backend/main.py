from flask import Flask
import yfinance as yf
import pandas as pd
import time
import threading
import schedule
import os

from telegram_bot import send_telegram

app = Flask(__name__)

# =========================
# SETTINGS
# =========================
SYMBOLS = ["EURUSD=X", "GBPUSD=X", "XAUUSD=X"]
last_signal = {}

# =========================
# ROUTE
# =========================
@app.route("/")
def home():
    return "Bot is running ✅"


# =========================
# DATA FETCH (STABLE)
# =========================
def get_data(symbol, interval="1m", period="1d"):
    for _ in range(3):
        try:
            df = yf.download(symbol, interval=interval, period=period, progress=False)
            df.dropna(inplace=True)

            if not df.empty:
                return df
        except:
            time.sleep(1)

    return pd.DataFrame()


# =========================
# SMART TIME FILTER
# =========================
def is_kill_zone():
    hour = pd.Timestamp.utcnow().hour
    return (6 <= hour <= 10) or (12 <= hour <= 16)


# =========================
# TREND (HTF CONFIRMATION)
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
# STRUCTURE + LIQUIDITY
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
# SNIPER ENTRY (STRICT)
# =========================
def sniper_entry(df):
    c = df.iloc[-1]
    body = abs(c["Close"] - c["Open"])
    wick = c["High"] - c["Low"]

    if wick == 0:
        return False

    # stricter precision
    return (body / wick) > 0.7


# =========================
# VOLATILITY FILTER (NEW)
# =========================
def volatility_filter(df):
    df["range"] = df["High"] - df["Low"]
    avg = df["range"].rolling(10).mean().iloc[-1]
    current = df["range"].iloc[-1]

    return current > avg  # only trade when volatility is good


# =========================
# SIGNAL ENGINE (BOOSTED)
# =========================
def generate_signal(symbol):
    df_1m = get_data(symbol, "1m")
    df_5m = get_data(symbol, "5m")

    if df_1m.empty or df_5m.empty:
        return None

    if len(df_1m) < 50 or len(df_5m) < 50:
        return None

    trend = detect_trend(df_5m)
    bos = break_of_structure(df_1m)
    sweep = liquidity_sweep(df_1m)
    ob = order_block(df_1m)
    sniper = sniper_entry(df_1m)
    vol = volatility_filter(df_1m)

    # ===== ACCURACY BOOST LOGIC =====
    score = 0
    confirmations = 0

    signals = [bos, sweep, ob]

    for s in signals:
        if s == trend:
            score += 2
            confirmations += 1

    if sniper:
        score += 2

    if vol:
        score += 2

    if not is_kill_zone():
        score -= 2

    # 🔥 STRICT FILTER
    if confirmations < 2:
        return None

    if score < 6:
        return None

    # choose best direction
    direction = trend

    price = df_1m["Close"].iloc[-1]
    strength = "🔥 STRONG" if score >= 8 else "⚡ MEDIUM"

    return f"""
🚀 SIGNAL ALERT

Pair: {symbol}
Type: {direction}
Strength: {strength}
Entry: {price}

📊 Confirmations: {confirmations}/3
⚡ Volatility: {"High" if vol else "Low"}
⏰ Kill Zone: {"YES" if is_kill_zone() else "NO"}
"""


# =========================
# SCANNER (SAFE)
# =========================
def scan_market():
    global last_signal
    print("Scanning market...")

    for symbol in SYMBOLS:
        try:
            signal = generate_signal(symbol)

            if signal and last_signal.get(symbol) != signal:
                last_signal[symbol] = signal
                print(signal)
                send_telegram(signal)

            time.sleep(2)  # API protection

        except Exception as e:
            print(f"Error scanning {symbol}: {e}")


# =========================
# LOOP
# =========================
def run_bot():
    schedule.every(1).minutes.do(scan_market)

    while True:
        schedule.run_pending()
        time.sleep(1)


# =========================
# START SAFE
# =========================
bot_started = False

def start_background():
    global bot_started
    if not bot_started:
        bot_started = True
        print("Starting bot thread...")

        try:
            send_telegram("🤖 Bot is LIVE with Accuracy Boost!")
        except:
            print("Telegram failed")

        threading.Thread(target=run_bot, daemon=True).start()


if os.environ.get("RUN_MAIN") == "true" or not app.debug:
    start_background()
