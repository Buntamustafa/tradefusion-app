from flask import Flask
import yfinance as yf
import pandas as pd
import numpy as np
import schedule
import time
import threading
from telegram_bot import send_telegram

app = Flask(__name__)

PAIRS = [
    "EURUSD=X",
    "GBPUSD=X",
    "EURGBP=X",
    "USDCAD=X",
    "GC=F",      # Gold
    "CL=F",      # Oil
    "BTC-USD"
]

# -----------------------------
# MARKET DATA
# -----------------------------
def get_data(symbol, interval="5m"):
    df = yf.download(symbol, period="2d", interval=interval)
    df.dropna(inplace=True)
    return df

# -----------------------------
# SMART MONEY LOGIC
# -----------------------------
def detect_bos(df):
    return df['High'].iloc[-1] > df['High'].iloc[-3]

def detect_liquidity_sweep(df):
    return df['Low'].iloc[-1] < df['Low'].iloc[-3]

def detect_order_block(df):
    return df['Close'].iloc[-2] < df['Open'].iloc[-2]

def kill_zone():
    from datetime import datetime
    hour = datetime.utcnow().hour
    return 7 <= hour <= 10 or 12 <= hour <= 15

# -----------------------------
# MULTI TIMEFRAME
# -----------------------------
def multi_tf(symbol):
    df_15m = get_data(symbol, "15m")
    df_5m = get_data(symbol, "5m")

    trend = "BUY" if df_15m['Close'].iloc[-1] > df_15m['Open'].iloc[-1] else "SELL"
    entry = "BUY" if df_5m['Close'].iloc[-1] > df_5m['Open'].iloc[-1] else "SELL"

    return trend == entry, trend

# -----------------------------
# SNIPER ENTRY (1m)
# -----------------------------
def sniper_entry(symbol):
    df = get_data(symbol, "1m")
    last = df.iloc[-1]

    body = abs(last['Close'] - last['Open'])
    wick = (last['High'] - last['Low'])

    return body > (wick * 0.6)

# -----------------------------
# SIGNAL ENGINE
# -----------------------------
def generate_signal(symbol):
    df = get_data(symbol)

    bos = detect_bos(df)
    sweep = detect_liquidity_sweep(df)
    ob = detect_order_block(df)
    kz = kill_zone()

    mtf_ok, direction = multi_tf(symbol)
    sniper = sniper_entry(symbol)

    score = sum([bos, sweep, ob, kz, mtf_ok, sniper])

    if score >= 5:
        strength = "🔥 STRONG"
    elif score >= 3:
        strength = "⚡ MEDIUM"
    else:
        return None

    zone = "Kill Zone" if kz else "Outside Kill Zone"

    return f"""
{strength} SIGNAL

Pair: {symbol}
Direction: {direction}

✔ BOS: {bos}
✔ Liquidity Sweep: {sweep}
✔ Order Block: {ob}
✔ Kill Zone: {zone}
✔ Multi TF: {mtf_ok}
✔ Sniper Entry (1m): {sniper}
"""

# -----------------------------
# SCANNER
# -----------------------------
def scan_markets():
    print("Scanning markets...")

    for pair in PAIRS:
        try:
            signal = generate_signal(pair)
            if signal:
                print(f"Signal found: {pair}")
                send_telegram(signal)
        except Exception as e:
            print(f"Error: {pair}", e)

# -----------------------------
# AUTO LOOP
# -----------------------------
def run_bot():
    schedule.every(1).minutes.do(scan_markets)

    while True:
        schedule.run_pending()
        time.sleep(1)

# -----------------------------
# START THREAD
# -----------------------------
threading.Thread(target=run_bot).start()

# -----------------------------
# WEB ROUTE (OPTIONAL)
# -----------------------------
@app.route("/")
def home():
    return "Bot is running 🚀"
