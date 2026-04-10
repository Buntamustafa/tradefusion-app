from flask import Flask, render_template_string
import requests, time, threading
import pandas as pd

app = Flask(__name__)

TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

signals = []

# 🔔 Telegram
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# 📊 Get data
def get_data(symbol="BTCUSDT", interval="15m"):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100"
    data = requests.get(url).json()
    df = pd.DataFrame(data)
    df.columns = ["time","o","h","l","c","v","ct","qv","n","tbb","tbq","ig"]
    df["c"] = df["c"].astype(float)
    df["h"] = df["h"].astype(float)
    df["l"] = df["l"].astype(float)
    df["o"] = df["o"].astype(float)
    return df

# 🔥 BOS
def detect_bos(df):
    return df["c"].iloc[-1] > df["h"].iloc[-5]

# ⚡ FVG
def detect_fvg(df):
    return df["l"].iloc[-2] > df["h"].iloc[-4]

# 📈 RSI
def rsi(df, period=14):
    delta = df["c"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# 💧 Liquidity Sweep
def liquidity_sweep(df):
    prev_high = df["h"].iloc[-5:-1].max()
    prev_low = df["l"].iloc[-5:-1].min()

    current_high = df["h"].iloc[-1]
    current_low = df["l"].iloc[-1]
    close = df["c"].iloc[-1]

    if current_high > prev_high and close < prev_high:
        return "SELL"
    if current_low < prev_low and close > prev_low:
        return "BUY"
    return None

# 🧠 ORDER BLOCK DETECTION
def order_block(df):
    # Last bearish candle before strong move up → bullish OB
    if df["c"].iloc[-3] < df["o"].iloc[-3] and df["c"].iloc[-1] > df["h"].iloc[-3]:
        return "BUY"

    # Last bullish candle before strong move down → bearish OB
    if df["c"].iloc[-3] > df["o"].iloc[-3] and df["c"].iloc[-1] < df["l"].iloc[-3]:
        return "SELL"

    return None

# 📍 SIMPLE LIQUIDITY ZONE
def liquidity_zone(df):
    high_zone = df["h"].rolling(10).max().iloc[-1]
    low_zone = df["l"].rolling(10).min().iloc[-1]
    price = df["c"].iloc[-1]

    if price >= high_zone * 0.995:
        return "HIGH_ZONE"
    elif price <= low_zone * 1.005:
        return "LOW_ZONE"
    return "MID"

# 📰 News filter
def news_filter(df):
    return abs(df["c"].iloc[-1] - df["c"].iloc[-2]) > 50

# 🧠 SIGNAL LOGIC
def generate_signal():
    df_15m = get_data(interval="15m")
    df_1h = get_data(interval="1h")

    trend_up = df_1h["c"].iloc[-1] > df_1h["c"].iloc[-10]

    bos = detect_bos(df_15m)
    fvg = detect_fvg(df_15m)
    rsi_val = rsi(df_15m).iloc[-1]
    sweep = liquidity_sweep(df_15m)
    ob = order_block(df_15m)
    zone = liquidity_zone(df_15m)
    news = news_filter(df_15m)

    signal_type = None
    strength = "SCALP"

    # 🔥 ELITE LOGIC
    if trend_up and sweep == "BUY" and ob == "BUY" and zone == "LOW_ZONE" and rsi_val < 40:
        signal_type = "BUY"
        strength = "STRONG"

    elif not trend_up and sweep == "SELL" and ob == "SELL" and zone == "HIGH_ZONE" and rsi_val > 60:
        signal_type = "SELL"
        strength = "STRONG"

    elif sweep == ob:
        signal_type = sweep
        strength = "MEDIUM"

    # ⚠️ News adjustment
    if news:
        strength = "SCALP"

    if signal_type:
        signal = {
            "pair": "BTCUSDT",
            "type": signal_type,
            "strength": strength,
            "time": time.strftime("%H:%M:%S")
        }

        signals.insert(0, signal)

        msg = f"""
📊 BTCUSDT {signal_type}
🔥 {strength}
🧠 OB + Liquidity + BOS + FVG
📍 Zone: {zone}
⏰ {signal['time']}
"""
        send_telegram(msg)

# 🔁 LOOP
def bot_loop():
    while True:
        try:
            generate_signal()
        except Exception as e:
            print(e)
        time.sleep(60)

# 🌐 DASHBOARD
@app.route("/dashboard")
def dashboard():
    return render_template_string("""
    <html>
    <body style="background:#0b1a2f;color:white;font-family:sans-serif;">
    <h2>📊 TradeFusion ELITE Signals</h2>

    {% for s in signals %}
    <div style="background:#132a4a;padding:15px;margin:10px;border-radius:10px;">
        <b>{{s.pair}}</b> - {{s.type}}<br>
        <b>{{s.strength}}</b><br>
        ⏰ {{s.time}}
    </div>
    {% endfor %}
    </body>
    </html>
    """, signals=signals)

@app.route("/")
def home():
    print("Ping received")
    return "Bot running ✅"

threading.Thread(target=bot_loop).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
