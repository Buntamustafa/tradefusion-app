from flask import Flask, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
import yfinance as yf
from telegram_bot import send_telegram

app = Flask(__name__)
CORS(app)

PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDCAD": "USDCAD=X",
    "XAUUSD": "GC=F",
    "BTCUSD": "BTC-USD"
}

# =========================
# FETCH DATA
# =========================
def get_data(symbol, interval="5m"):
    try:
        df = yf.download(symbol, period="2d", interval=interval, progress=False)
        df.dropna(inplace=True)
        return df
    except:
        return None

# =========================
# STRUCTURE (BOS)
# =========================
def detect_bos(df):
    if len(df) < 20:
        return None

    if df["High"].iloc[-1] > df["High"].iloc[-5:-1].max():
        return "bullish"

    if df["Low"].iloc[-1] < df["Low"].iloc[-5:-1].min():
        return "bearish"

    return None

# =========================
# FVG (Improved)
# =========================
def detect_fvg(df):
    if len(df) < 5:
        return None

    for i in range(len(df)-3, len(df)-1):
        if df["Low"].iloc[i] > df["High"].iloc[i-1]:
            return "bullish"
        if df["High"].iloc[i] < df["Low"].iloc[i-1]:
            return "bearish"

    return None

# =========================
# ORDER BLOCK (Improved)
# =========================
def detect_ob(df):
    candles = df.iloc[-6:-1]

    bullish = candles[candles["Close"] < candles["Open"]]
    bearish = candles[candles["Close"] > candles["Open"]]

    if len(bullish) >= 3:
        return "bullish"

    if len(bearish) >= 3:
        return "bearish"

    return None

# =========================
# LIQUIDITY SWEEP (NEW)
# =========================
def liquidity_sweep(df):
    recent_high = df["High"].iloc[-1]
    prev_high = df["High"].iloc[-10:-1].max()

    recent_low = df["Low"].iloc[-1]
    prev_low = df["Low"].iloc[-10:-1].min()

    if recent_high > prev_high:
        return "sell"
    if recent_low < prev_low:
        return "buy"

    return None

# =========================
# SNIPER ENTRY CANDLE
# =========================
def sniper_candle(df, direction):
    candle = df.iloc[-1]

    body = abs(candle["Close"] - candle["Open"])
    wick = candle["High"] - candle["Low"]

    if direction == "bullish":
        return candle["Close"] > candle["Open"] and body > wick * 0.6

    if direction == "bearish":
        return candle["Close"] < candle["Open"] and body > wick * 0.6

    return False

# =========================
# VOLATILITY FILTER
# =========================
def volatility_ok(df):
    atr = (df["High"] - df["Low"]).rolling(14).mean().iloc[-1]
    return atr > atr.mean()

# =========================
# SPREAD FILTER (SIMULATED)
# =========================
def spread_ok(df):
    spread = abs(df["Close"].iloc[-1] - df["Open"].iloc[-1])
    candle_range = df["High"].iloc[-1] - df["Low"].iloc[-1]
    return spread < candle_range * 0.4

# =========================
# MULTI-TIMEFRAME ALIGNMENT
# =========================
def mtf_alignment(symbol):
    df_5 = get_data(symbol, "5m")
    df_15 = get_data(symbol, "15m")

    if df_5 is None or df_15 is None:
        return None

    bos_5 = detect_bos(df_5)
    bos_15 = detect_bos(df_15)

    if bos_5 == bos_15:
        return bos_5

    return None

# =========================
# ACCURACY BOOST (NEW CORE)
# =========================
def confidence_score(bos, fvg, ob, sweep):
    score = 0

    if bos: score += 25
    if fvg: score += 25
    if ob: score += 25
    if sweep: score += 25

    return score

# =========================
# SNIPER ENGINE (FINAL)
# =========================
def sniper_signal(pair, symbol):
    df = get_data(symbol)

    if df is None or len(df) < 50:
        return {"pair": pair, "message": "No data"}

    bos = detect_bos(df)
    fvg = detect_fvg(df)
    ob = detect_ob(df)
    sweep = liquidity_sweep(df)
    mtf = mtf_alignment(symbol)

    if not mtf:
        return {"pair": pair, "message": "No MTF alignment"}

    if not volatility_ok(df):
        return {"pair": pair, "message": "Low volatility"}

    if not spread_ok(df):
        return {"pair": pair, "message": "High spread"}

    score = confidence_score(bos, fvg, ob, sweep)

    direction = mtf
    price = df["Close"].iloc[-1]

    # 🔥 STRICT SNIPER (HIGH CONFIDENCE ONLY)
    if score >= 75 and bos == fvg == ob == mtf:
        if sniper_candle(df, direction):
            message = f"""
🔥 SNIPER TRADE

Pair: {pair}
Direction: {direction.upper()}
Entry: {round(price,5)}

Confidence: {score}%
"""
            send_telegram(message)

            return {
                "pair": pair,
                "signal": direction,
                "confidence": score
            }

    # ⚠️ EARLY WARNING (CONTROLLED)
    if score >= 50:
        send_telegram(f"⚠️ {pair} forming setup... ({score}%)")

        return {
            "pair": pair,
            "type": "EARLY",
            "confidence": score
        }

    return {"pair": pair, "message": "No sniper setup"}

# =========================
# ROUTE
# =========================
@app.route("/")
def home():
    results = []

    for pair, symbol in PAIRS.items():
        results.append(sniper_signal(pair, symbol))

    return jsonify(results)

if __name__ == "__main__":
    app.run()
