from flask import Flask, jsonify, render_template_string
import requests, time, threading
import pandas as pd
import numpy as np

app = Flask(__name__)
signals = []

PAIRS = ["BTCUSDT", "ETHUSDT"]

# =========================
# 📊 GET DATA
# =========================
def get_data(symbol, interval="15m"):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=200"
    data = requests.get(url).json()
    df = pd.DataFrame(data)
    df.columns = ["time","o","h","l","c","v","ct","qv","n","tbb","tbq","ig"]
    df["c"] = df["c"].astype(float)
    df["h"] = df["h"].astype(float)
    df["l"] = df["l"].astype(float)
    df["o"] = df["o"].astype(float)
    return df

# =========================
# 📈 RSI
# =========================
def rsi(df, period=14):
    delta = df["c"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# =========================
# 💥 VOLATILITY FILTER (ATR)
# =========================
def atr(df, period=14):
    df["tr"] = np.maximum(df["h"] - df["l"], 
                np.maximum(abs(df["h"] - df["c"].shift()), abs(df["l"] - df["c"].shift())))
    return df["tr"].rolling(period).mean()

# =========================
# 🔥 BOS
# =========================
def bos(df):
    if df["h"].iloc[-1] > df["h"].iloc[-5:-1].max():
        return "BUY"
    if df["l"].iloc[-1] < df["l"].iloc[-5:-1].min():
        return "SELL"
    return None

# =========================
# 💧 LIQUIDITY SWEEP
# =========================
def sweep(df):
    if df["h"].iloc[-1] > df["h"].iloc[-5:-1].max() and df["c"].iloc[-1] < df["h"].iloc[-5:-1].max():
        return "SELL"
    if df["l"].iloc[-1] < df["l"].iloc[-5:-1].min() and df["c"].iloc[-1] > df["l"].iloc[-5:-1].min():
        return "BUY"
    return None

# =========================
# 🧠 ORDER BLOCK
# =========================
def order_block(df):
    if df["c"].iloc[-3] < df["o"].iloc[-3] and df["c"].iloc[-1] > df["h"].iloc[-3]:
        return "BUY"
    if df["c"].iloc[-3] > df["o"].iloc[-3] and df["c"].iloc[-1] < df["l"].iloc[-3]:
        return "SELL"
    return None

# =========================
# ⚡ FVG
# =========================
def fvg(df):
    if df["l"].iloc[-2] > df["h"].iloc[-4]:
        return "BUY"
    if df["h"].iloc[-2] < df["l"].iloc[-4]:
        return "SELL"
    return None

# =========================
# 🧱 ADVANCED LIQUIDITY ZONES
# =========================
def liquidity_zone(df):
    high = df["h"].rolling(50).max().iloc[-1]
    low = df["l"].rolling(50).min().iloc[-1]
    price = df["c"].iloc[-1]

    if price > high * 0.995:
        return "SELL_ZONE"
    elif price < low * 1.005:
        return "BUY_ZONE"
    return "MID"

# =========================
# 📉 TREND (1H)
# =========================
def trend(df):
    return "UP" if df["c"].iloc[-1] > df["c"].iloc[-20] else "DOWN"

# =========================
# 🌍 SESSION FILTER
# =========================
def session():
    hour = int(time.strftime("%H"))
    if 7 <= hour <= 16:
        return "LONDON"
    elif 13 <= hour <= 22:
        return "NEWYORK"
    return "ASIA"

# =========================
# 📰 NEWS SMART FILTER
# =========================
def news_filter(df):
    current_atr = atr(df).iloc[-1]
    avg_atr = atr(df).rolling(50).mean().iloc[-1]

    if current_atr > avg_atr * 1.5:
        return "HIGH_IMPACT"
    return "NORMAL"

# =========================
# 🎯 SIGNAL ENGINE
# =========================
def generate_signal(pair):
    df15 = get_data(pair, "15m")
    df1h = get_data(pair, "1h")
    df1m = get_data(pair, "1m")

    confirmations = 0
    direction = None

    checks = [
        sweep(df15),
        order_block(df15),
        bos(df15),
        fvg(df15)
    ]

    for c in checks:
        if c:
            confirmations += 1
            direction = c

    sniper = bos(df1m)
    trend_dir = trend(df1h)
    zone = liquidity_zone(df15)
    market_session = session()
    news = news_filter(df15)

    # =========================
    # 🎯 CLASSIFICATION
    # =========================
    strength = "SCALP"

    if confirmations >= 4 and sniper == direction:
        strength = "STRONG"
    elif confirmations >= 2:
        strength = "MEDIUM"

    # =========================
    # 🚫 TREND FILTER
    # =========================
    if trend_dir == "UP" and direction == "SELL":
        return
    if trend_dir == "DOWN" and direction == "BUY":
        return

    # =========================
    # 🌍 SESSION ADJUSTMENT
    # =========================
    if market_session == "ASIA" and strength == "STRONG":
        strength = "MEDIUM"

    # =========================
    # 📰 NEWS ADJUSTMENT
    # =========================
    if news == "HIGH_IMPACT":
        strength = "SCALP"

    if direction:
        price = df15["c"].iloc[-1]
        atr_val = atr(df15).iloc[-1]

        # =========================
        # 💰 DYNAMIC RISK
        # =========================
        sl = round(price - atr_val, 2) if direction == "BUY" else round(price + atr_val, 2)
        tp = round(price + atr_val * 2, 2) if direction == "BUY" else round(price - atr_val * 2, 2)

        signal = {
            "pair": pair,
            "type": direction,
            "strength": strength,
            "entry": round(price, 2),
            "sl": sl,
            "tp": tp,
            "session": market_session,
            "time": time.strftime("%H:%M:%S")
        }

        signals.insert(0, signal)

# =========================
# 🔁 LOOP
# =========================
def bot_loop():
    while True:
        try:
            for pair in PAIRS:
                generate_signal(pair)
        except Exception as e:
            print(e)
        time.sleep(60)

# =========================
# 🌐 API
# =========================
@app.route("/api/signals")
def api():
    return jsonify(signals[:20])

# =========================
# 🚀 START
# =========================
threading.Thread(target=bot_loop).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
