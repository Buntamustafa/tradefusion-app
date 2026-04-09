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
    df = df.iloc[::-1]  # reverse to oldest → newest

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    return df

# ===============================
# ANALYSIS ENGINE (ALL-IN-ONE)
# ===============================
def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # ===============================
    # TREND
    # ===============================
    if last["ema20"] > last["ema50"]:
        trend = "BUY"
    else:
        trend = "SELL"

    # ===============================
    # RSI
    # ===============================
    if last["rsi"] < 30:
        rsi_signal = "BUY"
    elif last["rsi"] > 70:
        rsi_signal = "SELL"
    else:
        rsi_signal = "NEUTRAL"

    # ===============================
    # LIQUIDITY
    # ===============================
    liquidity = None
    if last["low"] < prev["low"]:
        liquidity = "Sell-side liquidity taken"
    elif last["high"] > prev["high"]:
        liquidity = "Buy-side liquidity taken"

    # ===============================
    # FVG
    # ===============================
    fvg = None
    if abs(last["high"] - prev["low"]) > 0.002:
        fvg = "Bullish FVG"
    elif abs(prev["high"] - last["low"]) > 0.002:
        fvg = "Bearish FVG"

    # ===============================
    # SNIPER MODE (STRICT)
    # ===============================
    sniper = None

    if trend == "BUY" and rsi_signal == "BUY" and liquidity:
        sniper = "BUY"
    elif trend == "SELL" and rsi_signal == "SELL" and liquidity:
        sniper = "SELL"

    # ===============================
    # FINAL SIGNAL LOGIC
    # ===============================
    signal = None
    strength = "WEAK"

    if sniper:
        signal = sniper
        strength = "SNIPER 💀"
    elif trend == rsi_signal:
        signal = trend
        strength = "STRONG"
    else:
        signal = trend

    if signal is None:
        return {"message": "No valid setup"}

    entry = last["close"]

    # Dynamic SL/TP
    if signal == "BUY":
        sl = entry * 0.995
        tp = entry * 1.02
    else:
        sl = entry * 1.005
        tp = entry * 0.98

    # ===============================
    # CONFIDENCE
    # ===============================
    confidence = 60
    if trend == rsi_signal:
        confidence += 15
    if liquidity:
        confidence += 10
    if fvg:
        confidence += 10
    if strength == "SNIPER 💀":
        confidence = 95

    return {
        "action": signal,
        "entry": round(entry, 4),
        "sl": round(sl, 4),
        "tp": round(tp, 4),
        "confidence": f"{confidence}%",
        "strength": strength,
        "reason": f"{trend} | {liquidity} | {fvg} | RSI={round(last['rsi'],1)}"
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
