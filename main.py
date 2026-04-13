# ===============================
# 🔐 IMPORTS
# ===============================
from websocket import WebSocketApp
import json
import threading
import time
import os
import requests
from flask import Flask, jsonify

# ===============================
# 🔐 CONFIG
# ===============================
API_TOKEN = os.getenv("API_TOKEN")

# ✅ FIXED: USE DEFAULT WORKING APP ID
WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

ws = None
connected = False
authorized = False
last_error = None

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
last_signal_time = 0

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
        if 40 < rsi < 60:
            score += 30
        elif 30 < rsi < 70:
            score += 20

    return min(score, 100)

# ===============================
# ⚡ SIGNAL ENGINE
# ===============================
def fastSignal(data):
    global last_signal, last_signal_time

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

    if len(prices) < 10:
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

    current_time = time.time()
    if current_time - last_signal_time < 5:
        return

    strength = calculate_strength(
        rsi,
        trend_up or trend_down,
        momentum_up or momentum_down
    )

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

    # 💎 ELITE LOGIC
    strong_trend = abs(ema9 - ema21) > (price * 0.001)
    strong_momentum = abs(prices[-1] - prices[-5]) > (price * 0.0005)
    perfect_rsi = rsi is not None and 45 < rsi < 55

    if strong_trend and strong_momentum and perfect_rsi and strength >= 95:
        result["quality"] = "💎 ELITE SNIPER"
    elif strength >= 90:
        result["quality"] = "💎 ELITE"

    # 🚫 DUPLICATE FILTER
    if last_signal:
        same_symbol = last_signal["symbol"] == result["symbol"]
        same_direction = last_signal["direction"] == result["direction"]
        close_price = abs(last_signal["entry"] - price) < (price * 0.0005)

        if same_symbol and same_direction and close_price:
            return

    last_signal = result
    last_signal_time = current_time
    signals_log.append(result)

    if len(signals_log) > 50:
        signals_log.pop(0)

    print("🧠 SIGNAL:", result)

# ===============================
# 🔌 CONNECTION
# ===============================
def connect():
    global ws, connected, authorized, last_error

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

            ws.run_forever()

        except Exception as e:
            print("❌ Connection error:", e)
            last_error = str(e)

        print("⏳ Retrying in 5 seconds...")
        time.sleep(5)

def on_open(ws):
    global connected
    connected = True
    print("✅ Connected")

    if not API_TOKEN:
        print("❌ NO API TOKEN")
        return

    ws.send(json.dumps({"authorize": API_TOKEN}))

def on_message(ws, message):
    global authorized, last_error

    data = json.loads(message)

    if data.get("msg_type") == "authorize":
        authorized = True
        print("✅ Authorized")
        startFetching()

    if "error" in data:
        last_error = data["error"]["message"]
        print("❌ ERROR:", last_error)

    if data.get("msg_type") == "tick":
        fastSignal(data)

def on_error(ws, error):
    global connected, last_error
    connected = False
    last_error = str(error)
    print("❌ WS ERROR:", error)

def on_close(ws, a, b):
    global connected, authorized
    connected = False
    authorized = False
    print("🔌 Reconnecting...")

# ===============================
# 📡 FETCH
# ===============================
def startFetching():
    for symbol in symbols:
        ws.send(json.dumps({
            "ticks": symbol,
            "subscribe": 1
        }))

# ===============================
# ❤️ KEEP ALIVE
# ===============================
def keep_alive():
    while True:
        try:
            url = os.getenv("RENDER_EXTERNAL_URL")
            if url:
                requests.get(url)
        except:
            pass
        time.sleep(300)

# ===============================
# 🚀 START THREADS
# ===============================
def start_background_tasks():
    threading.Thread(target=connect, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()

# ===============================
# 🌐 ROUTES
# ===============================
@app.route("/")
def home():
    return jsonify({"message": "🚀 Bot running"})

@app.route("/status")
def status():
    return jsonify({
        "connected": connected,
        "authorized": authorized,
        "signals_count": len(signals_log),
        "last_error": last_error
    })

@app.route("/signals")
def signals():
    return jsonify(signals_log[-10:])

# ===============================
# 🚀 RUN
# ===============================
if __name__ == "__main__":
    start_background_tasks()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
