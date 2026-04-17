import requests
import time
import threading
from flask import Flask, jsonify

app = Flask(__name__)

TWELVE_API_KEY = "YOUR_TWELVEDATA_API_KEY"

CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT"]
FOREX_SYMBOLS = ["EUR/USD", "GBP/USD"]

signals = []
last_update = 0

REQUEST_DELAY = 1.0
CYCLE_DELAY = 15
CACHE_TTL = 30

cache = {}
cache_lock = threading.Lock()

# =========================
# 🔒 SAFE REQUEST
# =========================
def safe_request(url):
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            print(f"❌ HTTP {res.status_code}: {url}")
            return None
        return res.json()
    except Exception as e:
        print("❌ Request error:", e)
        return None

# =========================
# 🧠 CACHE SYSTEM (THREAD SAFE)
# =========================
def get_cached(key):
    with cache_lock:
        if key in cache:
            data, ts = cache[key]
            if time.time() - ts < CACHE_TTL:
                return data
    return None

def set_cache(key, value):
    with cache_lock:
        cache[key] = (value, time.time())

# =========================
# 🪙 CRYPTO (CoinGecko)
# =========================
def get_crypto_data(symbol):
    try:
        cached = get_cached(symbol)
        if cached:
            return cached

        mapping = {
            "BTCUSDT": "bitcoin",
            "ETHUSDT": "ethereum",
            "XRPUSDT": "ripple",
            "BNBUSDT": "binancecoin"
        }

        coin_id = mapping.get(symbol)
        if not coin_id:
            return None

        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart?vs_currency=usd&days=1"
        data = safe_request(url)

        if not data or "prices" not in data:
            return None

        prices = [p[1] for p in data["prices"]][-50:]

        set_cache(symbol, prices)
        return prices

    except Exception as e:
        print("❌ Crypto error:", e)
        return None

# =========================
# 💱 FOREX (TwelveData)
# =========================
def get_forex_data(symbol, interval):
    try:
        key = f"{symbol}_{interval}"
        cached = get_cached(key)
        if cached:
            return cached

        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&apikey={TWELVE_API_KEY}&outputsize=30"
        data = safe_request(url)

        if not data or "values" not in data:
            return None

        closes = [float(x["close"]) for x in data["values"]]

        set_cache(key, closes)
        return closes

    except Exception as e:
        print("❌ Forex error:", e)
        return None

# =========================
# 🔁 FOREX BACKUP
# =========================
def get_forex_backup(symbol):
    try:
        base, quote = symbol.split("/")
        url = f"https://api.exchangerate.host/timeseries?base={base}&symbols={quote}"
        data = safe_request(url)

        if not data or "rates" not in data:
            return None

        rates = [v[quote] for v in data["rates"].values()]
        return rates[-30:]

    except Exception as e:
        print("❌ Backup error:", e)
        return None

# =========================
# 🧠 ANALYSIS (SAFE)
# =========================
def analyze(symbol, data_5m, data_15m):
    try:
        if not data_5m or len(data_5m) < 5:
            return None

        current = data_5m[-1]
        prev = data_5m[-2]

        confidence = 0
        reasons = []

        # Direction
        if current > prev:
            direction = "BUY"
            confidence += 30
            reasons.append("5m uptrend")
        else:
            direction = "SELL"
            confidence += 30
            reasons.append("5m downtrend")

        # 15m confirmation
        if data_15m and len(data_15m) > 2:
            if data_15m[-1] > data_15m[-2]:
                confidence += 25
                reasons.append("15m trend match")

        # Momentum
        move = abs(current - prev)
        if move > 0:
            confidence += 20

        # Levels
        if current <= min(data_5m[-5:]):
            confidence += 15
            reasons.append("Support")
        elif current >= max(data_5m[-5:]):
            confidence += 15
            reasons.append("Resistance")

        # Quality
        if confidence >= 75:
            quality = "🔥 STRONG"
        elif confidence >= 60:
            quality = "⚡ MEDIUM"
        elif confidence >= 40:
            quality = "⚠️ WEAK"
        else:
            quality = "❌ POOR"

        return {
            "symbol": symbol,
            "direction": direction,
            "entry": round(current, 5),
            "tp": round(current * (1.01 if direction == "BUY" else 0.99), 5),
            "sl": round(current * (0.99 if direction == "BUY" else 1.01), 5),
            "confidence": confidence,
            "quality": quality,
            "reasons": reasons
        }

    except Exception as e:
        print("❌ Analyze error:", e)
        return None

# =========================
# 🔁 SCANNER LOOP (CRASH-PROOF)
# =========================
def scanner():
    global signals, last_update

    print("🚀 Scanner started")

    while True:
        try:
            new_signals = []

            # CRYPTO
            for symbol in CRYPTO_SYMBOLS:
                try:
                    data = get_crypto_data(symbol)
                    if data:
                        signal = analyze(symbol, data, data)
                        if signal:
                            new_signals.append(signal)
                except Exception as e:
                    print(f"❌ Crypto loop error {symbol}:", e)

                time.sleep(REQUEST_DELAY)

            # FOREX
            for symbol in FOREX_SYMBOLS:
                try:
                    data_5m = get_forex_data(symbol, "5min")
                    data_15m = get_forex_data(symbol, "15min")

                    if not data_5m:
                        print(f"⚠️ Backup used for {symbol}")
                        data_5m = get_forex_backup(symbol)

                    if data_5m:
                        signal = analyze(symbol, data_5m, data_15m)
                        if signal:
                            new_signals.append(signal)

                except Exception as e:
                    print(f"❌ Forex loop error {symbol}:", e)

                time.sleep(REQUEST_DELAY)

            signals = new_signals if new_signals else [{
                "symbol": "SYSTEM",
                "direction": "WAIT",
                "confidence": 0,
                "quality": "⚙️ RUNNING",
                "message": "Scanning market..."
            }]

            last_update = time.time()
            print("✅ Signals updated:", signals)

        except Exception as e:
            print("🔥 CRITICAL SCANNER ERROR:", e)

        time.sleep(CYCLE_DELAY)

# =========================
# 🌐 ROUTES (SAFE)
# =========================
@app.route("/")
def home():
    return jsonify({
        "message": "🚀 Bot Running",
        "endpoints": ["/signals", "/status"]
    })

@app.route("/signals")
def get_signals():
    try:
        return jsonify(signals)
    except Exception as e:
        return jsonify([{"error": str(e)}])

@app.route("/status")
def status():
    return jsonify({
        "running": True,
        "signals_count": len(signals),
        "last_update": last_update,
        "cache_size": len(cache)
    })

# =========================
# 🚀 START SAFE THREAD
# =========================
def start():
    while True:
        try:
            threading.Thread(target=scanner, daemon=True).start()
            break
        except Exception as e:
            print("Thread start failed:", e)
            time.sleep(5)

start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
