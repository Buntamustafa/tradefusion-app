from flask import Flask, jsonify
import yfinance as yf
import pandas as pd
import ta
import time
import os
from telegram_bot import send_telegram

app = Flask(__name__)

# CONFIG
PAIRS = ["EURUSD=X", "GBPUSD=X", "USDCAD=X", "GC=F", "CL=F", "BTC-USD"]

TIMEFRAME = "15m"
HIGHER_TIMEFRAME = "1h"

# FILTER SETTINGS
ATR_THRESHOLD = 0.0005
MIN_TREND_STRENGTH = 0.0003

# ===============================
# FETCH DATA
# ===============================
def get_data(symbol, interval):
    try:
        df = yf.download(symbol, period="2d", interval=interval, progress=False)
        return df
    except:
        return None

# ===============================
# TREND (EMA)
# ===============================
def get_trend(df):
    df["ema50"] = ta.trend.ema_indicator(df["Close"], window=50)
    df["ema200"] = ta.trend.ema_indicator(df["Close"], window=200)

    if df["ema50"].iloc[-1] > df["ema200"].iloc[-1]:
        return "BUY"
    elif df["ema50"].iloc[-1] < df["ema200"].iloc[-1]:
        return "SELL"
    return "NONE"

# ===============================
# TREND STRENGTH
# ===============================
def trend_strength(df):
    return abs(df["ema50"].iloc[-1] - df["ema200"].iloc[-1])

# ===============================
# VOLATILITY (ATR)
# ===============================
def get_atr(df):
    atr = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"])
    return atr.iloc[-1]

# ===============================
# LIQUIDITY SWEEP (SNIPER ENTRY)
# ===============================
def liquidity_sweep(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Sweep below (BUY)
    if last["Low"] < prev["Low"] and last["Close"] > prev["Low"]:
        return "BUY"

    # Sweep above (SELL)
    if last["High"] > prev["High"] and last["Close"] < prev["High"]:
        return "SELL"

    return None

# ===============================
# SIGNAL ENGINE
# ===============================
def generate_signal(symbol):
    df_ltf = get_data(symbol, TIMEFRAME)
    df_htf = get_data(symbol, HIGHER_TIMEFRAME)

    if df_ltf is None or df_htf is None or len(df_ltf) < 50:
        return {"pair": symbol, "message": "No data"}

    # Indicators
    df_ltf["ema50"] = ta.trend.ema_indicator(df_ltf["Close"], window=50)
    df_ltf["ema200"] = ta.trend.ema_indicator(df_ltf["Close"], window=200)

    trend_ltf = get_trend(df_ltf)
    trend_htf = get_trend(df_htf)

    atr = get_atr(df_ltf)
    strength = trend_strength(df_ltf)

    entry = liquidity_sweep(df_ltf)

    # ===============================
    # STRICT CONDITIONS
    # ===============================
    if atr < ATR_THRESHOLD:
        return {"pair": symbol, "message": "Low volatility"}

    if strength < MIN_TREND_STRENGTH:
        return {"pair": symbol, "message": "Weak trend"}

    if trend_ltf != trend_htf:
        return {"pair": symbol, "message": "No alignment"}

    if entry is None:
        return {"pair": symbol, "message": "No sniper setup"}

    # ===============================
    # SIGNAL STRENGTH
    # ===============================
    signal_type = "MEDIUM"

    if strength > MIN_TREND_STRENGTH * 2:
        signal_type = "STRONG"

    price = df_ltf["Close"].iloc[-1]

    message = f"""
🔥 {signal_type} SNIPER SIGNAL

Pair: {symbol}
Direction: {entry}
Price: {price:.5f}

Trend: {trend_ltf} (HTF aligned)
ATR: {atr:.5f}

⚡ Entry: Liquidity Sweep
"""

    # SEND TELEGRAM ALERT
    send_telegram(message)

    return {
        "pair": symbol,
        "signal": entry,
        "type": signal_type,
        "price": float(price)
    }

# ===============================
# API ROUTE
# ===============================
@app.route("/")
def home():
    results = []
    for pair in PAIRS:
        results.append(generate_signal(pair))
        time.sleep(1)

    return jsonify(results)

# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    app.run(debug=True)
