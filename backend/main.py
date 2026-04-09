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
    "BTC/USD": "BTCUSDT"
}

# ===============================
# FETCH DATA (MULTI TIMEFRAME)
# ===============================
def get_data(symbol, interval="5m"):
    url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval={interval}&limit=150"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code != 200:
        raise Exception(f"API error: {response.status_code}")

    data = response.json()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","trades","taker_base","taker_quote","ignore"
    ])

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    return df

# ===============================
# TREND FUNCTION (15m)
# ===============================
def get_trend(df):
    df["ema"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    last = df.iloc[-1]
    return "BUY" if last["close"] > last["ema"] else "SELL"

# ===============================
# SNIPER ANALYSIS
# ===============================
def analyze(df_5m, df_15m):
    df_5m["rsi"] = ta.momentum.RSIIndicator(df_5m["close"]).rsi()
    df_5m["ema"] = ta.trend.EMAIndicator(df_5m["close"], window=50).ema_indicator()

    last = df_5m.iloc[-1]
    prev = df_5m.iloc[-2]
    prev2 = df_5m.iloc[-3]

    trend_5m = "BUY" if last["close"] > last["ema"] else "SELL"
    trend_15m = get_trend(df_15m)

    # ===============================
    # REQUIRE TREND ALIGNMENT
    # ===============================
    if trend_5m != trend_15m:
        return None

    trend = trend_5m

    # ===============================
    # LIQUIDITY SWEEP (MANDATORY)
    # ===============================
    liquidity = None
    if last["low"] < prev["low"] and prev["low"] < prev2["low"]:
        liquidity = "Sell-side liquidity swept"
    elif last["high"] > prev["high"] and prev["high"] > prev2["high"]:
        liquidity = "Buy-side liquidity swept"

    if not liquidity:
        return None  # ❌ no trade

    # ===============================
    # FVG (MANDATORY)
    # ===============================
    fvg = None
    if prev2["high"] < prev["low"]:
        fvg = "Bullish FVG"
    elif prev2["low"] > prev["high"]:
        fvg = "Bearish FVG"

    if not fvg:
        return None  # ❌ no trade

    # ===============================
    # FINAL SIGNAL
    # ===============================
    signal = trend

    # ===============================
    # CONFIDENCE (STRICT)
    # ===============================
    confidence = 85

    if "liquidity" in liquidity:
        confidence += 5
    if "FVG" in fvg:
        confidence += 5

    # ===============================
    # OUTPUT
    # ===============================
    return {
        "action": signal,
        "entry": round(last["close"], 2),
        "sl": round(last["close"] * 0.995, 2),
        "tp": round(last["close"] * 1.02, 2),
        "confidence": f"{confidence}%",
        "reason": f"{trend} | {liquidity} | {fvg} | MTF aligned"
    }

# ===============================
# ROUTES
# ===============================
@app.route('/')
def home():
    return "NEYLA.fx SNIPER API 🚀"

@app.route('/signals')
def signals():
    results = []

    for name, symbol in PAIRS.items():
        try:
            df_5m = get_data(symbol, "5m")
            df_15m = get_data(symbol, "15m")

            signal = analyze(df_5m, df_15m)

            if signal:
                signal["pair"] = name
                results.append(signal)
            else:
                results.append({
                    "pair": name,
                    "message": "No sniper setup"
                })

        except Exception as e:
            results.append({
                "pair": name,
                "error": str(e)
            })

    return jsonify(results)

# ===============================
# RUN
# ===============================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
