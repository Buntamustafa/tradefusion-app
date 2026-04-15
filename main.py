import requests
import pandas as pd
import websocket
import json
import threading
import time
from flask import Flask, jsonify

app = Flask(__name__)

# ==============================
# CONFIG
# ==============================
SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
TIMEFRAMES = ["1h", "15m", "5m"]

market_data = {
    sym: {tf: [] for tf in TIMEFRAMES}
    for sym in SYMBOLS
}

signals_cache = []
last_signals = {}

# ==============================
# FETCH HISTORICAL (REST)
# ==============================
def fetch_historical(symbol, tf):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf}&limit=200"
        data = requests.get(url, timeout=10).json()

        candles = []
        for d in data:
            candles.append({
                "open": float(d[1]),
                "high": float(d[2]),
                "low": float(d[3]),
                "close": float(d[4]),
                "volume": float(d[5])
            })

        market_data[symbol][tf] = candles
    except Exception as e:
        print("REST ERROR:", e)

# ==============================
# WEBSOCKET
# ==============================
def on_message(ws, message):
    try:
        data = json.loads(message)

        if "data" in data and "k" in data["data"]:
            k = data["data"]["k"]
            symbol = k["s"]

            candle = {
                "open": float(k["o"]),
                "high": float(k["h"]),
                "low": float(k["l"]),
                "close": float(k["c"]),
                "volume": float(k["v"])
            }

            market_data[symbol]["5m"].append(candle)

            if len(market_data[symbol]["5m"]) > 200:
                market_data[symbol]["5m"].pop(0)

    except Exception as e:
        print("WS ERROR:", e)

def start_ws():
    while True:
        try:
            streams = [f"{sym.lower()}@kline_5m" for sym in SYMBOLS]
            url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"

            ws = websocket.WebSocketApp(url, on_message=on_message)
            ws.run_forever()
        except Exception as e:
            print("WS RECONNECT:", e)
            time.sleep(5)

# ==============================
# INDICATORS
# ==============================
def add_indicators(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    df["range"] = df["high"] - df["low"]
    df["volatility"] = df["range"].rolling(14).mean()
    return df

# ==============================
# STRATEGIES
# ==============================
def detect_trend(df):
    return "UP" if df["ema50"].iloc[-1] > df["ema200"].iloc[-1] else "DOWN"

def strong_trend(df):
    return abs(df["ema50"].iloc[-1] - df["ema200"].iloc[-1]) > df["close"].iloc[-1] * 0.002

def detect_bos(df):
    return df["high"].iloc[-1] > df["high"].rolling(10).max().iloc[-2]

def detect_fvg(df):
    return df["low"].iloc[-1] > df["high"].iloc[-3]

def liquidity_sweep(df):
    return df["low"].iloc[-1] < df["low"].rolling(10).min().iloc[-2]

def order_block(df):
    last = df.iloc[-2]
    return last["close"] < last["open"]

def candle_confirmation(df, trend):
    last = df.iloc[-1]
    return last["close"] > last["open"] if trend == "UP" else last["close"] < last["open"]

def high_volatility(df):
    return df["volatility"].iloc[-1] > df["volatility"].rolling(50).mean().iloc[-1]

# ==============================
# MULTI-TIMEFRAME ANALYSIS
# ==============================
def analyze_symbol(symbol):
    score = 0
    confirmations = []
    trends = []

    for tf in TIMEFRAMES:
        df = pd.DataFrame(market_data[symbol][tf])

        if len(df) < 50:
            return 0, "NONE", []

        df = add_indicators(df)
        trend = detect_trend(df)
        trends.append(trend)

        weight = 2 if tf == "1h" else 1.5 if tf == "15m" else 1

        if detect_bos(df):
            score += 20 * weight
            confirmations.append(f"BOS({tf})")

        if detect_fvg(df):
            score += 20 * weight
            confirmations.append(f"FVG({tf})")

        if liquidity_sweep(df):
            score += 15 * weight
            confirmations.append(f"Liq({tf})")

        if order_block(df):
            score += 10 * weight
            confirmations.append(f"OB({tf})")

        if candle_confirmation(df, trend):
            score += 10 * weight
            confirmations.append(f"Candle({tf})")

        if strong_trend(df):
            score += 15 * weight
            confirmations.append(f"StrongTrend({tf})")

        if high_volatility(df):
            score += 10 * weight
            confirmations.append(f"Volatility({tf})")

    if trends.count("UP") >= 2:
        score += 25
        trend = "UP"
    else:
        score += 25
        trend = "DOWN"

    return int(score), trend, confirmations

# ==============================
# CLASSIFICATION (EXPANDED)
# ==============================
def classify(score):
    if score >= 130:
        return "🔥 ELITE", 92
    elif score >= 110:
        return "💪 STRONG", 85
    elif score >= 90:
        return "⚖️ MEDIUM", 75
    elif score >= 70:
        return "📉 LOW", 65
    elif score >= 50:
        return "🔻 LOWER", 55
    else:
        return "⚠️ LOWEST", 45

# ==============================
# DUPLICATE FILTER
# ==============================
def is_duplicate(symbol, trend, entry):
    key = f"{symbol}_{trend}"

    if key in last_signals:
        last_entry = last_signals[key]
        if abs(entry - last_entry) / entry < 0.002:
            return True

    last_signals[key] = entry
    return False

# ==============================
# STRICT FILTER (UNCHANGED)
# ==============================
def final_filter(score, confirmations):
    required = ["BOS", "FVG", "StrongTrend"]
    hits = sum(any(req in c for c in confirmations) for req in required)
    return score >= 100 and hits >= 2

# ==============================
# SIGNAL GENERATION
# ==============================
def generate_signal(symbol):
    score, trend, confirmations = analyze_symbol(symbol)

    df = pd.DataFrame(market_data[symbol]["5m"])
    if len(df) < 50:
        return None

    price = df["close"].iloc[-1]

    if is_duplicate(symbol, trend, price):
        return None

    quality, confidence = classify(score)
    tradable = final_filter(score, confirmations)

    if trend == "UP":
        tp = price * 1.02
        sl = price * 0.995
    else:
        tp = price * 0.98
        sl = price * 1.005

    return {
        "symbol": symbol,
        "trend": trend,
        "entry": round(price, 4),
        "tp": round(tp, 4),
        "sl": round(sl, 4),
        "quality": quality,
        "confidence": confidence,
        "score": score,
        "confirmations": confirmations,
        "tradable": tradable
    }

# ==============================
# LOOP
# ==============================
def signal_loop():
    global signals_cache

    while True:
        new_signals = []

        for sym in SYMBOLS:
            sig = generate_signal(sym)
            if sig:
                new_signals.append(sig)

        signals_cache = new_signals
        time.sleep(5)

# ==============================
# ROUTES
# ==============================
@app.route("/")
def home():
    return "AI Crypto Bot Running 🚀"

@app.route("/signals")
def signals():
    return jsonify(signals_cache)

@app.route("/status")
def status():
    return jsonify({"status": "RUNNING"})

# ==============================
# START
# ==============================
def start_bot():
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            fetch_historical(sym, tf)

    threading.Thread(target=start_ws, daemon=True).start()
    threading.Thread(target=signal_loop, daemon=True).start()

if __name__ == "__main__":
    start_bot()
    app.run(host="0.0.0.0", port=10000)
