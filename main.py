import requests
import time
import threading
import os
from flask import Flask, jsonify

app = Flask(__name__)

# ================= CONFIG =================
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
REFRESH_INTERVAL = 60  # seconds

# ================= GLOBAL STATE =================
signals_cache = []
last_update = 0
bot_status = {
    "running": True,
    "last_error": None,
    "last_update": None
}

# ================= FETCH FUNCTIONS =================

def fetch_forex(pair):
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={pair}&interval=1min&outputsize=20&apikey={TWELVEDATA_API_KEY}"
        r = requests.get(url, timeout=10)
        data = r.json()

        if "values" not in data:
            return None

        closes = [float(x["close"]) for x in data["values"]]

        return closes[::-1]  # oldest -> newest

    except Exception as e:
        bot_status["last_error"] = str(e)
        return None


def fetch_crypto(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days=1"
        r = requests.get(url, timeout=10)
        data = r.json()

        prices = [p[1] for p in data["prices"]]

        return prices[-20:]

    except Exception as e:
        bot_status["last_error"] = str(e)
        return None


# ================= STRATEGY =================

def calculate_signal(prices, symbol):
    if not prices or len(prices) < 10:
        return {"symbol": symbol, "status": "no_data"}

    current = prices[-1]
    ma_short = sum(prices[-5:]) / 5
    ma_long = sum(prices[-10:]) / 10

    if ma_short > ma_long:
        trend = "BUY"
    elif ma_short < ma_long:
        trend = "SELL"
    else:
        trend = "WAIT"

    confidence = int(abs(ma_short - ma_long) / current * 10000)
    confidence = min(confidence, 95)

    return {
        "symbol": symbol,
        "trend": trend,
        "entry": round(current, 5),
        "tp": round(current * 1.01, 5),
        "sl": round(current * 0.99, 5),
        "confidence": confidence,
        "timestamp": int(time.time())
    }


# ================= SIGNAL GENERATOR =================

def generate_signals():
    global signals_cache, last_update

    new_signals = []

    try:
        # ===== FOREX =====
        forex_pairs = ["EUR/USD", "GBP/USD"]

        for pair in forex_pairs:
            prices = fetch_forex(pair)
            signal = calculate_signal(prices, pair)
            new_signals.append(signal)
            time.sleep(1)  # prevent rate limit

        # ===== CRYPTO =====
        crypto_map = {
            "bitcoin": "BITCOIN",
            "ethereum": "ETHEREUM",
            "ripple": "RIPPLE"
        }

        for coin_id, name in crypto_map.items():
            prices = fetch_crypto(coin_id)
            signal = calculate_signal(prices, name)
            new_signals.append(signal)
            time.sleep(1)

        signals_cache = new_signals
        last_update = time.time()
        bot_status["last_update"] = int(last_update)
        bot_status["last_error"] = None

    except Exception as e:
        bot_status["last_error"] = str(e)


# ================= BACKGROUND LOOP =================

def run_bot():
    while True:
        try:
            if time.time() - last_update > REFRESH_INTERVAL:
                generate_signals()
        except Exception as e:
            bot_status["last_error"] = str(e)

        time.sleep(5)


# ================= ROUTES =================

@app.route("/")
def home():
    return jsonify({"message": "🚀 AI Trading Bot Running"})


@app.route("/signals")
def get_signals():
    # Prevent stale data
    if time.time() - last_update > 120:
        return jsonify({
            "status": "stale",
            "message": "⚠️ Signals outdated, waiting for refresh..."
        })

    return jsonify(signals_cache)


@app.route("/status")
def status():
    return jsonify({
        "running": bot_status["running"],
        "last_update": bot_status["last_update"],
        "last_error": bot_status["last_error"],
        "signals_count": len(signals_cache)
    })


# ================= START BOT =================

threading.Thread(target=run_bot, daemon=True).start()

# ================= RUN =================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
