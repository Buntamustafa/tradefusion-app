from flask import Flask, render_template_string
import requests, time, threading
import pandas as pd

app = Flask(__name__)

TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

signals = []

# 👥 MULTI PAIRS
PAIRS = ["BTCUSDT", "ETHUSDT"]

# 🔔 TELEGRAM
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# 📊 DATA
def get_data(symbol, interval="15m"):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
    data = requests.get(url).json()
    df = pd.DataFrame(data)
    df.columns = ["time","o","h","l","c","v","ct","qv","n","tbb","tbq","ig"]
    df["c"] = df["c"].astype(float)
    df["h"] = df["h"].astype(float)
    df["l"] = df["l"].astype(float)
    df["o"] = df["o"].astype(float)
    return df

# 📈 RSI
def rsi(df, period=14):
    delta = df["c"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# 💧 LIQUIDITY SWEEP
def liquidity_sweep(df):
    prev_high = df["h"].iloc[-5:-1].max()
    prev_low = df["l"].iloc[-5:-1].min()

    if df["h"].iloc[-1] > prev_high and df["c"].iloc[-1] < prev_high:
        return "SELL"
    if df["l"].iloc[-1] < prev_low and df["c"].iloc[-1] > prev_low:
        return "BUY"
    return None

# 🧠 ORDER BLOCK
def order_block(df):
    if df["c"].iloc[-3] < df["o"].iloc[-3] and df["c"].iloc[-1] > df["h"].iloc[-3]:
        return "BUY"
    if df["c"].iloc[-3] > df["o"].iloc[-3] and df["c"].iloc[-1] < df["l"].iloc[-3]:
        return "SELL"
    return None

# 📍 ZONE
def liquidity_zone(df):
    high = df["h"].rolling(10).max().iloc[-1]
    low = df["l"].rolling(10).min().iloc[-1]
    price = df["c"].iloc[-1]

    if price >= high * 0.995:
        return "HIGH_ZONE"
    if price <= low * 1.005:
        return "LOW_ZONE"
    return "MID"

# 🧠 SIGNAL LOGIC
def generate_signal(pair):
    df_15m = get_data(pair, "15m")
    df_1h = get_data(pair, "1h")

    trend_up = df_1h["c"].iloc[-1] > df_1h["c"].iloc[-10]

    sweep = liquidity_sweep(df_15m)
    ob = order_block(df_15m)
    zone = liquidity_zone(df_15m)
    rsi_val = rsi(df_15m).iloc[-1]

    signal_type = None
    strength = "SCALP"

    # 🟣 ELITE
    if trend_up and sweep == "BUY" and ob == "BUY" and zone == "LOW_ZONE" and rsi_val < 35:
        signal_type = "BUY"
        strength = "ELITE"

    elif not trend_up and sweep == "SELL" and ob == "SELL" and zone == "HIGH_ZONE" and rsi_val > 65:
        signal_type = "SELL"
        strength = "ELITE"

    # 🔥 STRONG
    elif sweep == ob and sweep is not None:
        signal_type = sweep
        strength = "STRONG"

    # ⚡ MEDIUM
    elif sweep:
        signal_type = sweep
        strength = "MEDIUM"

    if signal_type:
        price = df_15m["c"].iloc[-1]

        if signal_type == "BUY":
            entry = round(price, 2)
            sl = round(price - 100, 2)
            tp = round(price + 200, 2)
        else:
            entry = round(price, 2)
            sl = round(price + 100, 2)
            tp = round(price - 200, 2)

        signal = {
            "pair": pair,
            "type": signal_type,
            "strength": strength,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "time": time.strftime("%H:%M:%S")
        }

        signals.insert(0, signal)

        msg = f"""
📊 {pair} {signal_type}
🔥 {strength}
💰 Entry: {entry}
🛑 SL: {sl}
🎯 TP: {tp}
⏰ {signal['time']}
"""
        send_telegram(msg)

# 🔁 LOOP
def bot_loop():
    while True:
        try:
            for pair in PAIRS:
                generate_signal(pair)
        except Exception as e:
            print(e)
        time.sleep(60)

# 🌐 DASHBOARD
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
    <html>
    <head>
        <meta http-equiv="refresh" content="10">
    </head>

    <body style="background:#0b1a2f;color:white;font-family:sans-serif;padding:15px;">

    <h2>📊 TradeFusion PRO Signals</h2>

    {% if signals|length == 0 %}
        <div style="background:#132a4a;padding:20px;border-radius:10px;">
            ⚠️ No signals yet...
        </div>
    {% endif %}

    {% for s in signals %}
    <div style="background:#132a4a;padding:15px;margin:10px 0;border-radius:12px;">

        <b>{{s.pair}}</b> | {{s.type}} | ⏰ {{s.time}}<br><br>

        {% if s.strength == "ELITE" %}
            <span style="background:purple;padding:5px 10px;border-radius:8px;">🟣 ELITE</span>
        {% elif s.strength == "STRONG" %}
            <span style="background:red;padding:5px 10px;border-radius:8px;">🔥 STRONG</span>
        {% elif s.strength == "MEDIUM" %}
            <span style="background:orange;padding:5px 10px;border-radius:8px;">⚡ MEDIUM</span>
        {% else %}
            <span style="background:gray;padding:5px 10px;border-radius:8px;">⚠️ SCALP</span>
        {% endif %}

        <br><br>

        💰 Entry: {{s.entry}}<br>
        🛑 SL: {{s.sl}}<br>
        🎯 TP: {{s.tp}}

    </div>

    <!-- 🔊 SOUND ALERT -->
    <audio autoplay>
        <source src="https://www.soundjay.com/buttons/sounds/button-3.mp3" type="audio/mpeg">
    </audio>

    {% endfor %}

    </body>
    </html>
    """, signals=signals)

@app.route("/")
def home():
    return "Bot running ✅"

# 🚀 START
threading.Thread(target=bot_loop).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
