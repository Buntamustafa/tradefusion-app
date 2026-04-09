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
# FETCH DATA (TWELVEDATA)
# ===============================
def get_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=100&apikey={API_KEY}"

    response = requests.get(url, timeout=10)
    data = response.json()

    if "values" not in data:
        raise Exception(data.get("message", "Data fetch failed"))

    df = pd.DataFrame(data["values"])
    df = df.iloc[::-1]  # oldest → newest

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    return df

# ===============================
# ANALYSIS ENGINE (SMART FILTER)
# ===============================
def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # TREND
    trend = "BUY" if last["ema20"] > last["ema50"] else "SELL"

    rsi = last["rsi"]

    # LIQUIDITY
    liquidity = None
    if last["low"] < prev["low"]:
        liquidity = "SELL_SIDE"
    elif last["high"] > prev["high"]:
        liquidity = "BUY_SIDE"

    # FVG
    fvg = None
    if last["low"] > prev["high"]:
        fvg = "BULLISH"
    elif last["high"] < prev["low"]:
        fvg = "BEARISH"

    # ===============================
    # STRICT SIGNAL LOGIC
    # ===============================
    signal = None
    strength = "NONE"

    # BUY SETUPS
    if (
        trend == "BUY"
        and rsi < 45
        and liquidity == "SELL_SIDE"
        and fvg == "BULLISH"
    ):
        signal = "BUY"
        strength = "SNIPER 💀"

    elif (
        trend == "BUY"
        and rsi < 55
        and liquidity == "SELL_SIDE"
    ):
        signal = "BUY"
        strength = "STRONG"

    # SELL SETUPS
    elif (
        trend == "SELL"
        and rsi > 55
        and liquidity == "BUY_SIDE"
        and fvg == "BEARISH"
    ):
        signal = "SELL"
        strength = "SNIPER 💀"

    elif (
        trend == "SELL"
        and rsi > 50
        and liquidity == "BUY_SIDE"
    ):
        signal = "SELL"
        strength = "STRONG"

    # NO TRADE
    if signal is None:
        return {"message": "No valid setup"}

    entry = last["close"]

    # RISK MANAGEMENT
    if signal == "BUY":
        sl = entry * 0.995
        tp = entry * 1.02
    else:
        sl = entry * 1.005
        tp = entry * 0.98

    confidence = 70
    if strength == "STRONG":
        confidence = 85
    if strength == "SNIPER 💀":
        confidence = 95

    return {
        "action": signal,
        "entry": round(entry, 4),
        "sl": round(sl, 4),
        "tp": round(tp, 4),
        "confidence": f"{confidence}%",
        "strength": strength,
        "reason": f"{trend} | {liquidity} | {fvg} | RSI={round(rsi,1)}"
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
            df = get_data(symbol)
            signal = analyze(df)
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
