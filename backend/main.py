from flask import Flask, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import ta
import os
from datetime import datetime

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
# KILL ZONE (SESSION FILTER)
# ===============================
def in_kill_zone():
    now = datetime.utcnow().hour
    return (7 <= now <= 10) or (12 <= now <= 15)

# ===============================
# NEWS FILTER
# ===============================
def high_impact_news():
    try:
        url = f"https://api.twelvedata.com/economic_calendar?importance=high&apikey={API_KEY}"
        res = requests.get(url, timeout=5).json()
        return "data" in res and len(res["data"]) > 0
    except:
        return False

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
# ANALYSIS
# ===============================
def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    trend = "BUY" if last["ema20"] > last["ema50"] else "SELL"
    rsi = last["rsi"]

    # Liquidity
    liquidity = None
    if last["low"] < prev["low"]:
        liquidity = "SELL_SIDE"
    elif last["high"] > prev["high"]:
        liquidity = "BUY_SIDE"

    # FVG
    fvg = None
    if prev["low"] > prev2["high"]:
        fvg = "BULLISH"
    elif prev["high"] < prev2["low"]:
        fvg = "BEARISH"

    # BOS
    bos = None
    if last["high"] > prev["high"] and prev["high"] > prev2["high"]:
        bos = "BULLISH"
    elif last["low"] < prev["low"] and prev["low"] < prev2["low"]:
        bos = "BEARISH"

    return {
        "trend": trend,
        "rsi": rsi,
        "liquidity": liquidity,
        "fvg": fvg,
        "bos": bos,
        "close": last["close"]
    }

# ===============================
# SIGNAL ENGINE
# ===============================
def generate_signal(df_5m, df_15m):

    # ===============================
    # ⚡ SCALP OUTSIDE KILL ZONE
    # ===============================
    if not in_kill_zone():
        a5 = analyze(df_5m)
        entry = a5["close"]
        trend = a5["trend"]
        rsi = a5["rsi"]

        if trend == "BUY":
            sl = entry * 0.997
            tp = entry * 1.01
        else:
            sl = entry * 1.003
            tp = entry * 0.99

        return {
            "action": trend,
            "entry": round(entry, 4),
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "confidence": "55%",
            "strength": "SCALP ⚡ (OUTSIDE SESSION)",
            "reason": f"Outside kill zone | Trend={trend} | RSI={round(rsi,1)}"
        }

    # ===============================
    # ⛔ NEWS FILTER
    # ===============================
    if high_impact_news():
        return {"message": "High impact news - stay out"}

    a5 = analyze(df_5m)
    a15 = analyze(df_15m)

    trend_5m = a5["trend"]
    trend_15m = a15["trend"]

    rsi = a5["rsi"]
    liquidity = a5["liquidity"]
    fvg = a5["fvg"]
    bos = a5["bos"]
    entry = a5["close"]

    signal = None
    strength = None

    # ===============================
    # 💀 SNIPER
    # ===============================
    if (
        trend_5m == "BUY"
        and trend_15m == "BUY"
        and liquidity == "SELL_SIDE"
        and fvg == "BULLISH"
        and bos == "BULLISH"
        and rsi < 45
    ):
        signal = "BUY"
        strength = "SNIPER 💀"

    elif (
        trend_5m == "SELL"
        and trend_15m == "SELL"
        and liquidity == "BUY_SIDE"
        and fvg == "BEARISH"
        and bos == "BEARISH"
        and rsi > 55
    ):
        signal = "SELL"
        strength = "SNIPER 💀"

    # ===============================
    # 💪 STRONG
    # ===============================
    elif (
        trend_5m == trend_15m
        and (
            (trend_5m == "BUY" and liquidity == "SELL_SIDE" and bos == "BULLISH")
            or (trend_5m == "SELL" and liquidity == "BUY_SIDE" and bos == "BEARISH")
        )
    ):
        signal = trend_5m
        strength = "STRONG"

    # ===============================
    # ⚡ SCALP (INSIDE SESSION)
    # ===============================
    else:
        signal = trend_5m
        strength = "SCALP ⚡"

    # ===============================
    # RISK MANAGEMENT
    # ===============================
    if signal == "BUY":
        sl = entry * 0.997
        tp = entry * 1.02
    else:
        sl = entry * 1.003
        tp = entry * 0.98

    # ===============================
    # CONFIDENCE
    # ===============================
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
        "reason": f"5m:{trend_5m} | 15m:{trend_15m} | BOS:{bos} | {liquidity} | {fvg} | RSI={round(rsi,1)}"
    }

# ===============================
# ROUTES
# ===============================
@app.route('/')
def home():
    return "NEYLA.fx ELITE PRO MAX API is running 🚀"

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
