import requests
import time
import threading
import os
from flask import Flask, jsonify

app = Flask(__name__)

API_KEY = os.getenv("TWELVEDATA_API_KEY")

# 🔥 Add as many pairs as you want
PAIRS = [
    "BTC/USDT", "ETH/USDT", "XRP/USDT",
    "BNB/USDT", "SOL/USDT"
]

signals_store = []
last_error = None


# =========================
# 📊 DATA FETCH
# =========================
def get_price(symbol):
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&outputsize=50&apikey={API_KEY}"
        res = requests.get(url).json()

        if "values" not in res:
            return None

        closes = [float(x["close"]) for x in res["values"]]
        return closes[::-1]

    except Exception as e:
        global last_error
        last_error = str(e)
        return None


# =========================
# 📈 RSI CALCULATION
# =========================
def calculate_rsi(data, period=14):
    gains, losses = [], []

    for i in range(1, len(data)):
        diff = data[i] - data[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))

    if len(gains) < period:
        return 50

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# =========================
# 🚨 SIGNAL GENERATOR
# =========================
def generate_signal(symbol):
    data = get_price(symbol)

    if not data:
        return {
            "symbol": symbol,
            "status": "no_data"
        }

    price = data[-1]
    rsi = calculate_rsi(data)

    # 🔥 STRONG
    if rsi < 25:
        return {
            "symbol": symbol,
            "direction": "BUY",
            "entry": price,
            "tp": price * 1.01,
            "sl": price * 0.99,
            "quality": "🔥 STRONG",
            "confidence": 90,
            "rsi": round(rsi, 2)
        }

    elif rsi > 75:
        return {
            "symbol": symbol,
            "direction": "SELL",
            "entry": price,
            "tp": price * 0.99,
            "sl": price * 1.01,
            "quality": "🔥 STRONG",
            "confidence": 90,
            "rsi": round(rsi, 2)
        }

    # ⚡ MEDIUM
    elif rsi < 40:
        return {
            "symbol": symbol,
            "direction": "BUY",
            "entry": price,
            "tp": price * 1.005,
            "sl": price * 0.995,
            "quality": "⚡ MEDIUM",
            "confidence": 70,
            "rsi": round(rsi, 2)
        }

    elif rsi > 60:
        return {
            "symbol": symbol,
            "direction": "SELL",
            "entry": price,
            "tp": price * 0.995,
            "sl": price * 1.005,
            "quality": "⚡ MEDIUM",
            "confidence": 70,
            "rsi": round(rsi, 2)
        }

    # ⚠️ LOW (ALWAYS SEND)
    else:
        direction = "BUY" if rsi < 50 else "SELL"

        return {
            "symbol": symbol,
            "direction": direction,
            "entry": price,
            "tp": price * 1.002 if direction == "BUY" else price * 0.998,
            "sl": price * 0.998 if direction == "BUY" else price * 1.002,
            "quality": "⚠️ LOW",
            "confidence": 50,
            "rsi": round(rsi, 2)
        }


# =========================
# 🔁 BACKGROUND SCANNER
# =========================
def signal_loop():
    global signals_store

    while True:
        new_signals = []

        for pair in PAIRS:
            signal = generate_signal(pair)
            new_signals.append(signal)

        signals_store = new_signals

        print("✅ Signals updated:", new_signals)

        # ⏱️ Adjust speed here (IMPORTANT for API limits)
        time.sleep(30)  # every 30 seconds


# =========================
# 🌐 API ROUTES
# =========================
@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "message": "🔥 Signal engine active",
        "pairs": PAIRS
    })


@app.route("/signals")
def signals():
    return jsonify(signals_store)


@app.route("/status")
def status():
    return jsonify({
        "running": True,
        "signals_count": len(signals_store),
        "last_error": last_error
    })


# =========================
# 🚀 START BOT
# =========================
if __name__ == "__main__":
    thread = threading.Thread(target=signal_loop)
    thread.daemon = True
    thread.start()

    app.run(host="0.0.0.0", port=10000)
