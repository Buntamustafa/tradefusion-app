import requests
from flask import Flask, jsonify

app = Flask(__name__)

PAIRS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT"]

last_error = None

# =========================
# 📊 DATA (CRYPTOCOMPARE)
# =========================
def get_klines(symbol, limit=100):
    global last_error

    try:
        base = symbol.replace("USDT", "")

        url = f"https://min-api.cryptocompare.com/data/v2/histominute?fsym={base}&tsym=USDT&limit={limit}"
        res = requests.get(url, timeout=10).json()

        if res.get("Response") != "Success":
            last_error = res
            return None

        data = res["Data"]["Data"]

        closes = [x["close"] for x in data]
        highs = [x["high"] for x in data]
        lows = [x["low"] for x in data]
        volumes = [x["volumeto"] for x in data]

        return closes, highs, lows, volumes

    except Exception as e:
        last_error = str(e)
        return None


# =========================
# 📈 INDICATORS
# =========================
def rsi(data, period=14):
    gains, losses = [], []

    for i in range(1, len(data)):
        diff = data[i] - data[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    if len(gains) < period:
        return 50

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def ema(data, period):
    k = 2 / (period + 1)
    ema_val = data[0]

    for price in data:
        ema_val = price * k + ema_val * (1 - k)

    return ema_val


# =========================
# 💧 HELPERS
# =========================
def liquidity_sweep(highs, lows):
    if highs[-1] > max(highs[-6:-1]):
        return "SELL"
    if lows[-1] < min(lows[-6:-1]):
        return "BUY"
    return None


def breakout(highs, lows):
    if highs[-1] > max(highs[-10:-1]):
        return "BUY"
    if lows[-1] < min(lows[-10:-1]):
        return "SELL"
    return None


def structure_break(closes):
    if closes[-1] > max(closes[-10:-1]):
        return "BUY"
    if closes[-1] < min(closes[-10:-1]):
        return "SELL"
    return None


# =========================
# 🎯 DYNAMIC CONFIDENCE
# =========================
def calculate_confidence(rsi_val, trend_strength, volume_strength, sweep, bos):
    score = 0

    # RSI strength
    if rsi_val < 30 or rsi_val > 70:
        score += 25
    elif rsi_val < 40 or rsi_val > 60:
        score += 15
    else:
        score += 5

    # Trend strength
    score += min(trend_strength * 100, 25)

    # Volume strength
    score += min(volume_strength * 10, 20)

    # Sweep
    if sweep:
        score += 15

    # Structure break
    if bos:
        score += 15

    return min(int(score), 100)


def get_quality(score):
    if score >= 80:
        return "🔥 STRONG"
    elif score >= 65:
        return "⚡ MEDIUM"
    else:
        return "⚠️ LOW"


# =========================
# 🚨 STRATEGY ENGINE
# =========================
def strat_engine(symbol):
    data = get_klines(symbol)

    if not data:
        return [{
            "symbol": symbol,
            "status": "no_data",
            "error": last_error
        }]

    closes, highs, lows, volumes = data

    r = rsi(closes)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)

    trend = "BUY" if ema50 > ema200 else "SELL"
    trend_strength = abs(ema50 - ema200) / closes[-1]

    avg_vol = sum(volumes[-10:]) / 10
    volume_strength = volumes[-1] / avg_vol if avg_vol else 1

    sweep = liquidity_sweep(highs, lows)
    bos = structure_break(closes)
    br = breakout(highs, lows)

    signals = []

    def build(strategy, direction):
        score = calculate_confidence(r, trend_strength, volume_strength, sweep, bos)
        return {
            "symbol": symbol,
            "strategy": strategy,
            "direction": direction,
            "confidence": score,
            "quality": get_quality(score)
        }

    # 🔥 Strategies (relaxed)
    if r < 40:
        signals.append(build("Range_RSI_Liquidity", "BUY"))

    if r > 60:
        signals.append(build("Range_RSI_Liquidity", "SELL"))

    if br:
        signals.append(build("Breakout_Volume", br))

    signals.append(build("MTF_RSI_Trend", trend))

    if sweep:
        signals.append(build("SMC_Sweep_BOS", sweep))

    if trend == "BUY" and r < 50:
        signals.append(build("Trend_Pullback", "BUY"))

    if trend == "SELL" and r > 50:
        signals.append(build("Trend_Pullback", "SELL"))

    # 🔥 NEVER EMPTY
    if not signals:
        fallback = "BUY" if r < 50 else "SELL"
        signals.append({
            "symbol": symbol,
            "strategy": "Fallback",
            "direction": fallback,
            "confidence": 50,
            "quality": "⚠️ LOW"
        })

    return signals


# =========================
# 🌐 ROUTES
# =========================
@app.route("/")
def home():
    return jsonify({
        "status": "🔥 Bot running (CryptoCompare)",
        "pairs": PAIRS
    })


@app.route("/signals")
def signals():
    all_signals = []
    for pair in PAIRS:
        all_signals.extend(strat_engine(pair))
    return jsonify(all_signals)


@app.route("/status")
def status():
    return jsonify({
        "running": True,
        "last_error": last_error
    })


# =========================
# 🚀 START
# =========================
app.run(host="0.0.0.0", port=10000)
