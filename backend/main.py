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
    "BTC/USD": "BTCUSDT"
}

# ===============================
# FETCH MARKET DATA (BINANCE US)
# ===============================
def get_data(symbol):
    url = f"https://api.binance.us/api/v3/klines?symbol={symbol}&interval=5m&limit=100"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
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

    except Exception as e:
        print("ERROR fetching data:", e)
        raise

# ===============================
# ANALYSIS
# ===============================
def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    trend = "BUY" if last["close"] > last["ema"] else "SELL"

    # RSI logic
    if last["rsi"] < 30:
        signal = "BUY"
    elif last["rsi"] > 70:
        signal = "SELL"
    else:
        signal = trend

    # Liquidity logic
    liquidity = ""
    if last["low"] < prev["low"]:
        liquidity = "Sell-side liquidity taken"
    elif last["high"] > prev["high"]:
        liquidity = "Buy-side liquidity taken"

    # FVG logic
    fvg = "FVG present" if abs(last["high"] - last["low"]) > 0.002 else "No FVG"

    # Confidence score
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
