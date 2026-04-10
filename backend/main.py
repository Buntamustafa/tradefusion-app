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
# 🔥 DATA SOURCES
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

def get_yahoo(pair):
    try:
        import yfinance as yf

        mapping = {
            "EUR/USD": "EURUSD=X",
            "XAU/USD": "GC=F",
            "BTC/USD": "BTC-USD"
        }

        ticker = yf.download(mapping[pair], interval="5m", period="1d")

        if ticker.empty:
            return None

        df = ticker.reset_index()
        df.columns = ["time","open","high","low","close","volume"]

        return df

    except:
        return None

def get_data(pair, symbol):
    cached = get_cache(pair)
    if cached is not None:
        return cached

    df = None

    # Crypto → Binance
    if "BTC" in pair:
        df = get_binance(symbol)

    # Forex/Gold → Twelve
    if df is None:
        df = get_twelve(symbol)

    # Final fallback → Yahoo (no API)
    if df is None:
        df = get_yahoo(pair)

    if df is not None and not df.empty:
        set_cache(pair, df)
        return df

    return None

def get_htf_data(symbol):
    return get_binance(symbol, "1h")

# ===============================
# 🔥 SESSION FILTER
# ===============================
def get_session():
    hour = datetime.utcnow().hour
    if 7 <= hour <= 11:
        return "LONDON"
    elif 13 <= hour <= 17:
        return "NEW_YORK"
    return "OFF"

# ===============================
# 🔥 VOLATILITY FILTER
# ===============================
def volatility_filter(df):
    atr = (df["high"] - df["low"]).rolling(14).mean().iloc[-1]
    avg = df["close"].rolling(50).std().iloc[-1]

    # avoid low volatility (dead market)
    if atr < avg * 0.3:
        return False

    # avoid extreme volatility (news spikes)
    if atr > avg * 3:
        return False

    return True

# ===============================
# 🔥 SPREAD FILTER (SIMULATED)
# ===============================
def spread_filter(df):
    spread = (df["high"].iloc[-1] - df["low"].iloc[-1])

    avg_spread = (df["high"] - df["low"]).rolling(20).mean().iloc[-1]

    # if current spread too wide → skip
    if spread > avg_spread * 2:
        return False

    return True

# ===============================
# 🔥 NEWS FILTER (NO API)
# ===============================
def news_filter(df):
    move = abs(df["close"].iloc[-1] - df["close"].iloc[-2])
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
# 🔥 SNIPER ENTRY
# ===============================
def sniper_entry(df, direction, zone_low, zone_high):
    price = df["close"].iloc[-1]

    if direction == "BUY":
        return zone_low <= price <= zone_high
    if direction == "SELL":
        return zone_high <= price <= zone_low

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
# 🚀 FINAL ENGINE
# ===============================
def generate_signal(df, htf_df):
    if df is None or len(df) < 20:
        return None

    # Filters
    if news_filter(df):
        return None

    if not volatility_filter(df):
        return None

    if not spread_filter(df):
        return None

    if get_session() == "OFF":
        return None

    # HTF
    htf_bias = get_htf_bias(htf_df)
    if not htf_bias:
        return None

    # Core logic
    liq = liquidity_sweep(df)
    fvg = fvg_zone(df)
    ob = order_block_zone(df)
    confirm = candle_confirm(df)

    if not (liq and fvg and ob and confirm):
        return None

    if not (liq == fvg[0] == ob[0] == confirm == htf_bias):
        return None

    # Sniper zone
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
# 🌐 ROUTE
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
                "entry_zone": [signal["zone_low"], signal["zone_high"]],
                "htf_bias": signal["htf_bias"],
                "session": get_session(),
                "confidence": "93% 🔥"
            })
        else:
            results.append({
                "pair": pair,
                "message": "No sniper setup"
            })

    return jsonify(results)

@app.route("/")
def home():
    return "TradeFusion Pro Running 🚀"
