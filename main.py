<!-- ================= BACKEND: main.py ================= -->Save this as main.py

import requests import pandas as pd import websocket import json import threading import time from flask import Flask, jsonify, render_template_string

app = Flask(name)

SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT"] TIMEFRAMES = ["1h", "15m", "5m"]

market_data = {sym: {tf: [] for tf in TIMEFRAMES} for sym in SYMBOLS} signals_cache = [] last_signals = {}

================= DATA =================

def fetch_historical(symbol, tf): url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf}&limit=200" data = requests.get(url).json() market_data[symbol][tf] = [{ "open": float(d[1]), "high": float(d[2]), "low": float(d[3]), "close": float(d[4]), "volume": float(d[5]) } for d in data]

================= WS =================

def on_message(ws, message): data = json.loads(message) if "data" in data: k = data["data"]["k"] sym = k["s"] candle = { "open": float(k["o"]), "high": float(k["h"]), "low": float(k["l"]), "close": float(k["c"]), "volume": float(k["v"]) } market_data[sym]["5m"].append(candle) if len(market_data[sym]["5m"]) > 200: market_data[sym]["5m"].pop(0)

def start_ws(): streams = [f"{s.lower()}@kline_5m" for s in SYMBOLS] url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}" websocket.WebSocketApp(url, on_message=on_message).run_forever()

================= LOGIC =================

def add_indicators(df): df["ema50"] = df["close"].ewm(span=50).mean() df["ema200"] = df["close"].ewm(span=200).mean() df["range"] = df["high"] - df["low"] df["volatility"] = df["range"].rolling(14).mean() return df

def detect_trend(df): return "UP" if df["ema50"].iloc[-1] > df["ema200"].iloc[-1] else "DOWN"

def detect_bos(df): return df["high"].iloc[-1] > df["high"].rolling(10).max().iloc[-2]

def detect_fvg(df): return df["low"].iloc[-1] > df["high"].iloc[-3]

def strong_trend(df): return abs(df["ema50"].iloc[-1] - df["ema200"].iloc[-1]) > df["close"].iloc[-1]*0.002

def analyze(symbol): score = 0 confirmations = [] trends = []

for tf in TIMEFRAMES:
    df = pd.DataFrame(market_data[symbol][tf])
    if len(df) < 50:
        return 0, "NONE", []

    df = add_indicators(df)
    trend = detect_trend(df)
    trends.append(trend)

    if detect_bos(df):
        score += 20
        confirmations.append("BOS")

    if detect_fvg(df):
        score += 20
        confirmations.append("FVG")

    if strong_trend(df):
        score += 20
        confirmations.append("STRONG")

trend = "UP" if trends.count("UP") >= 2 else "DOWN"
return score, trend, confirmations

def classify(score): percent = int((score/150)*100) return max(10, min(percent, 100))

def generate_signal(sym): score, trend, conf = analyze(sym) df = pd.DataFrame(market_data[sym]["5m"]) if len(df) < 50: return None

price = df["close"].iloc[-1]
percent = classify(score)

tradable = score >= 100

return {
    "symbol": sym,
    "trend": trend,
    "entry": round(price, 2),
    "tp": round(price*1.02 if trend=="UP" else price*0.98, 2),
    "sl": round(price*0.995 if trend=="UP" else price*1.005, 2),
    "confidence": percent,
    "tradable": tradable
}

def loop(): global signals_cache while True: signals_cache = [s for s in [generate_signal(sym) for sym in SYMBOLS] if s] time.sleep(5)

================= UI =================

HTML = """

<!DOCTYPE html><html>
<head>
<title>AI Trading Dashboard</title>
<style>
body { background:#0f172a; color:white; font-family:sans-serif }
.card { padding:15px; margin:10px; border-radius:10px }
.green { background:#064e3b }
.yellow { background:#78350f }
.red { background:#7f1d1d }
</style>
</head>
<body>
<h2>🚀 AI Signals</h2>
<div id="signals"></div>
<audio id="alert" src="https://www.soundjay.com/buttons/sounds/button-3.mp3"></audio><script>
async function load(){
 let res = await fetch('/signals');
 let data = await res.json();
 let html = '';

 data.forEach(s=>{
   let color = s.confidence>=80?'green':s.confidence>=60?'yellow':'red';

   if(s.tradable){
     document.getElementById('alert').play();
   }

   html += `<div class="card ${color}">
   <b>${s.symbol}</b><br>
   Trend: ${s.trend}<br>
   Entry: ${s.entry}<br>
   TP: ${s.tp}<br>
   SL: ${s.sl}<br>
   Confidence: ${s.confidence}%<br>
   Tradable: ${s.tradable}
   </div>`;
 });

 document.getElementById('signals').innerHTML = html;
}

setInterval(load,3000);
load();
</script></body>
</html>
"""@app.route('/') def home(): return render_template_string(HTML)

@app.route('/signals') def signals(): return jsonify(signals_cache)

================= START =================

def start(): for s in SYMBOLS: for tf in TIMEFRAMES: fetch_historical(s, tf)

threading.Thread(target=start_ws, daemon=True).start()
threading.Thread(target=loop, daemon=True).start()

if name == 'main': start() app.run(host='0.0.0.0', port=10000)
