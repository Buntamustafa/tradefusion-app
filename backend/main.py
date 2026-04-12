# ===============================
# 🔐 DERIV CONNECTION
# ===============================
import websocket
import json
import threading
import time

API_TOKEN = "pat_4f3bb0455ca7efe76bd34d5f18e7e2a44b62d697e906dbf4f9dffb4215cd18e0"  # 🔥 INSERT HERE
WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089"

ws = None

# ===============================
# 📊 PAIRS (YOU REQUESTED)
# ===============================
symbols = [
    "frxEURUSD",  # EUR/USD
    "frxXAUUSD",  # GOLD
    "frxUSOIL",   # OIL
    "cryBTCUSD",  # BTC
    "cryETHUSD"   # ETH
]

# ===============================
# 🔊 SOUND ALERT (SAFE FOR SERVER)
# ===============================
def playSound():
    print("🔊 Beep!")  # Server-safe (no audio crash)

# ===============================
# 🔌 CONNECT TO DERIV
# ===============================
def connect():
    global ws
    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error
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

# ===============================
# 🔐 AUTHORIZE
# ===============================
def authorize():
    ws.send(json.dumps({
        "authorize": API_TOKEN
    }))

# ===============================
# 📡 FETCH DATA (1m candles)
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
# 🧠 MARKET ANALYSIS CORE
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

    # ===============================
    # 📈 TREND STRUCTURE (NEW)
    # ===============================
    highs = [float(c["high"]) for c in candles[-10:]]
    lows = [float(c["low"]) for c in candles[-10:]]

    uptrend = highs[-1] > highs[0] and lows[-1] > lows[0]
    downtrend = highs[-1] < highs[0] and lows[-1] < lows[0]

    # ===============================
    # 🧩 BOS (Break of Structure)
    # ===============================
    bos = last["high"] > prev["high"] or last["low"] < prev["low"]

    # ===============================
    # 💧 LIQUIDITY SWEEP
    # ===============================
    sweep = False
    if last["high"] > prev["high"] and close < prev["high"]:
        sweep = True
    if last["low"] < prev["low"] and close > prev["low"]:
        sweep = True

    # ===============================
    # ⚡ MINI FVG
    # ===============================
    fvg = False
    c1 = candles[-3]
    c3 = candles[-1]

    if float(c1["high"]) < float(c3["low"]) or float(c1["low"]) > float(c3["high"]):
        fvg = True

    # ===============================
    # 🧱 SUPPORT / RESISTANCE
    # ===============================
    resistance = max(highs)
    support = min(lows)

    # ===============================
    # 🎯 ENTRY + SL + TP
    # ===============================
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

    # ===============================
    # 🎯 SIGNAL QUALITY
    # ===============================
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

    # ===============================
    # 📢 OUTPUT
    # ===============================
    if signal:
        print(f"""
==============================
📊 {symbol}
Direction: {direction}
{signal}
Quality: {quality}

📍 Entry: {entry}
🛑 Stop Loss: {sl}
🎯 Take Profit: {tp}

📈 Trend: {"UPTREND" if uptrend else "DOWNTREND" if downtrend else "RANGE"}

✔ BOS: {"✅" if bos else "❌"}
✔ Sweep: {"✅" if sweep else "❌"}
✔ FVG: {"✅" if fvg else "❌"}
==============================
        """)

        playSound()

# ===============================
# 🚀 START BOT
# ===============================
if __name__ == "__main__":
    connect()
