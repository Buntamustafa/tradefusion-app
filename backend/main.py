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

# =========================
# ROUTE (RENDER NEEDS THIS)
# =========================
@app.route("/")
def home():
    return "Bot is running ✅"


# =========================
# HELPERS
# =========================
def get_data(symbol, interval="1m", period="1d"):
    df = yf.download(symbol, interval=interval, period=period, progress=False)
    df.dropna(inplace=True)
    return df


def is_kill_zone():
    hour = pd.Timestamp.utcnow().hour
    return (6 <= hour <= 10) or (12 <= hour <= 16)


def detect_trend(df):
    df["ema50"] = df["Close"].ewm(span=50).mean()
    df["ema200"] = df["Close"].ewm(span=200).mean()

    if df["ema50"].iloc[-1] > df["ema200"].iloc[-1]:
        return "BUY"
    elif df["ema50"].iloc[-1] < df["ema200"].iloc[-1]:
        return "SELL"
    return None


def break_of_structure(df):
    recent_high = df["High"].rolling(10).max().iloc[-2]
    recent_low = df["Low"].rolling(10).min().iloc[-2]

    if df["Close"].iloc[-1] > recent_high:
        return "BUY"
    elif df["Close"].iloc[-1] < recent_low:
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
    current = df.iloc[-1]

    if last["Close"] < last["Open"] and current["Close"] > current["Open"]:
        return "BUY"
    elif last["Close"] > last["Open"] and current["Close"] < current["Open"]:
        return "SELL"
    return None


def sniper_entry(df):
    candle = df.iloc[-1]
    body = abs(candle["Close"] - candle["Open"])
    wick = candle["High"] - candle["Low"]

    return body / wick > 0.6 if wick != 0 else False


# =========================
# SIGNAL ENGINE
# =========================
def generate_signal(symbol):
    df_1m = get_data(symbol, "1m")
    df_5m = get_data(symbol, "5m")

    if len(df_1m) < 50 or len(df_5m) < 50:
        return None

    trend = detect_trend(df_5m)
    bos = break_of_structure(df_1m)
    sweep = liquidity_sweep(df_1m)
    ob = order_block(df_1m)
    sniper = sniper_entry(df_1m)

    score = 0

    if trend == bos:
        score += 2
    if trend == sweep:
        score += 2
    if trend == ob:
        score += 2
    if sniper:
        score += 2

    if not is_kill_zone():
        score -= 2

    if score < 4:
        return None

    strength = "🔥 STRONG" if score >= 6 else "⚡ MEDIUM"
    price = df_1m["Close"].iloc[-1]

    return f"""
🚀 SIGNAL ALERT

Pair: {symbol}
Type: {trend}
Strength: {strength}
Entry: {price}

⏰ Kill Zone: {"YES" if is_kill_zone() else "NO"}
"""


# =========================
# SCANNER
# =========================
def scan_market():
    print("Scanning market...")

    for symbol in SYMBOLS:
        signal = generate_signal(symbol)
        if signal:
            print(signal)
            send_telegram(signal)


# =========================
# AUTO LOOP
# =========================
def run_bot():
    schedule.every(1).minutes.do(scan_market)

    while True:
        schedule.run_pending()
        time.sleep(1)


# =========================
# SAFE THREAD START
# =========================
bot_started = False

def start_background():
    global bot_started
    if not bot_started:
        bot_started = True
        print("Starting bot thread...")
        threading.Thread(target=run_bot, daemon=True).start()


# =========================
# START (SAFE FOR RENDER)
# =========================
if os.environ.get("RUN_MAIN") == "true" or not app.debug:
    start_background()
