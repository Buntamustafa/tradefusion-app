from flask import Flask, jsonify
from flask_cors import CORS
import requests
import pandas as pd
import ta
import os
import time
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ===============================
# CONFIG
# ===============================
API_KEY = os.getenv("TWELVE_API_KEY")

PAIRS = {
    "EUR/USD": {"type": "forex", "symbol": "EUR/USD"},
    "BTC/USD": {"type": "crypto", "symbol": "BTCUSDT"},
    "XAU/USD": {"type": "forex", "symbol": "XAU/USD"}
}

CACHE = {}
CACHE_DURATION = 60  # seconds

# ===============================
# RETRY SYSTEM
# ===============================
def fetch_with_retry(url, retries=3, delay=2):
    for attempt in range(retries):
        try:
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                return res.json()
        except:
            pass

        time.sleep(delay)

    raise Exception("API request failed after retries")

# ===============================
# KILL ZONE
# ===============================
def in_kill_zone():
    now = datetime.utcnow().hour
    return (7 <= now <= 10) or (12 <= now <= 15)

# ===============================
# NEWS FILTER
# ===============================
def high_impact_news():
    try:
        url = f"https://api.twelvedata.com/economic_calendar?importance=high&apikey={API_KEY}"
        res = fetch_with_retry(url)
        return "data" in res and len(res["data"]) > 0
    except:
        return False

# ===============================
# FETCH DATA
# ===============================
def get_data(symbol, interval, market_type):
    key = f"{symbol}_{interval}"
    now = time.time()

    # CACHE
    if key in CACHE and (now - CACHE[key]["time"] < CACHE_DURATION):
        return CACHE[key]["data"]

    # ===============================
    # CRYPTO → BINANCE
    # ===============================
    if market_type == "crypto":
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={'5m' if interval=='5min' else '15m'}&limit=100"
        data = fetch_with_retry(url)

        if not data or len(data) < 50:
            raise Exception("Binance returned insufficient data")

        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "close_time","qav","trades","taker_base","taker_quote","ignore"
        ])

    # ===============================
    # FOREX → TWELVEDATA
    # ===============================
    else:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey={API_KEY}"
        res = fetch_with_retry(url)

        if "values" not in res:
            raise Exception(res.get("message", "Data fetch failed"))

        df = pd.DataFrame(res["values"])
        df = df.iloc[::-1]

    # FORMAT
    df["open"] = df["open"].astype(float)
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    # SAVE CACHE
    CACHE[key] = {"data": df, "time": now}

    return df

# ===============================
# ENTRY CONFIRMATION
# ===============================
def confirmation(df):
    if len(df) < 2:
        return None

    last = df.iloc[-1]

    body = abs(last["close"] - last["open"])
    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick = min(last["open"], last["close"]) - last["low"]

    if lower_wick > body * 1.5:
        return "BUY"
    if upper_wick > body * 1.5:
        return "SELL"

    return None

# ===============================
# ANALYSIS (SAFE)
# ===============================
def analyze(df):
    if df is None or len(df) < 50:
        raise Exception("Not enough market data")

    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema20"] = ta.trend.EMAIndicator(df["close"], window=20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()

    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    trend = "BUY" if last["ema20"] > last["ema50"] else "SELL"
    rsi = last["rsi"]

    liquidity = None
    if last["low"] < prev["low"]:
        liquidity = "SELL_SIDE"
    elif last["high"] > prev["high"]:
        liquidity = "BUY_SIDE"

    fvg = None
    if prev["low"] > prev2["high"]:
        fvg = "BULLISH"
    elif prev["high"] < prev2["low"]:
        fvg = "BEARISH"

    bos = None
    if last["high"] > prev["high"] and prev["high"] > prev2["high"]:
        bos = "BULLISH"
    elif last["low"] < prev["low"] and prev["low"] < prev2["low"]:
        bos = "BEARISH"

    return {
        "trend": trend,
        "rsi": rsi,
        "liquidity": liquidity,
        "fvg": fvg,
        "bos": bos,
        "close": last["close"]
    }

# ===============================
# SIGNAL ENGINE (STRICT)
# ===============================
def generate_signal(df_5m, df_15m):

    a5 = analyze(df_5m)
    a15 = analyze(df_15m)
    confirm = confirmation(df_5m)

    trend_5m = a5["trend"]
    trend_15m = a15["trend"]
    rsi = a5["rsi"]
    entry = a5["close"]

    # OUTSIDE SESSION → STRICT SCALP
    if not in_kill_zone():

        if trend_5m == "BUY" and rsi < 60 and confirm == "BUY":
            signal = "BUY"
        elif trend_5m == "SELL" and rsi > 40 and confirm == "SELL":
            signal = "SELL"
        else:
            return {"message": "Waiting for high-probability setup"}

        if signal == "BUY":
            sl = entry * 0.997
            tp = entry * 1.01
        else:
            sl = entry * 1.003
            tp = entry * 0.99

        return {
            "action": signal,
            "entry": round(entry, 4),
            "sl": round(sl, 4),
            "tp": round(tp, 4),
            "confidence": "60%",
            "strength": "SCALP ⚡ (CONFIRMED)",
            "reason": f"Outside kill zone | Confirmed {signal} | RSI={round(rsi,1)}"
        }

    # INSIDE SESSION
    if high_impact_news():
        return {"message": "High impact news - stay out"}

    if trend_5m == trend_15m and confirm == trend_5m:
        signal = trend_5m
        strength = "STRONG"
    elif confirm:
        signal = confirm
        strength = "SCALP ⚡"
    else:
        return {"message": "Waiting for high-probability setup"}

    if signal == "BUY":
        sl = entry * 0.997
        tp = entry * 1.02
    else:
        sl = entry * 1.003
        tp = entry * 0.98

    return {
        "action": signal,
        "entry": round(entry, 4),
        "sl": round(sl, 4),
        "tp": round(tp, 4),
        "confidence": "70%",
        "strength": strength,
        "reason": f"{strength} | RSI={round(rsi,1)}"
    }

# ===============================
# ROUTES
# ===============================
@app.route('/')
def home():
    return "NEYLA.fx ULTRA STABLE 🚀"

@app.route('/signals')
def signals():
    results = []

    for name, info in PAIRS.items():
        try:
            df_5m = get_data(info["symbol"], "5min", info["type"])
            df_15m = get_data(info["symbol"], "15min", info["type"])

            signal = generate_signal(df_5m, df_15m)
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
