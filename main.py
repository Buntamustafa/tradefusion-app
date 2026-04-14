import requests
import time
import threading
import os
from flask import Flask, jsonify

app = Flask(__name__)

# ✅ FIXED ENV VARIABLE NAME
API_KEY = os.getenv("TWELVEDATA_API_KEY")

if not API_KEY:
    print("❌ ERROR: API KEY NOT FOUND - CHECK RENDER ENV VARIABLE")

PAIRS = [
    "EURUSD",   # ✅ FIXED format
    "GBPUSD",
    "USDJPY",
    "BTC/USD",
    "ETH/USD",
    "XAU/USD",
    "XTI/USD"   # ✅ crude oil
]

TIMEFRAMES = ["1min", "5min", "15min"]

signals = []
status = {
    "connected": False,
    "api_working": False,
    "last_error": None,
    "signals_count": 0
}

# ===============================
# 📡 FETCH DATA (FIXED)
# ===============================
def fetch_data(symbol, timeframe):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={timeframe}&apikey={API_KEY}&outputsize=20"

    try:
        res = requests.get(url, timeout=10).json()

        # ✅ EMPTY RESPONSE FIX
        if not res:
            print(f"❌ EMPTY RESPONSE ({symbol})")
            return None

        # ✅ API ERROR HANDLING
        if "status" in res and res["status"] == "error":
            error_msg = res.get("message", "Unknown API error")
            print(f"❌ API ERROR ({symbol}):", error_msg)

            status["last_error"] = error_msg
            status["api_working"] = False
            return None

        # ✅ SAFE DATA CHECK
        if "values" not in res:
            print(f"❌ NO DATA ({symbol}):", res)
            status["api_working"] = False
            return None

        status["api_working"] = True
        return res["values"]

    except Exception as e:
        print(f"❌ FETCH ERROR ({symbol}):", e)
        status["last_error"] = str(e)
        status["api_working"] = False
        return None


# ===============================
# 🧱 ORDER BLOCK DETECTION
# ===============================
def detect_order_block(opens, closes, highs, lows, direction):
    try:
        for i in range(5, len(closes)):
            if direction == "BUY":
                if closes[i] < opens[i] and closes[i-1] > highs[i]:
                    return lows[i]

            if direction == "SELL":
                if closes[i] > opens[i] and closes[i-1] < lows[i]:
                    return highs[i]

        return None
    except:
        return None


# ===============================
# 🧠 ANALYSIS ENGINE
# ===============================
def analyze(symbol, data_map):
    try:
        total_score = 0
        direction_votes = []
        final_entry = None
        final_sl = None
        final_tp = None

        for tf, data in data_map.items():

            closes = [float(c["close"]) for c in data]
            highs = [float(c["high"]) for c in data]
            lows = [float(c["low"]) for c in data]
            opens = [float(c["open"]) for c in data]

            if len(closes) < 10:
                continue

            score = 0
            direction = None

            price = closes[0]

            # TREND (MA)
            ma = sum(closes[-5:]) / 5

            if price > ma:
                direction = "BUY"
                score += 1
            elif price < ma:
                direction = "SELL"
                score += 1

            # BOS
            if highs[0] > max(highs[1:5]):
                score += 1
            if lows[0] < min(lows[1:5]):
                score += 1

            # LIQUIDITY SWEEP
            if highs[1] > highs[2] and highs[1] > highs[3]:
                score += 1
            if lows[1] < lows[2] and lows[1] < lows[3]:
                score += 1

            # CANDLE CONFIRMATION
            if closes[0] > opens[0] and closes[1] < opens[1]:
                score += 1
            if closes[0] < opens[0] and closes[1] > opens[1]:
                score += 1

            # MOMENTUM
            if abs(closes[0] - closes[3]) > 0.001:
                score += 1

            total_score += score

            if direction:
                direction_votes.append(direction)

                # ORDER BLOCK ENTRY
                ob = detect_order_block(opens, closes, highs, lows, direction)

                if ob:
                    final_entry = ob
                else:
                    final_entry = price

                # STOP LOSS
                if direction == "BUY":
                    final_sl = min(lows[1:5])
                else:
                    final_sl = max(highs[1:5])

                # TAKE PROFIT (RR 1:2)
                risk = abs(final_entry - final_sl)

                if direction == "BUY":
                    final_tp = final_entry + (risk * 2)
                else:
                    final_tp = final_entry - (risk * 2)

        if not direction_votes:
            return None

        final_direction = max(set(direction_votes), key=direction_votes.count)

        # QUALITY CLASSIFICATION
        if total_score >= 10:
            quality = "🔥 ELITE"
        elif total_score >= 7:
            quality = "💪 STRONG"
        elif total_score >= 5:
            quality = "👍 MEDIUM"
        elif total_score >= 3:
            quality = "⚡ SCALP"
        else:
            return None

        return {
            "symbol": symbol,
            "direction": final_direction,
            "quality": quality,
            "score": total_score,
            "entry": round(final_entry, 5) if final_entry else None,
            "stop_loss": round(final_sl, 5) if final_sl else None,
            "take_profit": round(final_tp, 5) if final_tp else None
        }

    except Exception as e:
        print("❌ Analyze error:", e)
        return None


# ===============================
# 🔁 BOT LOOP
# ===============================
def bot_loop():
    tf_index = 0

    while True:
        try:
            status["connected"] = True
            new_signals = []

            current_tf = TIMEFRAMES[tf_index % len(TIMEFRAMES)]

            for pair in PAIRS:
                print(f"📡 Fetching {pair} @ {current_tf}")

                data = fetch_data(pair, current_tf)

                if data:
                    signal = analyze(pair, {current_tf: data})

                    if signal:
                        new_signals.append(signal)

                time.sleep(8)  # ✅ API LIMIT SAFE

            signals.clear()
            signals.extend(new_signals)
            status["signals_count"] = len(signals)

            tf_index += 1

        except Exception as e:
            print("❌ BOT LOOP ERROR:", e)
            status["last_error"] = str(e)
            status["connected"] = False

        time.sleep(10)


# ===============================
# 🌐 ROUTES
# ===============================
@app.route("/")
def home():
    return "Bot running 🚀"

@app.route("/signals")
def get_signals():
    if not signals:
        return jsonify([{"message": "⏳ Waiting for signals..."}])
    return jsonify(signals)

@app.route("/status")
def get_status():
    return jsonify(status)


# ===============================
# 🚀 START
# ===============================
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
