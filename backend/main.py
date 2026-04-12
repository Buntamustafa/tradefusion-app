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
# 📊 SIGNAL STORAGE
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
# 🔊 SOUND ALERT
# ===============================
def playSound():
    print("🔊 Beep!")

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
# 💪 SIGNAL STRENGTH
# ===============================
def calculate_strength(rsi, trend, momentum):
    score = 0

    if trend:
        score += 40
    if momentum:
        score += 30

    if rsi:
        if 40 < rsi < 60:
            score += 30
        elif 30 < rsi < 70:
            score += 20

    return min(score, 100)

# ===============================
# ⚡ FAST SIGNAL ENGINE
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

    momentum_up = prices[-1] > prices[-5]
    momentum_down = prices[-1] < prices[-5]

    trend_up = ema9 > ema21
    trend_down = ema9 < ema21

    valid_buy = momentum_up and trend_up and rsi < 70
    valid_sell = momentum_down and trend_down and rsi > 30

    if not (valid_buy or valid_sell):
        return

    strength = calculate_strength(rsi, trend_up or trend_down, momentum_up or momentum_down)

    quality = "⚠ SCALP"
    if strength > 75:
        quality = "🔥 STRONG"
    elif strength > 50:
        quality = "⚡ MEDIUM"

    result = {
        "symbol": symbol,
        "direction": "BUY" if valid_buy else "SELL",
        "signal": "⚡ FAST AI SIGNAL",
        "quality": quality,
        "strength": strength,
        "entry": price,
        "trend": "UPTREND" if trend_up else "DOWNTREND"
    }

    signals_log.append(result)

    if len(signals_log) > 50:
        signals_log.pop(0)

    print("🧠 AI SIGNAL:", result)
    playSound()

# ===============================
# 🔌 CONNECT TO DERIV
# ===============================
def connect():
    global ws
    while True:
        try:
            ws = WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever()
        except Exception as e:
            print("Reconnect error:", e)
            time.sleep(5)

def on_open(ws):
    print("✅ Connected")
    authorize()

def on_message(ws, message):
    data = json.loads(message)

    if data.get("msg_type") == "authorize":
        print("🔐 Authorized")
        startFetching()

    if data.get("msg_type") == "tick":
        fastSignal(data)

def on_error(ws, error):
    print("❌ Error:", error)

def on_close(ws, a, b):
    print("🔌 Reconnecting...")

# ===============================
# 🔐 AUTHORIZE
# ===============================
def authorize():
    if not API_TOKEN:
        print("❌ NO API TOKEN")
        return

    ws.send(json.dumps({"authorize": API_TOKEN}))

# ===============================
# 📡 FETCH DATA
# ===============================
def startFetching():
    for symbol in symbols:
        ws.send(json.dumps({
            "ticks": symbol,
            "subscribe": 1
        }))

# ===============================
# 🚀 SAFE BOT START (IMPORTANT)
# ===============================
def run_bot():
    print("🚀 Bot started...")
    connect()

if os.environ.get("RENDER"):
    threading.Thread(target=run_bot, daemon=True).start()

# ===============================
# 🌐 ROUTES
# ===============================
@app.route("/")
def home():
    if not signals_log:
        return jsonify([{"message": "⏳ Waiting for signals..."}])
    return jsonify(signals_log[::-1])

@app.route("/signals")
def signals():
    if not signals_log:
        return jsonify([{"message": "⏳ Waiting for signals..."}])
    return jsonify(signals_log)

@app.route("/test")
def test():
    return "✅ Test route working!"

# ===============================
# 🚀 RUN
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
