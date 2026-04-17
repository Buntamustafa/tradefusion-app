import requests
import time
import os
from flask import Flask, jsonify

app = Flask(__name__)

TWELVE_API_KEY = os.getenv("TWELVE_API_KEY")
ALPHA_API_KEY = os.getenv("ALPHA_API_KEY")

FOREX_PAIRS = ["EUR/USD", "GBP/USD"]
CRYPTO_IDS = ["bitcoin", "ethereum", "ripple"]

CACHE = {
    "signals": [],
    "last_update": 0,
    "cycle": 0
}

CACHE_TTL = 120


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
# FOREX
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
# CRYPTO APIs
# =========================
def fetch_coingecko():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(CRYPTO_IDS),
        "vs_currencies": "usd"
    }
    return safe_request(url, params)


def fetch_cryptocompare():
    url = "https://min-api.cryptocompare.com/data/pricemulti"
    symbols = ",".join([c[:3].upper() for c in CRYPTO_IDS])
    params = {
        "fsyms": symbols,
        "tsyms": "USD"
    }
    return safe_request(url, params)


def synthetic_price():
    return round(100 + (time.time() % 50), 2)


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
# TP/SL FIXED LOGIC
# =========================
def calculate_tp_sl(entry, trend):
    if trend == "BUY":
        tp = entry * 1.01
        sl = entry * 0.99
    elif trend == "SELL":
        tp = entry * 0.99   # BELOW entry
        sl = entry * 1.01   # ABOVE entry
    else:
        tp = entry
        sl = entry

    return round(tp, 5), round(sl, 5)


# =========================
# GENERATE SIGNALS
# =========================
def generate_signals():
    signals = []
    CACHE["cycle"] += 1

    print("🔄 Generating signals...")

    # ===== FOREX =====
    for pair in FOREX_PAIRS:

        if CACHE["cycle"] % 2 == 0:
            prices = fetch_twelve(pair) or fetch_alpha(pair)
        else:
            prices = fetch_alpha(pair) or fetch_twelve(pair)

        if not prices:
            prices = [1 + i * 0.001 for i in range(5)]

        trend, confidence = analyze(prices)
        entry = prices[-1]

        tp, sl = calculate_tp_sl(entry, trend)

        signals.append({
            "symbol": pair,
            "trend": trend,
            "entry": round(entry, 5),
            "tp": tp,
            "sl": sl,
            "confidence": confidence
        })

    # ===== CRYPTO =====
    cg = fetch_coingecko()
    cc = None

    if not cg:
        cc = fetch_cryptocompare()

    for coin in CRYPTO_IDS:
        price = None

        if cg:
            price = cg.get(coin, {}).get("usd")

        if not price and cc:
            symbol = coin[:3].upper()
            price = cc.get(symbol, {}).get("USD")

        if not price:
            price = synthetic_price()

        tp, sl = calculate_tp_sl(price, "BUY")

        signals.append({
            "symbol": coin.upper(),
            "trend": "BUY",
            "entry": round(price, 2),
            "tp": tp,
            "sl": sl,
            "confidence": 60
        })

    return signals


# =========================
# UPDATE
# =========================
def update_if_needed():
    now = time.time()

    if now - CACHE["last_update"] > CACHE_TTL:
        try:
            CACHE["signals"] = generate_signals()
            CACHE["last_update"] = now
        except Exception as e:
            print("Update error:", e)


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
        "signals": len(CACHE["signals"]),
        "last_update": CACHE["last_update"],
        "cycle": CACHE["cycle"]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
