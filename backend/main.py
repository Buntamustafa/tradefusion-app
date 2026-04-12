# ===============================
# 🔐 IMPORTS
# ===============================
from websocket import WebSocketApp
import json
import threading
import time
import os
from flask import Flask, jsonify

# ===============================
# 🔐 CONFIG
# ===============================
API_TOKEN = os.getenv("API_TOKEN")
WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

ws = None
connected = False

# ===============================
# 🌐 FLASK APP
# ===============================
app = Flask(__name__)

# ===============================
# 📊 STORAGE
# ===============================
signals_log = []
tick_prices = {}
last_signal = None

# ===============================
# 📊 SYMBOLS
# ===============================
symbols = [
    "frxEURUSD",
    "frxXAUUSD",
    "frxUSOIL",
    "cryBTCUSD",
    "cryETHUSD"
]

# ===============================
# 🔒 SAFE SEND
# ===============================
def safe_send(data):
    try:
        if ws and connected:
            ws.send(json.dumps(data))
    except Exception as e:
        print("❌ Send failed:", e)

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

    if rsi is not None:
        if 45 < rsi < 55:
            score += 30
        elif 40 < rsi < 60:
            score += 25
        elif 30 < rsi < 70:
            score += 15

    return min(score, 100)

# ===============================
# ⚡ SIGNAL ENGINE
# ===============================
def fastSignal(data):
    global last_signal

    if "tick" not in data:
        return

    symbol = data.get("tick", {}).get("symbol")
    if not symbol:
        return

    price = float(data["tick"]["quote"])

    if symbol not in tick_prices:
        tick_prices[symbol] = []

    tick_prices[symbol].append(price)

    if len(tick_prices[symbol]) > 50:
        tick_prices[symbol].pop(0)

    prices = tick_prices[symbol]

    if len(prices) < 10:
        return

    # Prevent edge crash
    if len(prices) < 5:
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

    # 💎 SNIPER CONDITIONS
    strong_trend = abs(ema9 - ema21) > (price * 0.001)
    strong_momentum = abs(prices[-1] - prices[-5]) > (price * 0.0005)
    perfect_rsi = rsi is not None and 45 < rsi < 55

    strength = calculate_strength(
        rsi,
        trend_up or trend_down,
        momentum_up or momentum_down
    )

    # 🎯 QUALITY
    quality = "⚠ SCALP"

    if strong_trend and strong_momentum and perfect_rsi and strength >= 95:
        quality = "💎 ELITE SNIPER"
    elif strength >= 90:
        quality = "💎 ELITE"
    elif strength > 75:
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

    # Smarter duplicate filter
    if last_signal:
        same_symbol = last_signal["symbol"] == result["symbol"]
        same_direction = last_signal["direction"] == result["direction"]
        close_price = abs(last_signal["entry"] - price) < (price * 0.00005)

        if same_symbol and same_direction and close_price:
            return

    last_signal = result
    signals_log.append(result)

    if len(signals_log) > 50:
        signals_log.pop(0)

    print("🧠 SIGNAL:", result)

# ===============================
# 🔌 CONNECT + AUTO RETRY
# ===============================
def connect():
    global ws

    while True:
        try:
            print("🔄 Connecting to Deriv...")
            ws = WebSocketApp(
                WS_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print("❌ Connection error:", e)

        print("⏳ Retrying in 5 seconds...")
        time.sleep(5)

def on_open(ws_instance):
    global ws
    ws = ws_instance
    print("✅ Connected to Deriv")
    authorize()

def on_message(ws, message):
    global connected
    data = json.loads(message)
    msg_type = data.get("msg_type")

    print("📩 MSG:", msg_type)

    if msg_type == "authorize":
        if "error" in data:
            print("❌ Auth failed:", data)
            connected = False
            time.sleep(3)
            authorize()
        else:
            print("🔐 Authorized SUCCESS")
            connected = True
            startFetching()

    elif msg_type == "tick":
        fastSignal(data)

    elif "error" in data:
        print("❌ WS ERROR:", data["error"])

def on_error(ws, error):
    print("❌ WebSocket Error:", error)

def on_close(ws, a, b):
    global connected
    connected = False
    print("🔌 Disconnected. Reconnecting...")

# ===============================
# 🔐 AUTHORIZE
# ===============================
def authorize():
    if not API_TOKEN:
        print("❌ NO API TOKEN SET")
        return

    print("🔐 Sending auth...")
    safe_send({"authorize": API_TOKEN})

# ===============================
# 📡 FETCH DATA
# ===============================
def startFetching():
    print("📡 Subscribing to symbols...")
    for symbol in symbols:
        safe_send({
            "ticks": symbol,
            "subscribe": 1
        })

# ===============================
# 🚀 BOT START
# ===============================
def run_bot():
    print("🚀 Bot started...")
    connect()

if not os.environ.get("RUN_MAIN"):
    threading.Thread(target=run_bot, daemon=True).start()

# ===============================
# 🌐 ROUTES
# ===============================
@app.route("/")
@app.route("/dashboard")
def dashboard():
    if not signals_log:
        return jsonify([{"message": "⏳ Waiting for signals..."}])
    return jsonify(signals_log[::-1])

@app.route("/signals")
def signals():
    return jsonify(signals_log[-10:])

@app.route("/force")
def force():
    test_signal = {
        "symbol": "TEST",
        "direction": "BUY",
        "signal": "TEST SIGNAL",
        "quality": "💎 ELITE SNIPER",
        "strength": 100,
        "entry": 12345,
        "trend": "UPTREND"
    }
    signals_log.append(test_signal)
    return jsonify({"status": "added"})

@app.route("/status")
def status():
    return jsonify({
        "connected": connected,
        "signals_count": len(signals_log)
    })

# ===============================
# 🚀 RUN
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
