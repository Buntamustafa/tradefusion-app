from flask import Flask, jsonify
from flask_cors import CORS
import pandas as pd
import yfinance as yf
from telegram_bot import send_telegram

app = Flask(__name__)
CORS(app)

PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDCAD": "CAD=X",
    "XAUUSD": "GC=F",
    "BTCUSD": "BTC-USD"
}

# =========================
# DATA FETCH
# =========================
def get_data(symbol, interval="5m"):
    try:
        df = yf.download(symbol, period="1d", interval=interval)
        df.dropna(inplace=True)
        return df
    except:
        return None

# =========================
# MARKET STRUCTURE (BOS)
# =========================
def detect_bos(df):
    highs = df['High']
    lows = df['Low']

    if highs.iloc[-1] > highs.iloc[-5:-1].max():
        return "bullish"
    elif lows.iloc[-1] < lows.iloc[-5:-1].min():
        return "bearish"
    return None

# =========================
# FAIR VALUE GAP (FVG)
# =========================
def detect_fvg(df):
    for i in range(len(df)-3, len(df)-1):
        if df['Low'].iloc[i] > df['High'].iloc[i-1]:
            return "bullish"
        if df['High'].iloc[i] < df['Low'].iloc[i-1]:
            return "bearish"
    return None

# =========================
# ORDER BLOCK
# =========================
def detect_ob(df):
    last = df.iloc[-2]

    if last['Close'] > last['Open']:
        return "bullish"
    elif last['Close'] < last['Open']:
        return "bearish"
    return None

# =========================
# VOLATILITY FILTER
# =========================
def volatility_ok(df):
    range_avg = (df['High'] - df['Low']).rolling(10).mean().iloc[-1]
    return range_avg > 0.0005  # adjust per asset

# =========================
# SPREAD FILTER (approx)
# =========================
def spread_ok(df):
    spread = abs(df['Close'].iloc[-1] - df['Open'].iloc[-1])
    return spread < 0.002

# =========================
# MULTI TIMEFRAME ALIGNMENT
# =========================
def mtf_alignment(symbol):
    df_15m = get_data(symbol, "15m")
    df_5m = get_data(symbol, "5m")

    if df_15m is None or df_5m is None:
        return None

    bos_15 = detect_bos(df_15m)
    bos_5 = detect_bos(df_5m)

    if bos_15 == bos_5:
        return bos_5

    return None

# =========================
# SNIPER ENGINE
# =========================
def sniper_signal(pair, symbol):
    df = get_data(symbol)

    if df is None or len(df) < 20:
        return {"pair": pair, "message": "No data"}

    direction = mtf_alignment(symbol)
    fvg = detect_fvg(df)
    ob = detect_ob(df)

    if not volatility_ok(df):
        return {"pair": pair, "message": "Low volatility"}

    if not spread_ok(df):
        return {"pair": pair, "message": "High spread"}

    price = df['Close'].iloc[-1]

    # 🎯 PERFECT SNIPER
    if direction and direction == fvg == ob:
        msg = f"""
🔥 SNIPER TRADE
Pair: {pair}
Direction: {direction.upper()}
Entry: {round(price, 5)}
        """
        send_telegram(msg)

        return {
            "pair": pair,
            "type": "SNIPER",
            "direction": direction,
            "entry": price
        }

    # ⚠️ EARLY ALERT (UPGRADE SNIPER)
    confluence = [direction, fvg, ob]
    if confluence.count(direction) >= 2 and direction is not None:
        msg = f"""
⚠️ ALMOST SNIPER
Pair: {pair}
Bias: {direction.upper()}
Wait for confirmation...
        """
        send_telegram(msg)

        return {
            "pair": pair,
            "type": "EARLY",
            "direction": direction
        }

    return {"pair": pair, "message": "No sniper setup"}

# =========================
# API ROUTE
# =========================
@app.route("/")
def home():
    results = []

    for pair, symbol in PAIRS.items():
        result = sniper_signal(pair, symbol)
        results.append(result)

    return jsonify(results)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run()
