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
API_KEY = os.getenv("TWELVE_API_KEY")

PAIRS = {
    "EUR/USD": "EUR/USD",
    "BTC/USD": "BTC/USD",
    "XAU/USD": "XAU/USD"
}

# ===============================
# FETCH DATA
# ===============================
def get_data(symbol, interval):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey={API_KEY}"

    response = requests.get(url, timeout=10)
    data = response.json()

    if "values" not in data:
        raise Exception(data.get("message", "Data fetch failed"))

    df = pd.DataFrame(data["values"])
    df = df.iloc[::-1]

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    return df

# ===============================
# ANALYSIS FUNCTION
# ===============================
def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    trend = "BUY" if last["ema20"] > last["ema50"] else "SELL"
    rsi = last["rsi"]

    liquidity = None
    if last["low"] < prev["low"]:
        liquidity = "SELL_SIDE"
    elif last["high"] > prev["high"]:
        liquidity = "BUY_SIDE"

    fvg = None
    if last["low"] > prev["high"]:
        fvg = "BULLISH"
    elif last["high"] < prev["low"]:
        fvg = "BEARISH"

    return {
        "trend": trend,
        "rsi": rsi,
        "liquidity": liquidity,
        "fvg": fvg,
        "close": last["close"]
    }

# ===============================
# MULTI-TIMEFRAME ENGINE
# ===============================
def generate_signal(df_5m, df_15m):
    a5 = analyze(df_5m)
    a15 = analyze(df_15m)

    trend_5m = a5["trend"]
    trend_15m = a15["trend"]

    rsi = a5["rsi"]
    liquidity = a5["liquidity"]
    fvg = a5["fvg"]
    entry = a5["close"]

    signal = None
    strength = None

    # ===============================
    # SNIPER (BOTH TIMEFRAMES AGREE)
    # ===============================
    if (
        trend_5m == "BUY"
        and trend_15m == "BUY"
        and rsi < 40
        and liquidity == "SELL_SIDE"
        and fvg == "BULLISH"
    ):
        signal = "BUY"
        strength = "SNIPER 💀"

    elif (
        trend_5m == "SELL"
        and trend_15m == "SELL"
        and rsi > 60
        and liquidity == "BUY_SIDE"
        and fvg == "BEARISH"
    ):
        signal = "SELL"
        strength = "SNIPER 💀"

    # ===============================
    # STRONG (TREND CONFIRMED)
    # ===============================
    elif trend_5m == trend_15m:
        signal = trend_5m
        strength = "STRONG"

    # ===============================
    # SCALP (DIFFERENT TIMEFRAMES)
    # ===============================
    else:
        signal = trend_5m
        strength = "SCALP ⚡"

    # ===============================
    # RISK MANAGEMENT
    # ===============================
    if signal == "BUY":
        sl = entry * 0.997
        tp = entry * 1.015
    else:
        sl = entry * 1.003
        tp = entry * 0.985

    # CONFIDENCE
    confidence = 60
    if strength == "STRONG":
        confidence = 80
    if strength == "SNIPER 💀":
        confidence = 95

    return {
        "action": signal,
        "entry": round(entry, 4),
        "sl": round(sl, 4),
        "tp": round(tp, 4),
        "confidence": f"{confidence}%",
        "strength": strength,
        "reason": f"5m:{trend_5m} | 15m:{trend_15m} | RSI={round(rsi,1)} | {liquidity} | {fvg}"
    }

# ===============================
# ROUTES
# ===============================
@app.route('/')
def home():
    return "NEYLA.fx API is running 🚀"

@app.route('/signals')
def signals():
    results = []

    for name, symbol in PAIRS.items():
        try:
            df_5m = get_data(symbol, "5min")
            df_15m = get_data(symbol, "15min")

            signal = generate_signal(df_5m, df_15m)
            signal["pair"] = name

            results.append(signal)

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
