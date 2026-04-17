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
    "last_trend": {}
}

CACHE_TTL = 120


# =========================
# REQUEST
# =========================
def safe_request(url, params=None):
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        return None


# =========================
# FOREX FETCH
# =========================
def fetch_twelve(pair, interval="1min"):
    if not TWELVE_API_KEY:
        return None

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": pair,
        "interval": interval,
        "apikey": TWELVE_API_KEY,
        "outputsize": 20
    }

    data = safe_request(url, params)
    if data and "values" in data:
        return [float(x["close"]) for x in data["values"]][::-1]
    return None


# =========================
# CRYPTO (MULTI API)
# =========================
def fetch_coingecko():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(CRYPTO_IDS), "vs_currencies": "usd"}
    return safe_request(url, params)


def fetch_cryptocompare():
    url = "https://min-api.cryptocompare.com/data/pricemulti"
    params = {"fsyms": "BTC,ETH,XRP", "tsyms": "USD"}
    return safe_request(url, params)


def synthetic_price():
    return 100 + (time.time() % 50)


# =========================
# INDICATORS
# =========================
def ema(prices, period=10):
    k = 2 / (period + 1)
    ema_val = prices[0]
    for price in prices:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def rsi(prices, period=14):
    gains, losses = [], []

    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains[-period:]) / period if gains else 0.001
    avg_loss = sum(losses[-period:]) / period if losses else 0.001

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# =========================
# SMART ANALYSIS
# =========================
def analyze(prices_1m, prices_5m, symbol):
    if not prices_1m or not prices_5m:
        return "WAIT", 10

    ema1 = ema(prices_1m)
    ema5 = ema(prices_5m)
    current = prices_1m[-1]
    rsi_val = rsi(prices_1m)

    # Trend confirmation
    if current > ema1 and current > ema5 and rsi_val < 70:
        trend = "BUY"
    elif current < ema1 and current < ema5 and rsi_val > 30:
        trend = "SELL"
    else:
        trend = "WAIT"

    # Anti-flip (lock previous signal)
    last = CACHE["last_trend"].get(symbol)
    if last and last != trend and trend != "WAIT":
        trend = "WAIT"

    CACHE["last_trend"][symbol] = trend

    confidence = 80 if trend != "WAIT" else 40
    return trend, confidence


# =========================
# TP / SL
# =========================
def tp_sl(entry, trend):
    if trend == "BUY":
        return entry * 1.02, entry * 0.99
    elif trend == "SELL":
        return entry * 0.98, entry * 1.01
    return entry, entry


# =========================
# GENERATE SIGNALS
# =========================
def generate_signals():
    signals = []

    # ===== FOREX =====
    for pair in FOREX_PAIRS:
        prices_1m = fetch_twelve(pair, "1min")
        prices_5m = fetch_twelve(pair, "5min")

        if not prices_1m or not prices_5m:
            prices_1m = [1 + i * 0.001 for i in range(20)]
            prices_5m = prices_1m

        trend, confidence = analyze(prices_1m, prices_5m, pair)
        entry = prices_1m[-1]
        tp, sl = tp_sl(entry, trend)

        signals.append({
            "symbol": pair,
            "trend": trend,
            "entry": round(entry, 5),
            "tp": round(tp, 5),
            "sl": round(sl, 5),
            "confidence": confidence
        })

    # ===== CRYPTO =====
    cg = fetch_coingecko()
    cc = None if cg else fetch_cryptocompare()

    for coin in CRYPTO_IDS:
        price = None

        if cg:
            price = cg.get(coin, {}).get("usd")

        if not price and cc:
            symbol = coin[:3].upper()
            price = cc.get(symbol, {}).get("USD")

        if not price:
            price = synthetic_price()

        tp, sl = tp_sl(price, "BUY")

        signals.append({
            "symbol": coin.upper(),
            "trend": "BUY",
            "entry": round(price, 2),
            "tp": round(tp, 2),
            "sl": round(sl, 2),
            "confidence": 60
        })

    return signals


# =========================
# UPDATE
# =========================
def update_if_needed():
    now = time.time()
    if now - CACHE["last_update"] > CACHE_TTL:
        CACHE["signals"] = generate_signals()
        CACHE["last_update"] = now


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
        "last_update": CACHE["last_update"]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
