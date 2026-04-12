# ===============================
# 🔐 DERIV CONNECTION
# ===============================
from websocket import WebSocketApp
import json
import threading
import time
import os
from flask import Flask, jsonify

API_TOKEN = os.getenv("API_TOKEN")
WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

ws = None

# ===============================
# 🌐 FLASK APP
# ===============================
app = Flask(__name__)

# ===============================
# 📊 STORAGE
# ===============================
signals_log = []
tick_prices = {}

# ===============================
# 📊 PAIRS
# ===============================
symbols = [
    "frxEURUSD",
    "frxXAUUSD",
    "frxUSOIL",
    "cryBTCUSD",
    "cryETHUSD"
]

# ===============================
# 🔊 SOUND
# ===============================
def playSound():
    print("🔊 SIGNAL ALERT!")

# ===============================
# 📉 INDICATORS
# ===============================
def calculate_rsi(prices, period=14):
    if len(prices) < period:
        return None

    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        if diff > 0:
            gains.append(diff)
        else:
            losses.append(abs(diff))

    avg_gain = sum(gains[-period:]) / period if gains else 0
    avg_loss = sum(losses[-period:]) / period if losses else 0

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_ema(prices, period):
    if len(prices) < period:
        return None

    ema = prices[0]
    k = 2 / (period + 1)

    for price in prices[1:]:
        ema = price * k + ema * (1 - k)

    return ema

# ===============================
# 🧠 SIGNAL STRENGTH ENGINE
# ===============================
def calculate_strength(bos, sweep, fvg, trend, ema_align):
    score = 0

    if bos:
        score += 25
    if sweep:
        score += 25
    if fvg:
        score += 20
    if trend:
        score += 15
    if ema_align:
        score += 15

    return score

# ===============================
# ⚡ FAST SIGNAL (AI)
# ===============================
def fastSignal(data):
    if "tick" not in data:
        return

    symbol = data.get("echo_req", {}).get("ticks", "")
    price = float(data["tick"]["quote"])

    if symbol not in tick_prices:
        tick_prices[symbol] = []

    tick_prices[symbol].append(price)

    if len(tick_prices[symbol]) > 50:
        tick_prices[symbol].pop(0)

    prices = tick_prices[symbol]

    if len(prices) < 20:
        return

    rsi = calculate_rsi(prices)
    ema9 = calculate_ema(prices, 9)
    ema21 = calculate_ema(prices, 21)

    if rsi is None or ema9 is None or ema21 is None:
        return

    trend_up = ema9 > ema21
    trend_down = ema9 < ema21

    valid_buy = trend_up and rsi < 70
    valid_sell = trend_down and rsi > 30

    if not (valid_buy or valid_sell):
        return

    # strength for fast
    strength = 60
    if trend_up and rsi < 60:
        strength = 80

    result = {
        "symbol": symbol,
        "direction": "BUY" if valid_buy else "SELL",
        "signal": "⚡ FAST AI SIGNAL",
        "quality": "⚡ FAST",
        "strength": f"{strength}%",
        "entry": price,
        "trend": "UPTREND" if trend_up else "DOWNTREND"
    }

    signals_log.append(result)
    if len(signals_log) > 50:
        signals_log.pop(0)

    print("🧠 FAST SIGNAL:", result)
    playSound()

# ===============================
# 🔌 CONNECTION
# ===============================
def connect():
    global ws
    while True:
        try:
            ws = WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message
            )
            ws.run_forever()
        except:
            time.sleep(5)

def on_open(ws):
    print("✅ Connected")
    ws.send(json.dumps({"authorize": API_TOKEN}))

def on_message(ws, message):
    data = json.loads(message)

    if data.get("msg_type") == "authorize":
        print("🔐 Authorized")
        startFetching()

    if data.get("msg_type") == "candles":
        analyzeMarket(data)

    if data.get("msg_type") == "tick":
        fastSignal(data)

# ===============================
# 📡 FETCH
# ===============================
def startFetching():
    for s in symbols:
        ws.send(json.dumps({
            "ticks_history": s,
            "style": "candles",
            "granularity": 60,
            "count": 100
        }))
        ws.send(json.dumps({
            "ticks": s,
            "subscribe": 1
        }))

# ===============================
# 🧠 MAIN ANALYSIS
# ===============================
def analyzeMarket(data):
    candles = data.get("candles", [])
    symbol = data.get("echo_req", {}).get("ticks_history")

    if len(candles) < 20:
        return

    last = candles[-1]
    prev = candles[-2]

    close = float(last["close"])

    highs = [float(c["high"]) for c in candles[-10:]]
    lows = [float(c["low"]) for c in candles[-10:]]

    uptrend = highs[-1] > highs[0]
    downtrend = highs[-1] < highs[0]

    bos = last["high"] > prev["high"] or last["low"] < prev["low"]

    sweep = (
        (last["high"] > prev["high"] and close < prev["high"]) or
        (last["low"] < prev["low"] and close > prev["low"])
    )

    fvg = (
        float(candles[-3]["high"]) < float(last["low"]) or
        float(candles[-3]["low"]) > float(last["high"])
    )

    prices = [float(c["close"]) for c in candles]
    ema9 = calculate_ema(prices, 9)
    ema21 = calculate_ema(prices, 21)

    ema_align = ema9 and ema21 and ((ema9 > ema21) or (ema9 < ema21))

    strength_score = calculate_strength(bos, sweep, fvg, (uptrend or downtrend), ema_align)

    # QUALITY CLASS
    if strength_score >= 80:
        quality = "🔥 STRONG"
    elif strength_score >= 60:
        quality = "⚡ MEDIUM"
    else:
        quality = "⚠ SCALP"

    result = {
        "symbol": symbol,
        "direction": "BUY" if uptrend else "SELL",
        "signal": "SMART ENTRY",
        "quality": quality,
        "strength": f"{strength_score}%",
        "entry": close,
        "trend": "UPTREND" if uptrend else "DOWNTREND"
    }

    signals_log.append(result)
    if len(signals_log) > 50:
        signals_log.pop(0)

    print("📊 SIGNAL:", result)
    playSound()

# ===============================
# 🌐 DASHBOARD
# ===============================
@app.route("/")
def dashboard():
    if not signals_log:
        return "<h2>⏳ Waiting for signals...</h2>"
    return jsonify(signals_log[::-1])

@app.route("/signals")
def signals():
    return jsonify(signals_log)

# ===============================
# 🚀 START
# ===============================
threading.Thread(target=connect, daemon=True).start()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
