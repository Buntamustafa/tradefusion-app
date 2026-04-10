from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import requests
import pandas as pd
import ta
import os
import time

app = Flask(__name__)
CORS(app)

# ===============================
# CONFIG
# ===============================
PAIRS = {
    "EUR/USD": "EURUSD",
    "BTC/USD": "BTCUSDT",
    "XAU/USD": "XAUUSD"
}

TWELVE_API_KEY = os.getenv("TWELVE_API_KEY")

# ===============================
# CACHE
# ===============================
CACHE = {}
CACHE_TIME = 60


def get_cached(key):
    if key in CACHE:
        data, timestamp = CACHE[key]
        if time.time() - timestamp < CACHE_TIME:
            return data
    return None


def set_cache(key, value):
    CACHE[key] = (value, time.time())


# ===============================
# FETCH DATA
# ===============================
def fetch_twelve(symbol, interval="5min"):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "apikey": TWELVE_API_KEY,
        "outputsize": 100
    }

    r = requests.get(url, params=params)
    data = r.json()

    if "values" not in data:
        raise Exception("TwelveData error")

    df = pd.DataFrame(data["values"])
    df = df.iloc[::-1]

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    if len(df) < 50:
        raise Exception("Not enough data")

    return df


def fetch_binance(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100"
    r = requests.get(url)
    data = r.json()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","trades","taker_base","taker_quote","ignore"
    ])

    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    return df


def get_data(name, symbol):
    cached = get_cached(name)
    if cached:
        return cached

    if "BTC" in name:
        df = fetch_binance(symbol)
    else:
        df = fetch_twelve(symbol)

    set_cache(name, df)
    return df


# ===============================
# ANALYSIS
# ===============================
def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()

    last = df.iloc[-1]

    trend = "BUY" if last["close"] > last["ema"] else "SELL"

    return trend, last["rsi"], last["close"]


def confirmation(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last["close"] > prev["high"]:
        return "BUY"
    elif last["close"] < prev["low"]:
        return "SELL"
    return None


# ===============================
# SIGNAL
# ===============================
def generate_signal(df):
    trend, rsi, entry = analyze(df)
    confirm = confirmation(df)

    if trend == "BUY" and confirm == "BUY" and rsi < 60:
        signal = "BUY"
    elif trend == "SELL" and confirm == "SELL" and rsi > 40:
        signal = "SELL"
    else:
        return {"message": "No clean scalp"}

    if signal == "BUY":
        sl = entry * 0.998
        tp = entry * 1.01
    else:
        sl = entry * 1.002
        tp = entry * 0.99

    return {
        "action": signal,
        "entry": round(entry, 4),
        "sl": round(sl, 4),
        "tp": round(tp, 4),
        "confidence": "60%",
        "strength": "SCALP ⚡",
        "reason": f"{signal} | RSI={round(rsi,1)}"
    }


# ===============================
# API ROUTE
# ===============================
@app.route('/signals')
def signals():
    results = []

    for name, symbol in PAIRS.items():
        try:
            df = get_data(name, symbol)
            signal = generate_signal(df)
            signal["pair"] = name
            results.append(signal)
        except Exception as e:
            results.append({"pair": name, "error": str(e)})

    return jsonify(results)


# ===============================
# LIVE DASHBOARD
# ===============================
@app.route('/')
def dashboard():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>TradeFusion Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            background: #0f172a;
            color: white;
            font-family: Arial;
            text-align: center;
        }
        h1 {
            margin-top: 20px;
        }
        .card {
            background: #1e293b;
            margin: 15px;
            padding: 20px;
            border-radius: 10px;
        }
        .buy { color: #22c55e; }
        .sell { color: #ef4444; }
        .wait { color: #facc15; }
    </style>
</head>
<body>

<h1>🚀 TradeFusion Live Signals</h1>
<div id="signals"></div>

<script>
async function loadSignals() {
    const res = await fetch('/signals');
    const data = await res.json();

    let html = "";

    data.forEach(s => {
        let color = "wait";
        if (s.action === "BUY") color = "buy";
        if (s.action === "SELL") color = "sell";

        html += `
        <div class="card">
            <h2>${s.pair}</h2>
            <p class="${color}">${s.action || s.message}</p>
            <p>Entry: ${s.entry || "-"}</p>
            <p>SL: ${s.sl || "-"}</p>
            <p>TP: ${s.tp || "-"}</p>
            <p>${s.reason || ""}</p>
        </div>
        `;
    });

    document.getElementById("signals").innerHTML = html;
}

// Auto refresh every 10 seconds
setInterval(loadSignals, 10000);

// Initial load
loadSignals();
</script>

</body>
</html>
""")


# ===============================
# RUN
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
