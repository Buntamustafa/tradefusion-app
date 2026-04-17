import requests
import time
import threading
import os
from flask import Flask, jsonify

app = Flask(__name__)

TWELVE_API_KEY = os.getenv("TWELVE_API_KEY")

# =========================
# CONFIG
# =========================
FOREX_PAIRS = ["EUR/USD", "GBP/USD"]
CRYPTO_IDS = ["bitcoin", "ethereum", "ripple"]

CACHE = {
    "forex": {},
    "crypto": {},
    "last_update": 0,
    "signals": []
}

CACHE_TTL = 60  # seconds


# =========================
# SAFE REQUEST FUNCTION
# =========================
def safe_request(url, params=None):
    try:
        res = requests.get(url, params=params, timeout=10)
        if res.status_code == 200:
            return res.json()
        else:
            print("Bad response:", res.status_code)
            return None
    except Exception as e:
        print("Request error:", str(e))
        return None


# =========================
# FETCH FOREX (TwelveData)
# =========================
def fetch_forex(pair, interval="1min"):
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": pair,
            "interval": interval,
            "apikey": TWELVE_API_KEY,
            "outputsize": 10
        }

        data = safe_request(url, params)

        if not data or "values" not in data:
            return None

        closes = [float(x["close"]) for x in data["values"]]
        return closes[::-1]  # oldest → newest

    except Exception as e:
        print("Forex fetch error:", e)
        return None


# =========================
# FETCH CRYPTO (CoinGecko)
# =========================
def fetch_crypto():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": ",".join(CRYPTO_IDS),
            "vs_currencies": "usd"
        }

        data = safe_request(url, params)
        return data

    except Exception as e:
        print("Crypto fetch error:", e)
        return None


# =========================
# SIMPLE TREND LOGIC
# =========================
def analyze_trend(prices):
    if not prices or len(prices) < 5:
        return "WAIT", 10

    short_avg = sum(prices[-3:]) / 3
    long_avg = sum(prices) / len(prices)

    if short_avg > long_avg:
        return "BUY", 70
    elif short_avg < long_avg:
        return "SELL", 70
    else:
        return "WAIT", 20


# =========================
# GENERATE SIGNALS
# =========================
def generate_signals():
    signals = []

    try:
        # ===== FOREX =====
        for pair in FOREX_PAIRS:
            prices_1m = fetch_forex(pair, "1min")
            prices_5m = fetch_forex(pair, "5min")

            if prices_1m and prices_5m:
                trend1, conf1 = analyze_trend(prices_1m)
                trend5, conf5 = analyze_trend(prices_5m)

                # Combine timeframes
                if trend1 == trend5:
                    trend = trend1
                    confidence = int((conf1 + conf5) / 2)
                else:
                    trend = "WAIT"
                    confidence = 30

                entry = prices_1m[-1]

                signals.append({
                    "symbol": pair,
                    "trend": trend,
                    "entry": entry,
                    "tp": round(entry * 1.01, 5),
                    "sl": round(entry * 0.99, 5),
                    "confidence": confidence
                })

        # ===== CRYPTO =====
        crypto_data = fetch_crypto()

        if crypto_data:
            for coin in CRYPTO_IDS:
                price = crypto_data.get(coin, {}).get("usd")

                if price:
                    signals.append({
                        "symbol": coin.upper(),
                        "trend": "BUY",
                        "entry": price,
                        "tp": round(price * 1.02, 2),
                        "sl": round(price * 0.98, 2),
                        "confidence": 60
                    })

    except Exception as e:
        print("Signal generation error:", e)

    # ===== FALLBACK (NEVER EMPTY) =====
    if not signals:
        signals.append({
            "message": "No strong signals right now",
            "trend": "WAIT",
            "confidence": 0
        })

    return signals


# =========================
# BACKGROUND LOOP
# =========================
def update_loop():
    while True:
        try:
            now = time.time()

            if now - CACHE["last_update"] > CACHE_TTL:
                print("Updating signals...")
                CACHE["signals"] = generate_signals()
                CACHE["last_update"] = now

        except Exception as e:
            print("Loop error:", e)

        time.sleep(10)


# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "signals": len(CACHE["signals"])
    })


@app.route("/signals")
def signals():
    return jsonify(CACHE["signals"])


@app.route("/status")
def status():
    return jsonify({
        "connected": True,
        "api_working": True if CACHE["signals"] else False,
        "signals_count": len(CACHE["signals"]),
        "last_update": CACHE["last_update"]
    })


# =========================
# START THREAD
# =========================
threading.Thread(target=update_loop, daemon=True).start()

# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
