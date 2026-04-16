import requests
from flask import Flask, jsonify

app = Flask(__name__)

# ✅ Binance uses THIS format
PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "XRPUSDT",
    "BNBUSDT",
    "SOLUSDT"
]

last_error = None


# =========================
# 📊 GET DATA FROM BINANCE
# =========================
def get_price(symbol):
    global last_error
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=50"
        res = requests.get(url).json()

        if not isinstance(res, list):
            last_error = res
            return None

        closes = [float(x[4]) for x in res]  # close price
        return closes

    except Exception as e:
        last_error = str(e)
        return None


# =========================
# 📈 RSI CALCULATION
# =========================
def calculate_rsi(data, period=14):
    gains = []
    losses = []

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
            "tp": round(price * 1.01, 6),
            "sl": round(price * 0.99, 6),
            "quality": "🔥 STRONG",
            "confidence": 90,
            "rsi": round(rsi, 2)
        }

    elif rsi > 75:
        return {
            "symbol": symbol,
            "direction": "SELL",
            "entry": price,
            "tp": round(price * 0.99, 6),
            "sl": round(price * 1.01, 6),
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
            "tp": round(price * 1.005, 6),
            "sl": round(price * 0.995, 6),
            "quality": "⚡ MEDIUM",
            "confidence": 70,
            "rsi": round(rsi, 2)
        }

    elif rsi > 60:
        return {
            "symbol": symbol,
            "direction": "SELL",
            "entry": price,
            "tp": round(price * 0.995, 6),
            "sl": round(price * 1.005, 6),
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
            "tp": round(price * (1.002 if direction == "BUY" else 0.998), 6),
            "sl": round(price * (0.998 if direction == "BUY" else 1.002), 6),
            "quality": "⚠️ LOW",
            "confidence": 50,
            "rsi": round(rsi, 2)
        }


# =========================
# 🌐 ROUTES
# =========================
@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "message": "🔥 Binance Signal Engine Active",
        "pairs": PAIRS
    })


@app.route("/signals")
def signals():
    results = []

    for pair in PAIRS:
        signal = generate_signal(pair)
        results.append(signal)

    return jsonify(results)


@app.route("/status")
def status():
    return jsonify({
        "running": True,
        "pairs": len(PAIRS),
        "last_error": last_error
    })


# =========================
# 🚀 START
# =========================
app.run(host="0.0.0.0", port=10000)
