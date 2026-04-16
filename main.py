import requests
import pandas as pd
import websocket
import json
import threading
import time
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# ================= CONFIG =================
SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
TIMEFRAMES = ["1h", "15m", "5m"]

market_data = {sym: {tf: [] for tf in TIMEFRAMES} for sym in SYMBOLS}
signals_cache = []
market_strength_value = 0

bot_started = False

# ================= SAFE REQUEST =================
def safe_request(url, retries=3):
    for _ in range(retries):
        try:
            return requests.get(url, timeout=10).json()
        except:
            time.sleep(1)
    return []

# ================= FETCH =================
def fetch_historical(symbol, tf):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf}&limit=200"
    data = safe_request(url)

    candles = []
    for d in data:
        try:
            candles.append({
                "open": float(d[1]),
                "high": float(d[2]),
                "low": float(d[3]),
                "close": float(d[4]),
                "volume": float(d[5])
            })
        except:
            continue

    market_data[symbol][tf] = candles

# ================= WS =================
def on_message(ws, message):
    try:
        data = json.loads(message)
        if "data" in data:
            k = data["data"]["k"]
            sym = k["s"]

            candle = {
                "open": float(k["o"]),
                "high": float(k["h"]),
                "low": float(k["l"]),
                "close": float(k["c"]),
                "volume": float(k["v"])
            }

            market_data[sym]["5m"].append(candle)

            if len(market_data[sym]["5m"]) > 200:
                market_data[sym]["5m"].pop(0)

    except Exception as e:
        print("WS ERROR:", e)

def start_ws():
    while True:
        try:
            streams = [f"{s.lower()}@kline_5m" for s in SYMBOLS]
            url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
            ws = websocket.WebSocketApp(url, on_message=on_message)
            ws.run_forever()
        except:
            time.sleep(5)

# ================= INDICATORS =================
def add_indicators(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    return df

# ================= STRATEGIES =================
def detect_trend(df):
    return "UP" if df["ema50"].iloc[-1] > df["ema200"].iloc[-1] else "DOWN"

def detect_bos(df):
    return df["high"].iloc[-1] > df["high"].rolling(10).max().iloc[-2]

def detect_fvg(df):
    return df["low"].iloc[-1] > df["high"].iloc[-3]

def strong_trend(df):
    return abs(df["ema50"].iloc[-1] - df["ema200"].iloc[-1]) > df["close"].iloc[-1]*0.002

# ================= ANALYSIS =================
def analyze(symbol):
    score = 0
    trends = []

    for tf in TIMEFRAMES:
        df = pd.DataFrame(market_data[symbol][tf])

        if len(df) < 50:
            return 0, "NONE"

        df = add_indicators(df)
        trend = detect_trend(df)
        trends.append(trend)

        try:
            if detect_bos(df): score += 20
            if detect_fvg(df): score += 20
            if strong_trend(df): score += 20
        except:
            continue

    trend = "UP" if trends.count("UP") >= 2 else "DOWN"
    return score, trend

# ================= % =================
def classify(score):
    percent = int((score / 150) * 100)
    return max(10, min(percent, 100))

# ================= SIGNAL =================
def generate_signal(sym):
    score, trend = analyze(sym)

    df = pd.DataFrame(market_data[sym]["5m"])
    if len(df) < 50:
        return {
            "symbol": sym,
            "trend": "WAIT",
            "entry": 0,
            "tp": 0,
            "sl": 0,
            "confidence": 10,
            "tradable": False
        }

    price = df["close"].iloc[-1]
    confidence = classify(score)

    tradable = score >= 100

    tp = price * (1.02 if trend == "UP" else 0.98)
    sl = price * (0.995 if trend == "UP" else 1.005)

    return {
        "symbol": sym,
        "trend": trend,
        "entry": round(price, 2),
        "tp": round(tp, 2),
        "sl": round(sl, 2),
        "confidence": confidence,
        "tradable": tradable
    }

# ================= MARKET STRENGTH =================
def calculate_market_strength():
    total_score = 0
    count = 0

    for sym in SYMBOLS:
        score, _ = analyze(sym)
        total_score += score
        count += 1

    if count == 0:
        return 0

    return int((total_score / (150 * count)) * 100)

# ================= LOOP =================
def signal_loop():
    global signals_cache, market_strength_value

    while True:
        try:
            new_signals = []

            for sym in SYMBOLS:
                sig = generate_signal(sym)
                new_signals.append(sig)

            signals_cache = new_signals
            market_strength_value = calculate_market_strength()

            print("Market Strength:", market_strength_value)

            time.sleep(5)

        except Exception as e:
            print("LOOP ERROR:", e)
            time.sleep(5)

# ================= UI =================
HTML = """
<!DOCTYPE html>
<html>
<head>
<title>AI Dashboard</title>
<style>
body { background:#0f172a; color:white; font-family:sans-serif }
.card { padding:15px; margin:10px; border-radius:10px }
.green { background:#064e3b }
.yellow { background:#78350f }
.red { background:#7f1d1d }
</style>
</head>
<body>
<h2>🚀 AI Crypto Signals</h2>

<h3 id="strength"></h3>

<div id="signals"></div>

<audio id="alert" src="https://www.soundjay.com/buttons/sounds/button-3.mp3"></audio>

<script>
let lastAlert = "";

async function load(){
 let res = await fetch('/signals');
 let data = await res.json();

 let strengthRes = await fetch('/strength');
 let strengthData = await strengthRes.json();

 let s = strengthData.strength;
 let color = s>=80?'🟢':s>=50?'🟡':'🔴';

 document.getElementById('strength').innerHTML =
   "Market Strength: " + color + " " + s + "%";

 let html = '';

 data.forEach(x=>{
   let c = x.confidence>=80?'green':x.confidence>=60?'yellow':'red';

   let id = x.symbol + x.entry;

   if(x.tradable && id !== lastAlert){
     document.getElementById('alert').play();
     lastAlert = id;
   }

   html += `<div class="card ${c}">
   <b>${x.symbol}</b><br>
   Trend: ${x.trend}<br>
   Entry: ${x.entry}<br>
   TP: ${x.tp}<br>
   SL: ${x.sl}<br>
   Confidence: ${x.confidence}%<br>
   Tradable: ${x.tradable}
   </div>`;
 });

 document.getElementById('signals').innerHTML = html;
}

setInterval(load,3000);
load();
</script>
</body>
</html>
"""

# ================= ROUTES =================
@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/signals")
def signals():
    return jsonify(signals_cache)

@app.route("/strength")
def strength():
    return jsonify({"strength": market_strength_value})

# ================= START =================
def start_bot_once():
    global bot_started
    if bot_started:
        return
    bot_started = True

    for s in SYMBOLS:
        for tf in TIMEFRAMES:
            fetch_historical(s, tf)

    threading.Thread(target=start_ws, daemon=True).start()
    threading.Thread(target=signal_loop, daemon=True).start()

start_bot_once()
