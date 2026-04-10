import yfinance as yf
import pandas as pd
import numpy as np
import time
import threading
import schedule

from telegram_bot import send_telegram


# =========================
# SETTINGS
# =========================
SYMBOLS = ["EURUSD=X", "GBPUSD=X", "XAUUSD=X"]
TIMEFRAME = "1m"


# =========================
# HELPERS
# =========================
def get_data(symbol, interval="1m", period="1d"):
    df = yf.download(symbol, interval=interval, period=period, progress=False)
    df.dropna(inplace=True)
    return df


def is_kill_zone():
    # London + NY session (UTC)
    hour = pd.Timestamp.utcnow().hour
    return (6 <= hour <= 10) or (12 <= hour <= 16)


def detect_trend(df):
    df["ema50"] = df["Close"].ewm(span=50).mean()
    df["ema200"] = df["Close"].ewm(span=200).mean()

    if df["ema50"].iloc[-1] > df["ema200"].iloc[-1]:
        return "BUY"
    elif df["ema50"].iloc[-1] < df["ema200"].iloc[-1]:
        return "SELL"
    return None


def break_of_structure(df):
    recent_high = df["High"].rolling(10).max().iloc[-2]
    recent_low = df["Low"].rolling(10).min().iloc[-2]

    if df["Close"].iloc[-1] > recent_high:
        return "BUY"
    elif df["Close"].iloc[-1] < recent_low:
        return "SELL"
    return None


def liquidity_sweep(df):
    high_sweep = df["High"].iloc[-1] > df["High"].iloc[-2]
    low_sweep = df["Low"].iloc[-1] < df["Low"].iloc[-2]

    if high_sweep:
        return "SELL"
    elif low_sweep:
        return "BUY"
    return None


def order_block(df):
    last_candle = df.iloc[-2]
    current = df.iloc[-1]

    if last_candle["Close"] < last_candle["Open"] and current["Close"] > current["Open"]:
        return "BUY"
    elif last_candle["Close"] > last_candle["Open"] and current["Close"] < current["Open"]:
        return "SELL"
    return None


def sniper_entry(df):
    # 1-minute precision entry
    candle = df.iloc[-1]

    body = abs(candle["Close"] - candle["Open"])
    wick = candle["High"] - candle["Low"]

    if body / wick > 0.6:
        return True
    return False


# =========================
# SIGNAL ENGINE
# =========================
def generate_signal(symbol):
    df_1m = get_data(symbol, "1m")
    df_5m = get_data(symbol, "5m")

    if len(df_1m) < 50 or len(df_5m) < 50:
        return None

    trend = detect_trend(df_5m)
    bos = break_of_structure(df_1m)
    sweep = liquidity_sweep(df_1m)
    ob = order_block(df_1m)
    sniper = sniper_entry(df_1m)

    score = 0
    direction = trend

    if trend == bos:
        score += 2
    if trend == sweep:
        score += 2
    if trend == ob:
        score += 2
    if sniper:
        score += 2

    if not is_kill_zone():
        score -= 2  # reduce strength outside session

    if score >= 6:
        strength = "🔥 STRONG"
    elif score >= 4:
        strength = "⚡ MEDIUM"
    else:
        return None

    price = df_1m["Close"].iloc[-1]

    return {
        "symbol": symbol,
        "direction": direction,
        "strength": strength,
        "price": price
    }


# =========================
# SCANNER
# =========================
def scan_market():
    print("Scanning market...")

    for symbol in SYMBOLS:
        signal = generate_signal(symbol)

        if signal:
            message = f"""
🚀 SIGNAL ALERT

Pair: {signal['symbol']}
Type: {signal['direction']}
Strength: {signal['strength']}
Entry: {signal['price']}

⏰ Kill Zone: {"YES" if is_kill_zone() else "NO"}
"""
            print(message)
            send_telegram(message)


# =========================
# AUTO LOOP
# =========================
def run_bot():
    schedule.every(1).minutes.do(scan_market)

    while True:
        schedule.run_pending()
        time.sleep(1)


# =========================
# START
# =========================
if __name__ == "__main__":
    send_telegram("🤖 Bot is LIVE and scanning markets...")

    thread = threading.Thread(target=run_bot)
    thread.start()
