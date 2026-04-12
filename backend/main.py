# ===============================
# 🔐 DERIV CONNECTION
# ===============================
import websocket
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
# 📊 SIGNAL STORAGE (NEW)
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
# 🔌 CONNECT TO DERIV
# ===============================
def connect():
    global ws

    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever()

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

def on_error(ws, error):
    print("❌ Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("🔌 Reconnecting...")
    time.sleep(5)
    connect()

# ===============================
# 🔐 AUTHORIZE
# ===============================
def authorize():
    if not API_TOKEN:
        print("❌ API TOKEN NOT FOUND!")
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

# ===============================
# 🧠 MARKET ANALYSIS
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

        # ✅ STORE SIGNAL (NEW)
        signals_log.append(result)

        # Keep only last 50 signals
        if len(signals_log) > 50:
            signals_log.pop(0)

        print(f"""
==============================
📊 {symbol}
Direction: {direction}
{signal}
Quality: {quality}

📍 Entry: {entry}
🛑 SL: {sl}
🎯 TP: {tp}
==============================
        """)

        playSound()

# ===============================
# 🌐 DASHBOARD ROUTES (NEW)
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

start_bot()

# ===============================
# 🚀 RUN FLASK
# ===============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
