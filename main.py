import requests
from flask import Flask, jsonify

app = Flask(__name__)

PAIRS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT"]

# =========================
# 📊 DATA
# =========================
def get_klines(symbol, interval="1m", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    res = requests.get(url).json()

    if not isinstance(res, list):
        return None

    closes = [float(x[4]) for x in res]
    highs = [float(x[2]) for x in res]
    lows = [float(x[3]) for x in res]
    volumes = [float(x[5]) for x in res]

    return closes, highs, lows, volumes


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
# 🎯 DYNAMIC SCORING
# =========================
def calculate_confidence(rsi_val, trend_strength, volume_strength, sweep, bos):
    score = 0

    # RSI contribution
    if rsi_val < 30 or rsi_val > 70:
        score += 25
    elif rsi_val < 40 or rsi_val > 60:
        score += 15
    else:
        score += 5

    # Trend strength (EMA distance)
    score += min(trend_strength * 100, 25)

    # Volume strength
    score += min(volume_strength * 100, 20)

    # Liquidity sweep
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
# 🚨 STRATEGIES
# =========================

def strat_engine(symbol):
    data = get_klines(symbol)
    if not data:
        return []

    closes, highs, lows, volumes = data

    r = rsi(closes)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)

    trend = "BUY" if ema50 > ema200 else "SELL"
    trend_strength = abs(ema50 - ema200) / closes[-1]

    avg_vol = sum(volumes[-10:]) / 10
    volume_strength = volumes[-1] / avg_vol if avg_vol > 0 else 1

    sweep = liquidity_sweep(highs, lows)
    bos = structure_break(closes)
    br = breakout(highs, lows)

    signals = []

    # =========================
    # 1. Range + RSI + Liquidity
    # =========================
    if r < 30 and sweep == "BUY":
        score = calculate_confidence(r, trend_strength, volume_strength, sweep, bos)
        signals.append({
            "symbol": symbol,
            "strategy": "Range_RSI_Liquidity",
            "direction": "BUY",
            "confidence": score,
            "quality": get_quality(score)
        })

    if r > 70 and sweep == "SELL":
        score = calculate_confidence(r, trend_strength, volume_strength, sweep, bos)
        signals.append({
            "symbol": symbol,
            "strategy": "Range_RSI_Liquidity",
            "direction": "SELL",
            "confidence": score,
            "quality": get_quality(score)
        })

    # =========================
    # 2. Breakout + Volume
    # =========================
    if br and volume_strength > 1.2:
        score = calculate_confidence(r, trend_strength, volume_strength, sweep, bos)
        signals.append({
            "symbol": symbol,
            "strategy": "Breakout_Volume",
            "direction": br,
            "confidence": score,
            "quality": get_quality(score)
        })

    # =========================
    # 3. MTF + RSI + Trend
    # =========================
    if trend == "BUY" and r < 40:
        score = calculate_confidence(r, trend_strength, volume_strength, sweep, bos)
        signals.append({
            "symbol": symbol,
            "strategy": "MTF_RSI_Trend",
            "direction": "BUY",
            "confidence": score,
            "quality": get_quality(score)
        })

    if trend == "SELL" and r > 60:
        score = calculate_confidence(r, trend_strength, volume_strength, sweep, bos)
        signals.append({
            "symbol": symbol,
            "strategy": "MTF_RSI_Trend",
            "direction": "SELL",
            "confidence": score,
            "quality": get_quality(score)
        })

    # =========================
    # 4. SMC Sweep + BOS
    # =========================
    if sweep and bos and sweep == bos:
        score = calculate_confidence(r, trend_strength, volume_strength, sweep, bos)
        signals.append({
            "symbol": symbol,
            "strategy": "SMC_Sweep_BOS",
            "direction": bos,
            "confidence": score,
            "quality": get_quality(score)
        })

    # =========================
    # 5. Trend Pullback
    # =========================
    if trend == "BUY" and r < 45:
        score = calculate_confidence(r, trend_strength, volume_strength, sweep, bos)
        signals.append({
            "symbol": symbol,
            "strategy": "Trend_Pullback",
            "direction": "BUY",
            "confidence": score,
            "quality": get_quality(score)
        })

    if trend == "SELL" and r > 55:
        score = calculate_confidence(r, trend_strength, volume_strength, sweep, bos)
        signals.append({
            "symbol": symbol,
            "strategy": "Trend_Pullback",
            "direction": "SELL",
            "confidence": score,
            "quality": get_quality(score)
        })

    return signals


# =========================
# 🌐 ROUTES
# =========================
@app.route("/signals")
def signals():
    all_signals = []

    for pair in PAIRS:
        all_signals.extend(strat_engine(pair))

    return jsonify(all_signals)


@app.route("/")
def home():
    return jsonify({
        "status": "🔥 Dynamic Multi-Strategy Bot Running",
        "pairs": PAIRS
    })


# =========================
# 🚀 START
# =========================
app.run(host="0.0.0.0", port=10000)
