from flask import Flask, jsonify
from flask_cors import CORS
import requests, pandas as pd, os, time
from datetime import datetime

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("TWELVE_API_KEY")

CACHE = {}
CACHE_TTL = 60

PAIRS = {
    "EUR/USD": "EURUSD",
    "BTC/USD": "BTCUSDT",
    "XAU/USD": "XAUUSD"
}

# ===============================
# 🔥 CACHE
# ===============================
def get_cache(pair):
    if pair in CACHE:
        data, t = CACHE[pair]
        if time.time() - t < CACHE_TTL:
            return data
    return None

def set_cache(pair, data):
    CACHE[pair] = (data, time.time())

# ===============================
# 🔥 DATA
# ===============================
def get_binance(symbol, tf="5m"):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf}&limit=100"
        data = requests.get(url).json()

        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "ct","qv","n","tb","tq","ignore"
        ])
        df = df.astype(float)
        return df
    except:
        return None

def get_twelve(symbol):
    if not API_KEY:
        return None
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=100&apikey={API_KEY}"
        data = requests.get(url).json()
        if "values" not in data:
            return None

        df = pd.DataFrame(data["values"])
        df = df.astype(float)
        return df
    except:
        return None

def get_data(pair, symbol):
    cached = get_cache(pair)
    if cached is not None:
        return cached

    df = None

    if "BTC" in pair:
        df = get_binance(symbol)

    if df is None:
        df = get_twelve(symbol)

    if df is not None and not df.empty:
        set_cache(pair, df)
        return df

    return None

def get_htf_data(symbol):
    return get_binance(symbol, "1h")

# ===============================
# 🔥 SESSION
# ===============================
def get_session():
    hour = datetime.utcnow().hour
    if 7 <= hour <= 11:
        return "LONDON"
    elif 13 <= hour <= 17:
        return "NEW_YORK"
    return "OFF"

# ===============================
# 🔥 NEWS FILTER (NO API)
# ===============================
def news_filter(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    move = abs(last["close"] - prev["close"])

    if move > df["close"].std() * 2:
        return True
    return False

# ===============================
# 🔥 HTF BIAS
# ===============================
def get_htf_bias(df):
    if df is None or len(df) < 50:
        return None

    last = df["close"].iloc[-1]
    ma = df["close"].rolling(50).mean().iloc[-1]

    if last > ma:
        return "BUY"
    elif last < ma:
        return "SELL"

    return None

# ===============================
# 🔥 LIQUIDITY SWEEP
# ===============================
def liquidity_sweep(df):
    high = df["high"].rolling(10).max().iloc[-2]
    low = df["low"].rolling(10).min().iloc[-2]

    last = df.iloc[-1]

    if last["high"] > high:
        return "BUY"
    elif last["low"] < low:
        return "SELL"
    return None

# ===============================
# 🔥 FVG
# ===============================
def fvg_zone(df):
    for i in range(len(df)-3, len(df)-1):
        if df["low"].iloc[i] > df["high"].iloc[i-2]:
            return ("BUY", df["high"].iloc[i-2], df["low"].iloc[i])
        if df["high"].iloc[i] < df["low"].iloc[i-2]:
            return ("SELL", df["low"].iloc[i-2], df["high"].iloc[i])
    return None

# ===============================
# 🔥 ORDER BLOCK
# ===============================
def order_block_zone(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last["close"] > prev["high"]:
        return ("BUY", prev["low"], prev["high"])
    if last["close"] < prev["low"]:
        return ("SELL", prev["high"], prev["low"])

    return None

# ===============================
# 🔥 SNIPER ENTRY (PRECISION)
# ===============================
def sniper_entry(df, direction, zone_low, zone_high):
    price = df["close"].iloc[-1]

    # Entry only if price returns into zone
    if direction == "BUY":
        if zone_low <= price <= zone_high:
            return True
    elif direction == "SELL":
        if zone_high <= price <= zone_low:
            return True

    return False

# ===============================
# 🔥 CANDLE CONFIRMATION
# ===============================
def candle_confirm(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        return "BUY"
    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        return "SELL"

    return None

# ===============================
# 🔥 FINAL ENGINE
# ===============================
def generate_signal(df, htf_df):
    if df is None or len(df) < 20:
        return None

    # HTF bias
    htf_bias = get_htf_bias(htf_df)
    if not htf_bias:
        return None

    # News filter
    if news_filter(df):
        return None

    # Session filter
    session = get_session()
    if session == "OFF":
        return None

    # Core logic
    liq = liquidity_sweep(df)
    fvg = fvg_zone(df)
    ob = order_block_zone(df)
    confirm = candle_confirm(df)

    if not (liq and fvg and ob and confirm):
        return None

    direction = liq

    # Alignment check
    if not (direction == fvg[0] == ob[0] == confirm == htf_bias):
        return None

    # 🔥 SNIPER ZONE MERGE (FVG + OB)
    zone_low = min(fvg[1], ob[1])
    zone_high = max(fvg[2], ob[2])

    # 🔥 ENTRY PRECISION
    if not sniper_entry(df, direction, zone_low, zone_high):
        return None

    return {
        "direction": direction,
        "htf_bias": htf_bias,
        "zone_low": round(zone_low, 5),
        "zone_high": round(zone_high, 5)
    }

# ===============================
# 🚀 ROUTE
# ===============================
@app.route("/signals")
def signals():
    results = []

    for pair, symbol in PAIRS.items():

        df = get_data(pair, symbol)
        htf_df = get_htf_data(symbol)

        if df is None or htf_df is None:
            results.append({"pair": pair, "message": "No data"})
            continue

        signal = generate_signal(df, htf_df)

        if signal:
            results.append({
                "pair": pair,
                "action": signal["direction"],
                "htf_bias": signal["htf_bias"],
                "entry_zone": [signal["zone_low"], signal["zone_high"]],
                "session": get_session(),
                "confidence": "92% 🔥"
            })
        else:
            results.append({
                "pair": pair,
                "message": "No sniper setup"
            })

    return jsonify(results)

@app.route("/")
def home():
    return "TradeFusion Sniper Bot Running 🚀"
