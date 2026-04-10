import requests
import time
import threading
from flask import Flask, render_template_string
import yfinance as yf
import pandas as pd

# ================= CONFIG =================
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

SYMBOLS = ["EURUSD=X", "GBPUSD=X", "USDJPY=X"]

app = Flask(__name__)

last_signal = {}
last_sent_time = {}
latest_signals = []

COOLDOWN = 900  # 15 mins


# ================= TELEGRAM =================
def send_telegram(symbol, signal, strength):
    message = f"""
🚨 TRADEFUSION ALERT 🚨

📊 Pair: {symbol}

📈 Signal: {signal}
🔥 Strength: {strength}

⚡ Action:
- STRONG → Enter immediately
- MEDIUM → Wait confirmation
- SCALP → Quick trade

🕒 Time: {time.strftime("%H:%M:%S")}
"""

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            "chat_id": CHAT_ID,
            "text": message
        })
    except:
        print("Telegram error")


# ================= RSI =================
def calculate_rsi(data, period=14):
    delta = data["Close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


# ================= DATA =================
def get_data(symbol, interval):
    df = yf.download(symbol, interval=interval, period="2d")
    df["RSI"] = calculate_rsi(df)
    return df.dropna()


# ================= SIGNAL LOGIC =================
def generate_signal(df15, df1h):
    rsi15 = df15["RSI"].iloc[-1]
    rsi1h = df1h["RSI"].iloc[-1]

    # BUY
    if rsi15 < 30 and rsi1h < 40:
        return "BUY", "STRONG"

    if rsi15 < 35:
        return "BUY", "MEDIUM"

    if rsi15 < 45:
        return "BUY", "SCALP"

    # SELL
    if rsi15 > 70 and rsi1h > 60:
        return "SELL", "STRONG"

    if rsi15 > 65:
        return "SELL", "MEDIUM"

    if rsi15 > 55:
        return "SELL", "SCALP"

    return None, None


# ================= COOLDOWN =================
def can_send(symbol):
    now = time.time()
    if symbol not in last_sent_time:
        return True
    return (now - last_sent_time[symbol]) > COOLDOWN


# ================= MARKET SCANNER =================
def scan_market():
    while True:
        for symbol in SYMBOLS:
            try:
                df15 = get_data(symbol, "15m")
                df1h = get_data(symbol, "1h")

                signal, strength = generate_signal(df15, df1h)

                if signal and last_signal.get(symbol) != signal and can_send(symbol):

                    last_signal[symbol] = signal
                    last_sent_time[symbol] = time.time()

                    # Save for dashboard
                    latest_signals.append({
                        "symbol": symbol,
                        "signal": signal,
                        "strength": strength,
                        "time": time.strftime("%H:%M:%S")
                    })

                    # Send Telegram alert
                    send_telegram(symbol, signal, strength)

            except Exception as e:
                print("Error:", e)

        time.sleep(60)


# ================= UPTIMEROBOT ROUTE =================
@app.route("/")
def home():
    print("Ping received")
    return "Bot is running ✅"


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    html = """
    <html>
    <head>
        <title>TradeFusion Signals</title>
        <meta http-equiv="refresh" content="10">
    </head>
    <body style="background:#0f172a;color:white;font-family:sans-serif;padding:20px">

        <h1>📊 TradeFusion Live Signals</h1>
        <p>Status: 🟢 Running</p>

        {% for s in signals %}
            <div style="
                margin:15px 0;
                padding:15px;
                border-radius:10px;
                background:#111827;
            ">
                <h2>{{s.symbol}}</h2>

                <p style="font-size:18px;">
                    {% if s.signal == "BUY" %}
                        🟢 BUY
                    {% else %}
                        🔴 SELL
                    {% endif %}
                </p>

                <p>
                    {% if s.strength == "STRONG" %}
                        <span style="color:lime;font-weight:bold;">🔥 STRONG</span>
                    {% elif s.strength == "MEDIUM" %}
                        <span style="color:orange;font-weight:bold;">⚡ MEDIUM</span>
                    {% else %}
                        <span style="color:cyan;font-weight:bold;">💨 SCALP</span>
                    {% endif %}
                </p>

                <small>{{s.time}}</small>
            </div>
        {% endfor %}

    </body>
    </html>
    """
    return render_template_string(html, signals=latest_signals[-10:])


# ================= RUN =================
if __name__ == "__main__":
    threading.Thread(target=scan_market).start()
    app.run(host="0.0.0.0", port=10000)
