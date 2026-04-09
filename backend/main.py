from flask import Flask, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import ta
import os

app = Flask(__name__)
CORS(app)

# ===============================
# CONFIG (CRYPTO ONLY)
# ===============================
PAIRS = {
    "BTC/USD": "BTCUSDT"
}

# ===============================
# FETCH MARKET DATA (BINANCE US)
# ===============================
def get_data(symbol):
    url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval=5m&limit=150"

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
# SMART MONEY ANALYSIS
# ===============================
def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    # ===============================
    # 1. TREND (STRUCTURE)
    # ===============================
    trend = "BUY" if last["close"] > last["ema"] else "SELL"

    # ===============================
    # 2. LIQUIDITY SWEEP
    # ===============================
    liquidity = None
    if last["low"] < prev["low"] and prev["low"] < prev2["low"]:
        liquidity = "Sell-side liquidity swept"
    elif last["high"] > prev["high"] and prev["high"] > prev2["high"]:
        liquidity = "Buy-side liquidity swept"

    # ===============================
    # 3. FAIR VALUE GAP (REALISTIC)
    # ===============================
    fvg = None
    if prev2["high"] < prev["low"]:
        fvg = "Bullish FVG"
    elif prev2["low"] > prev["high"]:
        fvg = "Bearish FVG"

    # ===============================
    # 4. ENTRY LOGIC (CONFLUENCE)
    # ===============================
    signal = trend

    if liquidity and fvg:
        if "Sell-side" in liquidity and fvg == "Bullish FVG":
            signal = "BUY"
        elif "Buy-side" in liquidity and fvg == "Bearish FVG":
            signal = "SELL"

    # RSI filter
    if last["rsi"] < 30:
        signal = "BUY"
    elif last["rsi"] > 70:
        signal = "SELL"

    # ===============================
    # 5. CONFIDENCE SYSTEM
    # ===============================
    confidence = 60

    if signal == trend:
        confidence += 10
    if liquidity:
        confidence += 10
    if fvg:
        confidence += 10
    if (signal == "BUY" and last["rsi"] < 40) or (signal == "SELL" and last["rsi"] > 60):
        confidence += 10

    # ===============================
    # OUTPUT
    # ===============================
    return {
        "action": signal,
        "entry": round(last["close"], 2),
        "sl": round(last["close"] * 0.995, 2),
        "tp": round(last["close"] * 1.02, 2),
        "confidence": f"{confidence}%",
        "reason": f"{trend} | {liquidity} | {fvg} | RSI={round(last['rsi'],1)}"
    }

# ===============================
# ROUTES
# ===============================
@app.route('/')
def home():
    return "NEYLA.fx PRO API is running 🚀"

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
