from flask import Flask, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import ta
import os

app = Flask(__name__)
CORS(app)

# ===============================
# CONFIG
# ===============================
PAIRS = {
    "EUR/USD": "EURUSDT",
    "BTC/USD": "BTCUSDT",
    "XAU/USD": "XAUUSDT"
}

# ===============================
# FETCH MARKET DATA (BINANCE)
# ===============================
def get_data(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100"
    data = requests.get(url).json()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","trades","taker_base","taker_quote","ignore"
    ])

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    return df

# ===============================
# ANALYSIS
# ===============================
def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    trend = "BUY" if last["close"] > last["ema"] else "SELL"

    if last["rsi"] < 30:
        signal = "BUY"
    elif last["rsi"] > 70:
        signal = "SELL"
    else:
        signal = trend

    liquidity = ""
    if last["low"] < prev["low"]:
        liquidity = "Sell-side liquidity taken"
    elif last["high"] > prev["high"]:
        liquidity = "Buy-side liquidity taken"

    fvg = "FVG present" if abs(last["high"] - last["low"]) > 0.002 else "No FVG"

    confidence = 70
    if signal == trend:
        confidence += 10
    if liquidity:
        confidence += 5
    if "FVG" in fvg:
        confidence += 5

    return {
        "action": signal,
        "entry": round(last["close"], 4),
        "sl": round(last["close"] * 0.99, 4),
        "tp": round(last["close"] * 1.02, 4),
        "confidence": f"{confidence}%",
        "reason": f"{trend} + RSI + {liquidity} + {fvg}"
    }

# ===============================
# ROUTE
# ===============================
@app.route('/signals')
def signals():
    results = []

    for name, symbol in PAIRS.items():
        try:
            df = get_data(symbol)
            signal = analyze(df)
            signal["pair"] = name
            results.append(signal)
        except:
            results.append({
                "pair": name,
                "error": "Data fetch failed"
            })

    return jsonify(results)

# ===============================
# HOME ROUTE (fix Not Found)
# ===============================
@app.route('/')
def home():
    return "NEYLA.fx API is running 🚀"

# ===============================
# RUN
# ===============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
