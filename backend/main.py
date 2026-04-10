from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import requests, pandas as pd, ta, os
from datetime import datetime

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("TWELVE_API_KEY")

PAIRS = {
    "EUR/USD": {"type": "forex", "symbol": "EUR/USD"},
    "BTC/USD": {"type": "crypto", "symbol": "BTCUSDT"},
    "XAU/USD": {"type": "forex", "symbol": "XAU/USD"}
}

# ================= DATA =================
def safe_request(url, params=None):
    try:
        return requests.get(url, params=params, timeout=5).json()
    except:
        return None

def fetch_binance(symbol, interval):
    data = safe_request(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=100")
    if not data: return None

    df = pd.DataFrame(data)
    df.columns = ["t","o","h","l","c","v","ct","qv","n","tb","tq","ig"]

    for col in ["o","h","l","c"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.rename(columns={"o":"open","h":"high","l":"low","c":"close"}).dropna()

def fetch_twelve(symbol, interval):
    if not API_KEY: return None

    data = safe_request(
        "https://api.twelvedata.com/time_series",
        {"symbol": symbol, "interval": interval, "apikey": API_KEY}
    )

    if not data or "values" not in data:
        return None

    df = pd.DataFrame(data["values"]).iloc[::-1]

    for col in ["open","high","low","close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna()

def get_data(info, interval):
    return fetch_binance(info["symbol"], interval) if info["type"]=="crypto" else fetch_twelve(info["symbol"], interval)

# ================= INDICATORS =================
def add_indicators(df):
    df["ema20"] = ta.trend.EMAIndicator(df["close"], 20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], 50).ema_indicator()
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["range"] = df["high"] - df["low"]
    return df.dropna()

# ================= SESSION =================
def session_filter():
    now = datetime.utcnow().hour

    if 7 <= now <= 10:
        return "LONDON"
    if 13 <= now <= 16:
        return "NEW_YORK"
    if 0 <= now <= 5:
        return "ASIA"

    return "OFF_SESSION"

# ================= NEWS =================
def detect_news_volatility(df):
    avg = df["range"].rolling(20).mean()
    if df["range"].iloc[-1] > avg.iloc[-2] * 2.5:
        return True
    return False

def spread_filter(df):
    spread = df.iloc[-1].high - df.iloc[-1].low
    if spread > df.iloc[-1].close * 0.002:
        return False
    return True

# ================= SMART MONEY =================
def liquidity_sweep(df):
    last = df.iloc[-1]
    if last.high > df["high"].iloc[-3]:
        return "BUY_LIQUIDITY"
    if last.low < df["low"].iloc[-3]:
        return "SELL_LIQUIDITY"
    return None

def fake_breakout(df):
    last = df.iloc[-1]
    if last.high > df["high"].iloc[-3] and last.close < last.open:
        return "BULL_TRAP"
    if last.low < df["low"].iloc[-3] and last.close > last.open:
        return "BEAR_TRAP"
    return None

def order_block(df):
    prev = df.iloc[-2]
    if prev.close > prev.open:
        return "BEARISH_OB"
    if prev.close < prev.open:
        return "BULLISH_OB"
    return None

def fvg(df):
    if df["low"].iloc[-2] > df["high"].iloc[-4]:
        return "BULLISH_FVG"
    if df["high"].iloc[-2] < df["low"].iloc[-4]:
        return "BEARISH_FVG"
    return None

# ================= ENTRY =================
def entry_confirmation(df, direction):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    body = abs(last.close - last.open)

    bullish_engulf = last.close > last.open and last.close > prev.high and last.open < prev.low
    bearish_engulf = last.close < last.open and last.open > prev.high and last.close < prev.low

    lower_wick = min(last.open, last.close) - last.low
    upper_wick = last.high - max(last.open, last.close)

    bullish_reject = lower_wick > body * 2
    bearish_reject = upper_wick > body * 2

    if direction == "BUY":
        return bullish_engulf or bullish_reject
    if direction == "SELL":
        return bearish_engulf or bearish_reject

    return False

# ================= SIGNAL =================
def generate_signal(pair, info):
    try:
        df5 = get_data(info, "5min")
        df15 = get_data(info, "15min")
        df1h = get_data(info, "1h")

        if df5 is None or df15 is None or df1h is None:
            return {"pair": pair, "message": "No data"}

        df5 = add_indicators(df5)
        df15 = add_indicators(df15)
        df1h = add_indicators(df1h)

        if df5.empty or df15.empty or df1h.empty:
            return {"pair": pair, "message": "Indicator error"}

        session = session_filter()
        news = detect_news_volatility(df5)
        spread_ok = spread_filter(df5)

        if not spread_ok:
            return {"pair": pair, "message": "High spread (news)"}

        bias = "BUY" if df1h.iloc[-1].ema20 > df1h.iloc[-1].ema50 else "SELL"
        confirm = "BUY" if df15.iloc[-1].ema20 > df15.iloc[-1].ema50 else "SELL"

        if bias != confirm:
            return {"pair": pair, "message": "MTF conflict"}

        liquidity = liquidity_sweep(df5)
        trap = fake_breakout(df5)
        ob = order_block(df5)
        gap = fvg(df5)

        price = df5.iloc[-1].close

        # ================= SESSION SWITCH =================

        # 🔥 SNIPER (London/NY)
        if session in ["LONDON", "NEW_YORK"]:
            if trap and liquidity and ob and gap:

                if trap == "BULL_TRAP" and ob == "BEARISH_OB" and gap == "BEARISH_FVG":
                    if entry_confirmation(df5, "SELL"):
                        return {
                            "pair": pair,
                            "action": "SELL",
                            "entry": round(price,4),
                            "confidence": "99%",
                            "strength": f"SNIPER 🎯 ({session})",
                            "reason": "Full confluence + confirmation"
                        }

                if trap == "BEAR_TRAP" and ob == "BULLISH_OB" and gap == "BULLISH_FVG":
                    if entry_confirmation(df5, "BUY"):
                        return {
                            "pair": pair,
                            "action": "BUY",
                            "entry": round(price,4),
                            "confidence": "99%",
                            "strength": f"SNIPER 🎯 ({session})",
                            "reason": "Full confluence + confirmation"
                        }

        # 💤 SCALP (Asia)
        if session == "ASIA":
            rsi = df5.iloc[-1].rsi

            if rsi < 30 and entry_confirmation(df5, "BUY"):
                return {
                    "pair": pair,
                    "action": "BUY",
                    "entry": round(price,4),
                    "confidence": "65%",
                    "strength": "SCALP ⚡ (ASIA)",
                    "reason": "RSI oversold + confirmation"
                }

            if rsi > 70 and entry_confirmation(df5, "SELL"):
                return {
                    "pair": pair,
                    "action": "SELL",
                    "entry": round(price,4),
                    "confidence": "65%",
                    "strength": "SCALP ⚡ (ASIA)",
                    "reason": "RSI overbought + confirmation"
                }

        return {"pair": pair, "message": f"No setup ({session})"}

    except Exception as e:
        return {"pair": pair, "error": str(e)}

# ================= ROUTES =================
@app.route("/signals")
def signals():
    return jsonify([generate_signal(p, i) for p, i in PAIRS.items()])

@app.route("/")
def dashboard():
    return render_template_string("""
    <html>
    <body style="background:black;color:white;text-align:center">
    <h2>🔥 PRO AI TRADER</h2>
    <div id="data"></div>

    <script>
    async function load(){
        let r = await fetch('/signals');
        let d = await r.json();

        let html="";
        d.forEach(x=>{
            html += `<p><b>${x.pair}</b> → ${x.action||x.message}<br>${x.strength||""}<br>${x.reason||""}</p><hr>`;
        });

        document.getElementById("data").innerHTML = html;
    }

    setInterval(load,5000);
    load();
    </script>
    </body>
    </html>
    """)

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
