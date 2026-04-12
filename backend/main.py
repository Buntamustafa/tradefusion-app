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
# ⚡ FAST SIGNAL ENGINE (AI)
# ===============================
tick_prices = {}

def fastSignal(data):
    if "tick" not in data:
        return

    symbol = data["echo_req"].get("ticks", "")
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

    if not rsi or not ema9 or not ema21:
        return

    momentum_up = prices[-1] > prices[-5]
    momentum_down = prices[-1] < prices[-5]

    trend_up = ema9 > ema21
    trend_down = ema9 < ema21

    valid_buy = momentum_up and trend_up and rsi < 70
    valid_sell = momentum_down and trend_down and rsi > 30

    if not (valid_buy or valid_sell):
        return

    quality = "⚡ FAST"

    if trend_up and rsi < 60:
        quality = "🔥 STRONG"
    elif trend_down and rsi > 40:
        quality = "⚡ MEDIUM"
    else:
        quality = "⚠ SCALP"

    result = {
        "symbol": symbol,
        "direction": "BUY" if valid_buy else "SELL",
        "signal": "⚡ FAST AI SIGNAL",
        "quality": quality,
        "entry": price,
        "sl": None,
        "tp": None,
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
    print("✅ Connected to Deriv")
    authorize()

def on_message(ws, message):
    data = json.loads(message)

    if data.get("msg_type") == "authorize":
        print("🔐 Authorized")
        startFetching()

    if data.get("msg_type") == "candles":
        analyzeMarket(data)

    if data.get("msg_type") == "tick":
        fastSignal(data)

def on_error(ws, error):
    print("❌ Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("🔌 Connection closed, retrying...")

# ===============================
# 🔐 AUTHORIZE
# ===============================
def authorize():
    if not API_TOKEN:
        print("❌ API TOKEN NOT FOUND! Set it in Render.")
        return

    ws.send(json.dumps({
        "authorize": API_TOKEN
    }))

# ===============================
# 📡 FETCH DATA
# ===============================
def startFetching():
    for symbol in symbols:
        ws.send(json.dumps({
            "ticks_history": symbol,
            "style": "candles",
            "granularity": 60,
            "count": 100
        }))

    # ⚡ FAST TICKS
    for symbol in symbols:
        ws.send(json.dumps({
            "ticks": symbol,
            "subscribe": 1
        }))

# ===============================
# 🧠 MARKET ANALYSIS (ORIGINAL)
# ===============================
def analyzeMarket(data):
    candles = data.get("candles", [])
    symbol = data.get("echo_req", {}).get("ticks_history")

    if not candles or len(candles) < 20:
        return

    last = candles[-1]
    prev = candles[-2]

    high = float(last["high"])
    low = float(last["low"])
    close = float(last["close"])

    highs = [float(c["high"]) for c in candles[-10:]]
    lows = [float(c["low"]) for c in candles[-10:]]

    uptrend = highs[-1] > highs[0] and lows[-1] > lows[0]
    downtrend = highs[-1] < highs[0] and lows[-1] < lows[0]

    bos = last["high"] > prev["high"] or last["low"] < prev["low"]

    sweep = False
    if last["high"] > prev["high"] and close < prev["high"]:
        sweep = True
    if last["low"] < prev["low"] and close > prev["low"]:
        sweep = True

    fvg = False
    c1 = candles[-3]
    c3 = candles[-1]

    if float(c1["high"]) < float(c3["low"]) or float(c1["low"]) > float(c3["high"]):
        fvg = True

    resistance = max(highs)
    support = min(lows)

    entry = close
    sl = None
    tp = None
    direction = None

    if uptrend:
        direction = "BUY"
        sl = support
        tp = entry + (entry - sl) * 2

    elif downtrend:
        direction = "SELL"
        sl = resistance
        tp = entry - (sl - entry) * 2

    signal = None
    quality = "⚠ SCALP"

    if bos and sweep and fvg and (uptrend or downtrend):
        signal = "SNIPER ENTRY 🎯"
        quality = "🔥 STRONG"
    elif bos and (sweep or fvg):
        signal = "ENTRY ⚡"
        quality = "⚡ MEDIUM"
    elif bos:
        signal = "QUICK SCALP ⚠"
        quality = "⚠ SCALP"

    if signal:
        result = {
            "symbol": symbol,
            "direction": direction,
            "signal": signal,
            "quality": quality,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "trend": "UPTREND" if uptrend else "DOWNTREND" if downtrend else "RANGE"
        }

        signals_log.append(result)

        if len(signals_log) > 50:
            signals_log.pop(0)

        print(result)
        playSound()

# ===============================
# 🌐 DASHBOARD
# ===============================
@app.route("/")
def dashboard():
    return f"""
    <html>
    <head>
        <title>TradeFusion Dashboard</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body {{ background:#0f172a; color:white; font-family:sans-serif; }}
            .card {{ background:#1e293b; padding:15px; margin:10px; border-radius:10px; }}
        </style>
    </head>
    <body>
        <h2>🚀 TradeFusion Live Signals</h2>
        {"".join([f'''
        <div class="card">
            <b>{s["symbol"]}</b><br>
            {s["signal"]} ({s["quality"]})<br>
            Direction: {s["direction"]}<br>
            Entry: {s["entry"]}<br>
            SL: {s["sl"]}<br>
            TP: {s["tp"]}
        </div>
        ''' for s in signals_log[::-1]])}
    </body>
    </html>
    """

@app.route("/signals")
def get_signals():
    return jsonify(signals_log)

# ===============================
# 🚀 START BOT
# ===============================
def start_bot():
    thread = threading.Thread(target=connect)
    thread.daemon = True
    thread.start()

if os.environ.get("RUN_MAIN") != "true":
    start_bot()

# ===============================
# 🚀 RUN FLASK
# ===============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
