import requests
import time
import threading
from flask import Flask, jsonify

app = Flask(__name__)

API_KEY = "YOUR_API_KEY"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT"]
INTERVAL = "5min"

signals = []
last_update = 0

# 🔒 RATE LIMIT SETTINGS (SAFE)
REQUEST_DELAY = 1.2   # seconds between each API call
CYCLE_DELAY = 15      # seconds between full scans

# 📊 Fetch market data
def get_price_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={INTERVAL}&apikey={API_KEY}&outputsize=20"
    
    try:
        res = requests.get(url, timeout=10)
        data = res.json()

        if "values" not in data:
            print(f"API issue for {symbol}: {data}")
            return None

        return data["values"]

    except Exception as e:
        print("Error:", e)
        return None


# 🧠 Signal scoring system (NO more empty signals)
def calculate_signal(symbol, data):
    try:
        closes = [float(c["close"]) for c in data]

        current = closes[0]
        prev = closes[1]

        confidence = 0
        reasons = []

        # 📈 Trend direction
        if current > prev:
            direction = "BUY"
            confidence += 30
            reasons.append("Short-term uptrend")
        else:
            direction = "SELL"
            confidence += 30
            reasons.append("Short-term downtrend")

        # ⚡ Momentum strength
        move = abs(current - prev)
        if move > 0.5:
            confidence += 25
            reasons.append("Strong momentum")
        elif move > 0.2:
            confidence += 15
            reasons.append("Moderate momentum")

        # 📉 Simple support/resistance idea
        recent_low = min(closes[-5:])
        recent_high = max(closes[-5:])

        if current <= recent_low:
            confidence += 20
            reasons.append("Near support")
        elif current >= recent_high:
            confidence += 20
            reasons.append("Near resistance")

        # 🎯 Quality grading (NO filtering)
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
            "entry": round(current, 4),
            "tp": round(current * (1.01 if direction == "BUY" else 0.99), 4),
            "sl": round(current * (0.99 if direction == "BUY" else 1.01), 4),
            "confidence": confidence,
            "quality": quality,
            "reasons": reasons
        }

    except Exception as e:
        print("Signal error:", e)
        return None


# 🔁 Main scanner loop (RATE SAFE)
def scanner():
    global signals, last_update

    while True:
        new_signals = []

        for symbol in SYMBOLS:
            data = get_price_data(symbol)

            if data:
                signal = calculate_signal(symbol, data)
                if signal:
                    new_signals.append(signal)

            # 🔒 Prevent API ban
            time.sleep(REQUEST_DELAY)

        signals = new_signals
        last_update = time.time()

        print("Updated signals:", signals)

        # ⏳ Wait before next scan
        time.sleep(CYCLE_DELAY)


# 🌐 Routes
@app.route("/")
def home():
    return jsonify({
        "message": "🚀 Trading Bot Running",
        "endpoints": ["/signals", "/status"]
    })


@app.route("/signals")
def get_signals():
    if not signals:
        return jsonify([{"message": "⏳ Gathering market data..."}])
    return jsonify(signals)


@app.route("/status")
def status():
    return jsonify({
        "running": True,
        "signals_count": len(signals),
        "last_update": last_update
    })


# 🚀 Start background scanner
threading.Thread(target=scanner, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
