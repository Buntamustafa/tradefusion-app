from flask import Flask, jsonify, render_template_string
import requests
import time
import threading
import random

app = Flask(__name__)

TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

signals = []

# 🔔 Send Telegram message
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": message})

# 📊 Generate signals (SIMULATION — replace with your logic)
def generate_signal():
    pairs = ["EURUSD", "GBPUSD", "BTCUSD"]
    types = ["BUY", "SELL"]

    pair = random.choice(pairs)
    signal_type = random.choice(types)

    # Strength logic
    strength = random.choice(["STRONG", "MEDIUM", "SCALP"])

    signal = {
        "pair": pair,
        "type": signal_type,
        "strength": strength,
        "time": time.strftime("%H:%M:%S")
    }

    signals.insert(0, signal)

    msg = f"""
📊 {pair} {signal_type}
🔥 Strength: {strength}
⏰ {signal['time']}
"""
    send_telegram(msg)

# 🔁 Run bot loop
def bot_loop():
    while True:
        generate_signal()
        time.sleep(60)  # every 1 minute

# 🌐 Dashboard UI
@app.route("/dashboard")
def dashboard():
    html = """
    <html>
    <head>
    <title>TradeFusion</title>
    <style>
    body { background:#0b1a2f; color:white; font-family:sans-serif; }
    .card {
        background:#132a4a;
        margin:10px;
        padding:15px;
        border-radius:10px;
    }
    .BUY { color:#00ff88; }
    .SELL { color:#ff4d4d; }
    .STRONG { background:green; padding:5px; }
    .MEDIUM { background:orange; padding:5px; }
    .SCALP { background:blue; padding:5px; }
    </style>
    </head>
    <body>

    <h2>📊 TradeFusion Live Signals</h2>

    {% for s in signals %}
    <div class="card">
        <b>{{s.pair}}</b> 
        <span class="{{s.type}}">{{s.type}}</span><br><br>
        <span class="{{s.strength}}">{{s.strength}}</span><br><br>
        ⏰ {{s.time}}
    </div>
    {% endfor %}

    </body>
    </html>
    """
    return render_template_string(html, signals=signals)

# 🟢 Home route for UptimeRobot
@app.route("/")
def home():
    print("Ping received")
    return "Bot is running ✅"

# 🚀 Start bot thread
threading.Thread(target=bot_loop).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
