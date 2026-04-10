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
    "EUR/USD": {"type": "forex", "symbol": "EUR/USD"},
    "BTC/USD": {"type": "crypto", "symbol": "BTCUSDT"},
    "XAU/USD": {"type": "forex", "symbol": "XAU/USD"}
}

API_KEY = os.getenv("TWELVE_API_KEY")

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
# FETCH FUNCTIONS
# ===============================
def fetch_twelve(symbol):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": "5min",
        "apikey": API_KEY,
        "outputsize": 100
    }

    for _ in range(3):
        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json()

            if "values" not in data:
                time.sleep(1)
                continue

            df = pd.DataFrame(data["values"]).iloc[::-1]

            for col in ["close", "high", "low"]:
                df[col] = df[col].astype(float)

            if len(df) < 50:
                raise Exception("Not enough data")

            return df

        except:
            time.sleep(1)

    raise Exception("TwelveData failed")

def fetch_bybit(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=5&limit=100"
        r = requests.get(url, timeout=10)
        data = r.json()

        candles = data["result"]["list"]

        df = pd.DataFrame(candles, columns=[
            "time","open","high","low","close","volume","turnover"
        ]).iloc[::-1]

        for col in ["open","close","high","low"]:
            df[col] = df[col].astype(float)

        return df
    except:
        return None

def fetch_binance(symbol):
    urls = [
        f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100",
        f"https://api.binance.com/api/v3/uiKlines?symbol={symbol}&interval=5m&limit=100"
    ]

    for url in urls:
        for _ in range(2):
            try:
                r = requests.get(url, timeout=10)
                data = r.json()

                if isinstance(data, list) and len(data) > 50:
                    df = pd.DataFrame(data, columns=[
                        "time","open","high","low","close","volume",
                        "close_time","qav","trades","taker_base","taker_quote","ignore"
                    ])

                    for col in ["open","close","high","low"]:
                        df[col] = df[col].astype(float)

                    return df
            except:
                time.sleep(1)

    return fetch_bybit(symbol)

def get_data(name, info):
    cached = get_cache(name)
    if cached:
        return cached

    if info["type"] == "crypto":
        df = fetch_binance(info["symbol"])
    else:
        df = fetch_twelve(info["symbol"])

    if df is None or len(df) < 50:
        raise Exception("Data fetch failed")

    set_cache(name, df)
    return df

# ===============================
# ANALYSIS
# ===============================
def analyze(df):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

    last = df.iloc[-1]

    trend = "BUY" if last["ema20"] > last["ema50"] else "SELL"
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
# VOLATILITY DETECTION
# ===============================
def get_volatility(df):
    return (df["high"] - df["low"]).rolling(10).mean().iloc[-1]

# ===============================
# SIGNAL ENGINE (AUTO SWITCH)
# ===============================
def generate_signal(df):
    trend, rsi, entry = analyze(df)
    confirm = confirmation(df)
    volatility = get_volatility(df)

    # 🎯 SNIPER (HIGH VOLATILITY)
    if volatility > df["close"].mean() * 0.002:
        if confirm == trend and 45 < rsi < 65:
            signal = trend
            return {
                "action": signal,
                "entry": round(entry,4),
                "sl": round(entry*0.995,4),
                "tp": round(entry*1.03 if signal=="BUY" else entry*0.97,4),
                "confidence": "90%",
                "strength": "SNIPER 🎯",
                "reason": f"High volatility | RSI={round(rsi,1)}"
            }

    # 🔄 MEDIUM
    if confirm == trend:
        return {
            "action": trend,
            "entry": round(entry,4),
            "sl": round(entry*0.997,4),
            "tp": round(entry*1.02 if trend=="BUY" else entry*0.98,4),
            "confidence": "75%",
            "strength": "MEDIUM 🔄",
            "reason": f"Trend + Confirm | RSI={round(rsi,1)}"
        }

    # ⚡ SCALP
    if trend == "BUY" and rsi < 65:
        signal = "BUY"
    elif trend == "SELL" and rsi > 35:
        signal = "SELL"
    else:
        return {"message": "Waiting for setup"}

    return {
        "action": signal,
        "entry": round(entry,4),
        "sl": round(entry*0.998,4),
        "tp": round(entry*1.01 if signal=="BUY" else entry*0.99,4),
        "confidence": "60%",
        "strength": "SCALP ⚡",
        "reason": f"Fallback scalp | RSI={round(rsi,1)}"
    }

# ===============================
# API
# ===============================
@app.route('/signals')
def signals():
    results = []

    for name, info in PAIRS.items():
        try:
            df = get_data(name, info)
            signal = generate_signal(df)
            signal["pair"] = name
            results.append(signal)
        except Exception as e:
            results.append({"pair": name, "error": str(e)})

    return jsonify(results)

# ===============================
# DASHBOARD
# ===============================
@app.route('/')
def dashboard():
    return render_template_string("""
    <html>
    <body style="background:#0f172a;color:white;text-align:center;font-family:sans-serif;">
    <h2>🚀 Smart TradeFusion Dashboard</h2>
    <div id="data"></div>

    <script>
    async function load(){
        let res = await fetch('/signals');
        let data = await res.json();

        let html = "";
        data.forEach(d=>{
            html += `<p><b>${d.pair}</b>: ${d.action || d.message || d.error} (${d.strength || ""})</p>`;
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
