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
# CONFIG (FIXED SYMBOLS)
# ===============================
PAIRS = {
    "EUR/USD": "EUR/USD",
    "BTC/USD": "BTCUSDT",
    "XAU/USD": "XAU/USD"
}

TWELVE_API_KEY = os.getenv("TWELVE_API_KEY")

CACHE = {}
CACHE_TIME = 60


# ===============================
# CACHE
# ===============================
def get_cache(key):
    if key in CACHE:
        data, t = CACHE[key]
        if time.time() - t < CACHE_TIME:
            return data
    return None


def set_cache(key, value):
    CACHE[key] = (value, time.time())


# ===============================
# FETCH (SAFE)
# ===============================
def fetch_twelve(symbol):
    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": symbol,
        "interval": "5min",
        "apikey": TWELVE_API_KEY,
        "outputsize": 100
    }

    for _ in range(3):
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json()

            if "values" not in data:
                time.sleep(1)
                continue

            df = pd.DataFrame(data["values"])
            df = df.iloc[::-1]

            df["close"] = df["close"].astype(float)
            df["high"] = df["high"].astype(float)
            df["low"] = df["low"].astype(float)

            if len(df) < 50:
                raise Exception("Not enough data")

            return df

        except:
            time.sleep(1)

    raise Exception("TwelveData failed")


def fetch_binance(symbol):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100"

    try:
        r = requests.get(url, timeout=10)
        data = r.json()

        if not isinstance(data, list):
            raise Exception("Invalid Binance data")

        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "close_time","qav","trades","taker_base","taker_quote","ignore"
        ])

        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)

        if len(df) < 50:
            raise Exception("Not enough Binance data")

        return df

    except:
        raise Exception("Binance failed")


def get_data(name, symbol):
    cached = get_cache(name)
    if cached:
        return cached

    try:
        if "BTC" in name:
            df = fetch_binance(symbol)
        else:
            df = fetch_twelve(symbol)

        set_cache(name, df)
        return df

    except Exception as e:
        raise Exception(str(e))


# ===============================
# ANALYSIS (SAFE)
# ===============================
def analyze(df):
    if df is None or len(df) < 2:
        raise Exception("Invalid data")

    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()

    last = df.iloc[-1]

    trend = "BUY" if last["close"] > last["ema"] else "SELL"

    return trend, last["rsi"], last["close"]


def confirmation(df):
    if len(df) < 2:
        return None

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
        return {"message": "Waiting for setup"}

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
# API
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
            results.append({
                "pair": name,
                "error": str(e)
            })

    return jsonify(results)


# ===============================
# DASHBOARD
# ===============================
@app.route('/')
def dashboard():
    return render_template_string("""
    <html>
    <body style="background:black;color:white;text-align:center;font-family:sans-serif;">
    <h2>TradeFusion Live</h2>
    <div id="data"></div>

    <script>
    async function load(){
        let res = await fetch('/signals');
        let data = await res.json();

        let html = "";
        data.forEach(d=>{
            html += `<p>${d.pair}: ${d.action || d.message || d.error}</p>`;
        });

        document.getElementById("data").innerHTML = html;
    }

    setInterval(load, 10000);
    load();
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
