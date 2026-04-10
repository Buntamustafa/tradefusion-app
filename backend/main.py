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
# FETCH FOREX
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

            if len(df) >= 50:
                return df
        except:
            time.sleep(1)

    return None

# ===============================
# FETCH CRYPTO (BINANCE)
# ===============================
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

    return None

# ===============================
# FETCH CRYPTO (BYBIT)
# ===============================
def fetch_bybit(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=5&limit=100"
        r = requests.get(url, timeout=10)
        data = r.json()

        if "result" not in data:
            return None

        candles = data["result"]["list"]

        df = pd.DataFrame(candles, columns=[
            "time","open","high","low","close","volume","turnover"
        ]).iloc[::-1]

        for col in ["open","close","high","low"]:
            df[col] = df[col].astype(float)

        return df
    except:
        return None

# ===============================
# 🆕 FETCH CRYPTO (COINGECKO FINAL BACKUP)
# ===============================
def fetch_coingecko():
    try:
        url = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        params = {"vs_currency": "usd", "days": "1"}

        r = requests.get(url, params=params, timeout=10)
        data = r.json()

        prices = data["prices"]

        df = pd.DataFrame(prices, columns=["time","close"])

        df["high"] = df["close"]
        df["low"] = df["close"]

        return df
    except:
        return None

# ===============================
# GET DATA (ULTRA SAFE)
# ===============================
def get_data(name, info):
    cached = get_cache(name)

    for _ in range(2):
        try:
            if info["type"] == "crypto":
                df = fetch_binance(info["symbol"])

                if df is None:
                    df = fetch_bybit(info["symbol"])

                if df is None:
                    df = fetch_coingecko()
            else:
                df = fetch_twelve(info["symbol"])

            if df is not None and len(df) >= 50:
                set_cache(name, df)
                return df

        except:
            time.sleep(1)

    if cached:
        print(f"Using cache for {name}")
        return cached

    return None

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

def get_volatility(df):
    return (df["high"] - df["low"]).rolling(10).mean().iloc[-1]

# ===============================
# SIGNAL ENGINE
# ===============================
def generate_signal(df):
    trend, rsi, entry = analyze(df)
    confirm = confirmation(df)
    volatility = get_volatility(df)

    # 🎯 SNIPER
    if volatility > df["close"].mean() * 0.002:
        if confirm == trend and 45 < rsi < 65:
            return {
                "action": trend,
                "entry": round(entry,4),
                "sl": round(entry*0.995,4),
                "tp": round(entry*1.03 if trend=="BUY" else entry*0.97,4),
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

            if df is None:
                results.append({
                    "pair": name,
                    "message": "Data unavailable (safe mode)"
                })
                continue

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
    <body style="background:#0f172a;color:white;text-align:center;font-family:sans-serif;">
    <h2>🚀 Ultimate TradeFusion</h2>
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
