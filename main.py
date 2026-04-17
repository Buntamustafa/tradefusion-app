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

# 🔒 Rate limit protection
REQUEST_DELAY = 1.5   # seconds between calls
CYCLE_DELAY = 20      # seconds between full scans

def get_price_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={INTERVAL}&apikey={API_KEY}&outputsize=20"
    
    try:
        response = requests.get(url)
        data = response.json()

        if "values" not in data:
            return None

        return data["values"]

    except Exception as e:
        print("Error:", e)
        return None


def calculate_signal(symbol, data):
    try:
        closes = [float(c["close"]) for c in data]

        current = closes[0]
        prev = closes[1]

        confidence = 0

        # Simple logic (upgradeable)
        if current > prev:
            direction = "BUY"
            confidence += 40
        else:
            direction = "SELL"
            confidence += 40

        # Momentum
        if abs(current - prev) > 0.5:
            confidence += 30

        # Fake RSI logic (replace later with real RSI)
        if current < min(closes[-5:]):
            confidence += 20

        # 🚫 Filter weak signals
        if confidence < 60:
            return None

        return {
            "symbol": symbol,
            "direction": direction,
            "entry": current,
            "tp": round(current * 1.01, 2),
            "sl": round(current * 0.99, 2),
            "confidence": confidence,
            "quality": "🔥 STRONG" if confidence > 75 else "⚡ MEDIUM"
        }

    except:
        return None


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

            # 🔒 IMPORTANT: avoid rate limit
            time.sleep(REQUEST_DELAY)

        signals = new_signals
        last_update = time.time()

        print("Updated signals:", signals)

        # 🔁 Wait before next scan
        time.sleep(CYCLE_DELAY)


@app.route("/signals")
def get_signals():
    if not signals:
        return jsonify([{"message": "⏳ Waiting for strong signals..."}])
    return jsonify(signals)


@app.route("/status")
def status():
    return jsonify({
        "running": True,
        "signals_count": len(signals),
        "last_update": last_update
    })


# 🚀 Start scanner in background
threading.Thread(target=scanner, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
