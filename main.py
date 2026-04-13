import requests
import time
import threading
import os
from flask import Flask, jsonify

app = Flask(__name__)

# ===============================
# 🔐 CONFIG
# ===============================
API_KEY = os.getenv("TWELVE_API_KEY")

if not API_KEY:
    print("❌ ERROR: TWELVE_API_KEY is NOT SET")

SYMBOLS = [
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "BTC/USD",
    "ETH/USD",
    "XAU/USD",
    "XTI/USD"
]

signals = []
api_status = {
    "working": False,
    "last_error": None
}

# ===============================
# 📊 INDICATORS (UNCHANGED)
# ===============================
def calculate_rsi(closes):
    gains, losses = [], []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains)/len(gains) if gains else 0
    avg_loss = sum(losses)/len(losses) if losses else 0

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_ema(closes, period=5):
    return sum(closes[-period:]) / period


# ===============================
# 🧠 STRATEGY (UNCHANGED)
# ===============================
def detect_structure(closes):
    if closes[-1] > closes[-2] > closes[-3]:
        return "UPTREND"
    elif closes[-1] < closes[-2] < closes[-3]:
        return "DOWNTREND"
    return "RANGE"


def detect_bos(closes):
    return closes[-1] > max(closes[:-1]) or closes[-1] < min(closes[:-1])


def detect_liquidity_sweep(closes):
    high = max(closes[:-1])
    low = min(closes[:-1])

    if closes[-2] > high and closes[-1] < high:
        return "SELL"
    if closes[-2] < low and closes[-1] > low:
        return "BUY"
    return None


def detect_engulfing(closes):
    if closes[-1] > closes[-2] and closes[-2] < closes[-3]:
        return "BUY"
    if closes[-1] < closes[-2] and closes[-2] > closes[-3]:
        return "SELL"
    return None


def detect_support_resistance(closes):
    return min(closes[-10:]), max(closes[-10:])


# ===============================
# 🔍 ANALYSIS (UNCHANGED)
# ===============================
def analyze(symbol, values):
    try:
        closes = [float(v["close"]) for v in values[::-1]]

        ema = calculate_ema(closes)
        rsi = calculate_rsi(closes)

        structure = detect_structure(closes)
        bos = detect_bos(closes)
        sweep = detect_liquidity_sweep(closes)
        candle = detect_engulfing(closes)

        support, resistance = detect_support_resistance(closes)

        direction = None
        strength = 0

        if structure == "UPTREND":
            direction = "BUY"
            strength += 20
        elif structure == "DOWNTREND":
            direction = "SELL"
            strength += 20

        if bos:
            strength += 20

        if sweep == direction:
            strength += 25

        if candle == direction:
            strength += 20

        if direction == "BUY" and closes[-1] > ema:
            strength += 10
        if direction == "SELL" and closes[-1] < ema:
            strength += 10

        if direction == "BUY" and rsi < 40:
            strength += 10
        if direction == "SELL" and rsi > 60:
            strength += 10

        if direction == "BUY" and closes[-1] <= support * 1.01:
            strength += 10
        if direction == "SELL" and closes[-1] >= resistance * 0.99:
            strength += 10

        if strength < 40:
            return None

        if strength >= 90:
            quality = "💎 ELITE"
        elif strength >= 75:
            quality = "🔥 STRONG"
        elif strength >= 50:
            quality = "⚡ MEDIUM"
        else:
            quality = "🟡 SCALP"

        return {
            "symbol": symbol,
            "direction": direction,
            "entry": closes[-1],
            "quality": quality,
            "strength": strength,
            "rsi": round(rsi, 2),
            "structure": structure
        }

    except Exception as e:
        print(f"❌ Analyze error ({symbol}):", e)
        return None


# ===============================
# 🔄 BOT LOOP (FIXED)
# ===============================
def run_bot():
    global signals, api_status

    while True:
        try:
            if not API_KEY:
                api_status["working"] = False
                api_status["last_error"] = "Missing API key"
                time.sleep(10)
                continue

            symbols_str = ",".join(SYMBOLS)

            url = f"https://api.twelvedata.com/time_series?symbol={symbols_str}&interval=1min&outputsize=20&apikey={API_KEY}"

            response = requests.get(url, timeout=10)
            data = response.json()

            # ✅ Check API error
            if "code" in data:
                api_status["working"] = False
                api_status["last_error"] = data.get("message")
                print("❌ API ERROR:", data)
                time.sleep(15)
                continue

            api_status["working"] = True
            api_status["last_error"] = None

            new_signals = []

            for symbol in SYMBOLS:
                if symbol in data and "values" in data[symbol]:
                    result = analyze(symbol, data[symbol]["values"])
                    if result:
                        new_signals.append(result)

            signals = new_signals

            print("✅ Signals:", len(signals))

        except Exception as e:
            api_status["working"] = False
            api_status["last_error"] = str(e)
            print("❌ LOOP ERROR:", e)

        time.sleep(15)


# ===============================
# 🌐 ROUTES (ADDED HEALTH CHECK)
# ===============================
@app.route("/")
def home():
    return "🚀 Trading Bot Running"

@app.route("/signals")
def get_signals():
    return jsonify(signals)

@app.route("/status")
def status():
    return jsonify({
        "signals_count": len(signals),
        "api_working": api_status["working"]
    })

@app.route("/health")
def health():
    return jsonify(api_status)


# ===============================
# 🚀 START
# ===============================
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
