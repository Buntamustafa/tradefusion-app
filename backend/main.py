from flask import Flask, jsonify
import yfinance as yf
import pandas as pd
from datetime import datetime
from telegram_bot import send_telegram

app = Flask(__name__)

PAIRS = ["EURUSD=X", "GBPUSD=X", "USDCAD=X", "EURGBP=X", "BTC-USD", "GC=F"]

# =========================
# DATA
# =========================
def get_data(symbol, interval):
    try:
        df = yf.download(symbol, period="2d", interval=interval, progress=False)
        return df if not df.empty else None
    except:
        return None

# =========================
# INDICATORS
# =========================
def atr(df):
    return (df["High"] - df["Low"]).rolling(14).mean().iloc[-1]

# =========================
# SMART MONEY CORE
# =========================
def liquidity_sweep(df):
    return df["High"].iloc[-1] > df["High"].rolling(10).max().iloc[-2] or \
           df["Low"].iloc[-1] < df["Low"].rolling(10).min().iloc[-2]

def bos(df):
    return df["Close"].iloc[-1] > df["High"].iloc[-2] or \
           df["Close"].iloc[-1] < df["Low"].iloc[-2]

def fvg(df):
    return df["Low"].iloc[-1] > df["High"].iloc[-3] or \
           df["High"].iloc[-1] < df["Low"].iloc[-3]

def order_block(df):
    last = df.iloc[-2]
    return abs(last["Close"] - last["Open"]) > (last["High"] - last["Low"]) * 0.5

# =========================
# MULTI TIMEFRAME
# =========================
def mtf_bias(symbol):
    df1 = get_data(symbol, "1h")
    df2 = get_data(symbol, "15m")

    if df1 is None or df2 is None:
        return None

    htf = df1["Close"].iloc[-1] > df1["Close"].rolling(20).mean().iloc[-1]
    mtf = df2["Close"].iloc[-1] > df2["High"].iloc[-2]

    if htf and mtf:
        return "BUY"
    if not htf and not mtf:
        return "SELL"

    return None

# =========================
# 5M ENTRY REFINEMENT
# =========================
def refined_entry(df, direction):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    body = abs(last["Close"] - last["Open"])
    wick = last["High"] - last["Low"]

    strong = body > wick * 0.6

    if direction == "BUY":
        return last["Close"] > prev["High"] and strong

    if direction == "SELL":
        return last["Close"] < prev["Low"] and strong

    return False

# =========================
# 1M SNIPER ENTRY (FINAL TRIGGER)
# =========================
def sniper_1m(df, direction):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # BUY precision
    if direction == "BUY":
        return (
            last["Low"] < prev["Low"] and
            last["Close"] > last["Open"] and
            last["Close"] > prev["High"]
        )

    # SELL precision
    if direction == "SELL":
        return (
            last["High"] > prev["High"] and
            last["Close"] < last["Open"] and
            last["Close"] < prev["Low"]
        )

    return False

# =========================
# KILL ZONE
# =========================
def kill_zone():
    hour = datetime.utcnow().hour
    return 6 <= hour <= 9 or 12 <= hour <= 15

# =========================
# SIGNAL ENGINE
# =========================
def analyze(pair):
    df_15 = get_data(pair, "15m")
    df_5 = get_data(pair, "5m")
    df_1 = get_data(pair, "1m")

    if df_15 is None or df_5 is None or df_1 is None:
        return {"pair": pair, "message": "No data"}

    direction = mtf_bias(pair)
    if not direction:
        return {"pair": pair, "message": "No MTF alignment"}

    if atr(df_15) < 0.0008:
        return {"pair": pair, "message": "Low volatility"}

    # Smart money confluence
    score = 0
    if liquidity_sweep(df_5): score += 2
    if bos(df_5): score += 2
    if fvg(df_5): score += 1
    if order_block(df_5): score += 2

    # Entry refinement
    if not refined_entry(df_5, direction):
        return {"pair": pair, "message": "No refined entry"}

    # 1M sniper trigger
    if not sniper_1m(df_1, direction):
        return {"pair": pair, "message": "Waiting 1M sniper"}

    # Strength classification
    if score >= 6:
        strength = "🔥 STRONG"
    elif score >= 4:
        strength = "⚡ MEDIUM"
    else:
        return {"pair": pair, "message": "No sniper setup"}

    if not kill_zone() and strength == "🔥 STRONG":
        strength = "⚡ MEDIUM"

    message = f"""
{strength} SNIPER ENTRY

Pair: {pair}
Direction: {direction}

Entry: 1M Precision Trigger
Session: {"Kill Zone" if kill_zone() else "Outside"}
"""

    send_telegram(message)

    return {
        "pair": pair,
        "signal": direction,
        "strength": strength
    }

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return "Sniper Bot Running"

@app.route("/scan")
def scan():
    results = []
    for pair in PAIRS:
        results.append(analyze(pair))
    return jsonify(results)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run()
