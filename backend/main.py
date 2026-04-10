from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import requests
import pandas as pd
import ta
import os
import time

app = Flask(__name__)
CORS(app)

PAIRS = {
    "EUR/USD": {"type": "forex", "symbol": "EUR/USD"},
    "BTC/USD": {"type": "crypto", "symbol": "BTCUSDT"},
    "XAU/USD": {"type": "forex", "symbol": "XAU/USD"}
}

API_KEY = os.getenv("TWELVE_API_KEY")

CACHE = {}
TRADES = {}
CACHE_TIME = 60

# ===============================
# SAFE CACHE
# ===============================
def get_cache(key):
    try:
        if key in CACHE:
            data, t = CACHE[key]
            if time.time() - t < CACHE_TIME:
                return data
    except:
        pass
    return None

def set_cache(key, value):
    try:
        CACHE[key] = (value, time.time())
    except:
        pass

# ===============================
# SAFE FETCH
# ===============================
def fetch_twelve(symbol):
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {"symbol": symbol,"interval": "5min","apikey": API_KEY,"outputsize": 100}
        data = requests.get(url, params=params, timeout=10).json()

        if "values" not in data:
            return None

        df = pd.DataFrame(data["values"]).iloc[::-1]

        for col in ["open","close","high","low"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna()

        if len(df) < 50:
            return None

        return df

    except:
        return None


def fetch_binance(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=100"
        data = requests.get(url, timeout=10).json()

        if not isinstance(data, list):
            return None

        df = pd.DataFrame(data)

        if df.empty:
            return None

        df.columns = [
            "time","open","high","low","close","volume",
            "close_time","qav","trades","taker_base","taker_quote","ignore"
        ]

        for col in ["open","close","high","low"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna()

        return df

    except:
        return None


def get_data(name, info):
    try:
        cached = get_cache(name)

        if info["type"] == "crypto":
            df = fetch_binance(info["symbol"])
        else:
            df = fetch_twelve(info["symbol"])

        if df is not None:
            set_cache(name, df)
            return df

        return cached

    except:
        return None

# ===============================
# SAFE ANALYSIS
# ===============================
def analyze(df):
    try:
        df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
        df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
        df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

        df = df.dropna()

        if len(df) < 10:
            return None, None, None

        last = df.iloc[-1]

        trend = "BUY" if last["ema20"] > last["ema50"] else "SELL"

        return trend, float(last["rsi"]), float(last["close"])

    except:
        return None, None, None

# ===============================
# SAFE ENTRY
# ===============================
def refine_entry(price):
    return price

# ===============================
# SAFE TRADE TRACKER
# ===============================
def track_trade(pair, action, entry, price):
    try:
        if pair not in TRADES:
            TRADES[pair] = {"entry": entry, "action": action, "status": "PENDING"}

        trade = TRADES[pair]

        if trade["status"] == "PENDING":
            if action == "BUY" and price <= entry:
                trade["status"] = "FILLED"
            elif action == "SELL" and price >= entry:
                trade["status"] = "FILLED"
            elif abs(price - entry) / entry > 0.01:
                trade["status"] = "MISSED"

        return trade["status"]

    except:
        return "ERROR"

# ===============================
# SIGNAL ENGINE (SAFE)
# ===============================
def generate_signal(df, pair):
    try:
        trend, rsi, price = analyze(df)

        if trend is None:
            return {"message": "No valid data"}

        entry = refine_entry(price)

        if trend == "BUY" and rsi > 50:
            status = track_trade(pair, "BUY", entry, price)
            return {
                "action": "BUY",
                "entry": round(entry,4),
                "status": status,
                "confidence": "70%"
            }

        if trend == "SELL" and rsi < 50:
            status = track_trade(pair, "SELL", entry, price)
            return {
                "action": "SELL",
                "entry": round(entry,4),
                "status": status,
                "confidence": "70%"
            }

        return {"message": "Waiting for setup"}

    except Exception as e:
        return {"error": str(e)}

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
                results.append({"pair": name, "message": "No data"})
                continue

            signal = generate_signal(df, name)
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
    <body style="background:#0f172a;color:white;text-align:center;">
    <h2>🛡 SAFE TRADING BOT</h2>
    <div id="data"></div>

    <script>
    async function load(){
        let res = await fetch('/signals');
        let data = await res.json();

        let html = "";
        data.forEach(d=>{
            html += `<p><b>${d.pair}</b>: ${d.action || d.message || d.error}</p>`;
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
