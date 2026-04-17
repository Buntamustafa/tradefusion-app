import requests
import time
import os
from flask import Flask, jsonify

app = Flask(__name__)

# =========================
# API KEYS
# =========================
TWELVE_API_KEY = os.getenv("TWELVE_API_KEY")
ALPHA_API_KEY = os.getenv("ALPHA_API_KEY")

# =========================
# CONFIG
# =========================
FOREX_PAIRS = ["EUR/USD", "GBP/USD"]
CRYPTO_IDS = ["bitcoin", "ethereum", "ripple"]

CACHE = {
    "signals": [],
    "last_update": 0,
    "cycle": 0
}

CACHE_TTL = 120  # safer for rate limits

# =========================
# SAFE REQUEST
# =========================
def safe_request(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            print("Bad response:", r.status_code)
            return None
    except Exception as e:
        print("Request error:", e)
        return None

# =========================
# FOREX - TWELVEDATA
# =========================
def fetch_twelve(pair):
    if not TWELVE_API_KEY:
        return None

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": pair,
        "interval": "1min",
        "apikey": TWELVE_API_KEY,
        "outputsize": 5
    }

    data = safe_request(url, params)
    if data and "values" in data:
        return [float(x["close"]) for x in data["values"]][::-1]
    return None

# =========================
# FOREX - ALPHA VANTAGE
# =========================
def fetch_alpha(pair):
    if not ALPHA_API_KEY:
        return None

    base, quote = pair.split("/")
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "FX_INTRADAY",
        "from_symbol": base,
        "to_symbol": quote,
        "interval": "5min",
        "apikey": ALPHA_API_KEY
    }

    data = safe_request(url, params)
    key = "Time Series FX (5min)"

    if data and key in data:
        values = list(data[key].values())[:5]
        return [float(v["4. close"]) for v in values][::-1]

    return None

# =========================
# CRYPTO - COINGECKO
# =========================
def fetch_crypto():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(CRYPTO_IDS),
        "vs_currencies": "usd"
    }
    return safe_request(url, params)

# =========================
# FALLBACK (NO API)
# =========================
def synthetic_prices():
    base = 1.0 + (time.time() % 10) / 100
    return [base + i * 0.001 for i in range(5)]

# =========================
# ANALYSIS
# =========================
def analyze(prices):
    if not prices:
        return "WAIT", 10

    avg = sum(prices) / len(prices)
    last = prices[-1]

    if last > avg:
        return "BUY", 70
    elif last < avg:
        return "SELL", 70
    return "WAIT", 20

# =========================
# GENERATE SIGNALS
# =========================
def generate_signals():
    signals = []
    CACHE["cycle"] += 1

    print("🔄 Generating signals... Cycle:", CACHE["cycle"])

    for pair in FOREX_PAIRS:

        # Rotate APIs to avoid limits
        if CACHE["cycle"] % 2 == 0:
            prices = fetch_twelve(pair) or fetch_alpha(pair)
        else:
            prices = fetch_alpha(pair) or fetch_twelve(pair)

        # fallback if both fail
        if not prices:
            print("⚠️ Using synthetic data for", pair)
            prices = synthetic_prices()

        trend, confidence = analyze(prices)
        entry = prices[-1]

        signals.append({
            "symbol": pair,
            "trend": trend,
            "entry": round(entry, 5),
            "tp": round(entry * 1.01, 5),
            "sl": round(entry * 0.99, 5),
            "confidence": confidence
        })

    # ===== CRYPTO =====
    crypto = fetch_crypto()

    if crypto:
        for coin in CRYPTO_IDS:
            price = crypto.get(coin, {}).get("usd")
            if price:
                signals.append({
                    "symbol": coin.upper(),
                    "trend": "BUY",
                    "entry": price,
                    "tp": round(price * 1.02, 2),
                    "sl": round(price * 0.98, 2),
                    "confidence": 60
                })

    # FINAL SAFETY (NEVER EMPTY)
    if not signals:
        signals = [{
            "symbol": "SYSTEM",
            "trend": "WAIT",
            "entry": 0,
            "tp": 0,
            "sl": 0,
            "confidence": 0
        }]

    print("✅ Signals:", signals)
    return signals

# =========================
# UPDATE (NO THREAD)
# =========================
def update_if_needed():
    now = time.time()

    if now - CACHE["last_update"] > CACHE_TTL:
        try:
            CACHE["signals"] = generate_signals()
            CACHE["last_update"] = now
        except Exception as e:
            print("❌ Update error:", e)

# =========================
# ROUTES
# =========================
@app.route("/")
def home():
    return jsonify({"status": "running"})

@app.route("/signals")
def signals():
    update_if_needed()
    return jsonify(CACHE["signals"])

@app.route("/status")
def status():
    return jsonify({
        "api_keys": {
            "twelve": bool(TWELVE_API_KEY),
            "alpha": bool(ALPHA_API_KEY)
        },
        "signals_count": len(CACHE["signals"]),
        "last_update": CACHE["last_update"],
        "cycle": CACHE["cycle"]
    })

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
