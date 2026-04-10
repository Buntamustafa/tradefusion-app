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
# CACHE
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
# DATA SOURCES
# ===============================
def get_binance(symbol, tf="5m"):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={tf}&limit=100"
        data = requests.get(url, timeout=5).json()

        df = pd.DataFrame(data, columns=[
            "time","open","high","low","close","volume",
            "ct","qv","n","tb","tq","ignore"
        ])
        df = df.astype(float)
        return df
    except:
        return None

def get_yahoo(pair, tf="5m"):
    try:
        import yfinance as yf

        mapping = {
            "EUR/USD": "EURUSD=X",
            "XAU/USD": "GC=F",
            "BTC/USD": "BTC-USD"
        }

        period = "1d" if tf == "5m" else "2d"

        ticker = yf.download(mapping[pair], interval=tf, period=period)

        if ticker.empty:
            return None

        df = ticker.reset_index()
        df.columns = ["time","open","high","low","close","volume"]

        return df
    except:
        return None

def get_twelve(symbol):
    if not API_KEY:
        return None
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=100&apikey={API_KEY}"
        data = requests.get(url, timeout=5).json()

        if "values" not in data:
            return None

        df = pd.DataFrame(data["values"])
        df = df.astype(float)

        return df
    except:
        return None

# ===============================
# 🔥 DATA PIPELINE (FIXED)
# ===============================
def get_data(pair, symbol):
    cached = get_cache(pair)
    if cached is not None:
        return cached

    df = None

    # Binance first (BTC best)
    try:
        if "BTC" in pair:
            df = get_binance(symbol)
    except:
        df = None

    # Yahoo fallback
    if df is None:
        df = get_yahoo(pair, "5m")

    # Twelve fallback
    if df is None:
        df = get_twelve(symbol)

    if df is not None and not df.empty:
        set_cache(pair, df)
        return df

    return None

# ===============================
# 🔥 HTF DATA (FIXED)
# ===============================
def get_htf_data(pair, symbol):
    df = None

    # Binance first
    try:
        if "BTC" in pair:
            df = get_binance(symbol, "1h")
    except:
        df = None

    # Yahoo fallback (CRITICAL FIX)
    if df is None:
        df = get_yahoo(pair, "1h")

    return df

# ===============================
# SESSION
# ===============================
def get_session():
    hour = datetime.utcnow().hour
    if 7 <= hour <= 11:
        return "LONDON"
    elif 13 <= hour <= 17:
        return "NEW_YORK"
    return "OFF"

# ===============================
# FILTERS
# ===============================
def volatility_filter(df):
    atr = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
    avg = df["close"].rolling(50).std().iloc[-1]
    return avg * 0.3 < atr < avg * 3

def spread_filter(df):
    spread = df["high"].iloc[-1] - df["low"].iloc[-1]
    avg = (df["high"] - df["low"]).rolling(20).mean().iloc[-1]
    return spread < avg * 2

def news_filter(df):
    move = abs(df["close"].iloc[-1] - df["close"].iloc[-2])
    return move > df["close"].std() * 2

# ===============================
# HTF BIAS
# ===============================
def get_htf_bias(df):
    if df is None or len(df) < 50:
        return None

    ma = df["close"].rolling(50).mean().iloc[-1]
    price = df["close"].iloc[-1]

    if price > ma:
        return "BUY"
    elif price < ma:
        return "SELL"

    return None

# ===============================
# SMART MONEY LOGIC
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

def fvg_zone(df):
    for i in range(len(df)-3, len(df)-1):
        if df["low"].iloc[i] > df["high"].iloc[i-2]:
            return ("BUY", df["high"].iloc[i-2], df["low"].iloc[i])
        if df["high"].iloc[i] < df["low"].iloc[i-2]:
            return ("SELL", df["low"].iloc[i-2], df["high"].iloc[i])
    return None

def order_block_zone(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last["close"] > prev["high"]:
        return ("BUY", prev["low"], prev["high"])
    if last["close"] < prev["low"]:
        return ("SELL", prev["high"], prev["low"])

    return None

def candle_confirm(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        return "BUY"
    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        return "SELL"
    return None

# ===============================
# 🔥 SNIPER ENTRY
# ===============================
def sniper_entry(df, direction, zone_low, zone_high):
    price = df["close"].iloc[-1]
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if direction == "BUY":
        if not (zone_low <= price <= zone_high):
            return False
    else:
        if not (zone_high <= price <= zone_low):
            return False

    body = abs(last["close"] - last["open"])
    wick = (last["high"] - last["low"]) - body
    rejection = wick > body * 1.5

    if direction == "BUY":
        structure = last["close"] > prev["high"]
    else:
        structure = last["close"] < prev["low"]

    return rejection and structure

# ===============================
# 🚀 ENGINE
# ===============================
def generate_signal(df, htf_df):
    if df is None or len(df) < 20:
        return None

    if news_filter(df):
        return None

    if not volatility_filter(df):
        return None

    if not spread_filter(df):
        return None

    if get_session() == "OFF":
        return None

    htf_bias = get_htf_bias(htf_df)
    if not htf_bias:
        return None

    liq = liquidity_sweep(df)
    fvg = fvg_zone(df)
    ob = order_block_zone(df)
    confirm = candle_confirm(df)

    if not (liq and fvg and ob and confirm):
        return None

    if not (liq == fvg[0] == ob[0] == confirm == htf_bias):
        return None

    zone_low = min(fvg[1], ob[1])
    zone_high = max(fvg[2], ob[2])

    if not sniper_entry(df, liq, zone_low, zone_high):
        return None

    return {
        "direction": liq,
        "zone_low": round(zone_low, 5),
        "zone_high": round(zone_high, 5),
        "htf_bias": htf_bias
    }

# ===============================
# ROUTES
# ===============================
@app.route("/signals")
def signals():
    results = []

    for pair, symbol in PAIRS.items():
        df = get_data(pair, symbol)
        htf_df = get_htf_data(pair, symbol)

        if df is None or htf_df is None:
            results.append({"pair": pair, "message": "No data"})
            continue

        signal = generate_signal(df, htf_df)

        if signal:
            results.append({
                "pair": pair,
                "action": signal["direction"],
                "entry_zone": [signal["zone_low"], signal["zone_high"]],
                "htf_bias": signal["htf_bias"],
                "session": get_session(),
                "confidence": "95% 🔥"
            })
        else:
            results.append({
                "pair": pair,
                "message": "No sniper setup"
            })

    return jsonify(results)

@app.route("/")
def home():
    return "TradeFusion Prop Sniper Running 🚀"
