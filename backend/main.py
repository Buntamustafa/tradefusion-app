from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import requests
import pandas as pd
import ta
import os
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)

PAIRS = {
    "EUR/USD": {"type": "forex", "symbol": "EUR/USD"},
    "BTC/USD": {"type": "crypto", "symbol": "BTCUSDT"},
    "XAU/USD": {"type": "forex", "symbol": "XAU/USD"}
}

API_KEY = os.getenv("TWELVE_API_KEY")

CACHE = {}
TRADES = {}  # store active trades
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
# FETCH DATA
# ===============================
def fetch_twelve(symbol):
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {"symbol": symbol,"interval": "5min","apikey": API_KEY,"outputsize": 100}
        data = requests.get(url, params=params).json()

        if "values" not in data:
            return None

        df = pd.DataFrame(data["values"]).iloc[::-1]

        for col in ["open","close","high","low"]:
            df[col] = df[col].astype(float)

        return df
    except:
        return None

def fetch_binance(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100"
        data = requests.get(url).json()

        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "close_time","qav","trades","taker_base","taker_quote","ignore"
        ])

        for col in ["open","close","high","low"]:
            df[col] = df[col].astype(float)

        return df
    except:
        return None

def fetch_bybit(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval=5&limit=100"
        data = requests.get(url).json()

        candles = data["result"]["list"]

        df = pd.DataFrame(candles, columns=[
            "time","open","high","low","close","volume","turnover"
        ]).iloc[::-1]

        for col in ["open","close","high","low"]:
            df[col] = df[col].astype(float)

        return df
    except:
        return None

def get_data(name, info):
    cached = get_cache(name)

    if info["type"] == "crypto":
        df = fetch_binance(info["symbol"]) or fetch_bybit(info["symbol"])
    else:
        df = fetch_twelve(info["symbol"])

    if df is not None and len(df) > 50:
        set_cache(name, df)
        return df

    return cached

# ===============================
# SMC DETECTION
# ===============================
def detect_fvg(df):
    if len(df) < 3:
        return None

    c1 = df.iloc[-3]
    c3 = df.iloc[-1]

    if c1["high"] < c3["low"]:
        return ("BULLISH", c1["high"], c3["low"])

    if c1["low"] > c3["high"]:
        return ("BEARISH", c3["high"], c1["low"])

    return None

def detect_order_block(df):
    prev = df.iloc[-2]

    if prev["close"] < prev["open"]:
        return ("BULLISH_OB", prev["low"], prev["high"])

    if prev["close"] > prev["open"]:
        return ("BEARISH_OB", prev["low"], prev["high"])

    return None

def detect_liquidity(df):
    last = df.iloc[-1]
    if last["high"] > df["high"].iloc[-5:-1].max():
        return "BUY_SIDE"
    if last["low"] < df["low"].iloc[-5:-1].min():
        return "SELL_SIDE"
    return None

def detect_bos(df):
    last = df.iloc[-1]
    if last["close"] > df["high"].iloc[-10:-1].max():
        return "BOS_BUY"
    if last["close"] < df["low"].iloc[-10:-1].min():
        return "BOS_SELL"
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

# ===============================
# ENTRY REFINEMENT
# ===============================
def refine_entry(fvg, ob, price):
    if fvg:
        _, low, high = fvg
        return (low + high) / 2

    if ob:
        _, low, high = ob
        return (low + high) / 2

    return price

# ===============================
# LIMIT EXECUTION TRACKER
# ===============================
def track_trade(pair, action, entry, current_price):
    if pair not in TRADES:
        TRADES[pair] = {
            "entry": entry,
            "action": action,
            "status": "PENDING"
        }

    trade = TRADES[pair]

    if trade["status"] == "PENDING":
        if action == "BUY" and current_price <= entry:
            trade["status"] = "FILLED"
        elif action == "SELL" and current_price >= entry:
            trade["status"] = "FILLED"

        elif abs(current_price - entry) / entry > 0.01:
            trade["status"] = "MISSED"

    return trade["status"]

# ===============================
# SIGNAL ENGINE
# ===============================
def generate_signal(df, pair):
    trend, rsi, price = analyze(df)

    fvg = detect_fvg(df)
    ob = detect_order_block(df)
    liquidity = detect_liquidity(df)
    bos = detect_bos(df)

    entry = refine_entry(fvg, ob, price)

    if all([fvg, ob, liquidity, bos]):
        if trend == "BUY" and liquidity == "SELL_SIDE":
            status = track_trade(pair, "BUY", entry, price)
            return {
                "action": "BUY",
                "entry": round(entry,4),
                "status": status,
                "strength": "SNIPER 🎯"
            }

        if trend == "SELL" and liquidity == "BUY_SIDE":
            status = track_trade(pair, "SELL", entry, price)
            return {
                "action": "SELL",
                "entry": round(entry,4),
                "status": status,
                "strength": "SNIPER 🎯"
            }

    return {"message": "Waiting for setup"}

# ===============================
# API
# ===============================
@app.route('/signals')
def signals():
    results = []

    for name, info in PAIRS.items():
        df = get_data(name, info)

        if df is None:
            results.append({"pair": name, "message": "No data"})
            continue

        signal = generate_signal(df, name)
        signal["pair"] = name
        results.append(signal)

    return jsonify(results)

# ===============================
# DASHBOARD
# ===============================
@app.route('/')
def dashboard():
    return render_template_string("""
    <html>
    <body style="background:#0f172a;color:white;text-align:center;">
    <h2>🚀 LIMIT EXECUTION BOT</h2>
    <div id="data"></div>

    <script>
    async function load(){
        let res = await fetch('/signals');
        let data = await res.json();

        let html = "";
        data.forEach(d=>{
            html += `<p><b>${d.pair}</b>: ${d.action || d.message} | ${d.status || ""}</p>`;
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
