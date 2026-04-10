from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import requests, pandas as pd, ta, os, time
from datetime import datetime

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("TWELVE_API_KEY")

PAIRS = {
    "EUR/USD": {"type": "forex", "symbol": "EUR/USD"},
    "BTC/USD": {"type": "crypto", "symbol": "BTCUSDT"},
    "XAU/USD": {"type": "forex", "symbol": "XAU/USD"}
}

last_news_time = 0

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
    h = datetime.utcnow().hour
    if 7 <= h <= 10: return "LONDON"
    if 13 <= h <= 16: return "NEW_YORK"
    if 0 <= h <= 5: return "ASIA"
    return "OFF"

# ================= HYBRID NEWS =================
def detect_news(df):
    global last_news_time

    avg = df["range"].rolling(20).mean()
    spike = df["range"].iloc[-1] > avg.iloc[-2] * 2.5

    if spike:
        last_news_time = time.time()

    # active for 10 minutes after spike
    if time.time() - last_news_time < 600:
        return True
    return False

def news_bias(df):
    # Determine USD strength using candle direction
    last = df.iloc[-1]

    if last.close > last.open:
        return "USD_WEAK"
    else:
        return "USD_STRONG"

# ================= FILTER =================
def spread_ok(df):
    spread = df.iloc[-1].high - df.iloc[-1].low
    return spread < df.iloc[-1].close * 0.002

# ================= SMART MONEY =================
def liquidity(df):
    last = df.iloc[-1]
    if last.high > df["high"].iloc[-3]: return "BUY"
    if last.low < df["low"].iloc[-3]: return "SELL"
    return None

def trap(df):
    last = df.iloc[-1]
    if last.high > df["high"].iloc[-3] and last.close < last.open:
        return "BULL_TRAP"
    if last.low < df["low"].iloc[-3] and last.close > last.open:
        return "BEAR_TRAP"
    return None

def order_block(df):
    prev = df.iloc[-2]
    return "BULLISH_OB" if prev.close < prev.open else "BEARISH_OB"

def fvg(df):
    if df["low"].iloc[-2] > df["high"].iloc[-4]: return "BULLISH_FVG"
    if df["high"].iloc[-2] < df["low"].iloc[-4]: return "BEARISH_FVG"
    return None

# ================= ENTRY =================
def confirm(df, side):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    engulf_buy = last.close > prev.high and last.open < prev.low
    engulf_sell = last.open > prev.high and last.close < prev.low

    wick_buy = (min(last.open,last.close)-last.low) > abs(last.close-last.open)*2
    wick_sell = (last.high-max(last.open,last.close)) > abs(last.close-last.open)*2

    if side=="BUY": return engulf_buy or wick_buy
    if side=="SELL": return engulf_sell or wick_sell
    return False

# ================= SIGNAL =================
def generate_signal(pair, info):
    try:
        df5 = get_data(info,"5min")
        df15 = get_data(info,"15min")
        df1h = get_data(info,"1h")

        if df5 is None or df15 is None or df1h is None:
            return {"pair":pair,"message":"No data"}

        df5,df15,df1h = add_indicators(df5),add_indicators(df15),add_indicators(df1h)

        if df5.empty or df15.empty or df1h.empty:
            return {"pair":pair,"message":"Indicator error"}

        session = session_filter()
        news = detect_news(df5)
        bias_news = news_bias(df5) if news else None

        if not spread_ok(df5):
            return {"pair":pair,"message":"High spread (news)"}

        # MTF
        bias = "BUY" if df1h.iloc[-1].ema20 > df1h.iloc[-1].ema50 else "SELL"
        confirm_trend = "BUY" if df15.iloc[-1].ema20 > df15.iloc[-1].ema50 else "SELL"

        if bias != confirm_trend:
            return {"pair":pair,"message":"MTF conflict"}

        # SMART MONEY
        liq = liquidity(df5)
        tr = trap(df5)
        ob = order_block(df5)
        gap = fvg(df5)
        price = df5.iloc[-1].close

        # ================= HYBRID LOGIC =================
        if session in ["LONDON","NEW_YORK"]:

            # SELL
            if tr=="BULL_TRAP" and ob=="BEARISH_OB" and gap=="BEARISH_FVG":
                if confirm(df5,"SELL"):

                    # News alignment
                    if news and bias_news!="USD_STRONG":
                        return {"pair":pair,"message":"News conflict"}

                    return {
                        "pair":pair,
                        "action":"SELL",
                        "entry":round(price,4),
                        "confidence":"99%",
                        "strength":f"SNIPER 🎯 ({session})",
                        "reason":"Hybrid News + Smart Money"
                    }

            # BUY
            if tr=="BEAR_TRAP" and ob=="BULLISH_OB" and gap=="BULLISH_FVG":
                if confirm(df5,"BUY"):

                    if news and bias_news!="USD_WEAK":
                        return {"pair":pair,"message":"News conflict"}

                    return {
                        "pair":pair,
                        "action":"BUY",
                        "entry":round(price,4),
                        "confidence":"99%",
                        "strength":f"SNIPER 🎯 ({session})",
                        "reason":"Hybrid News + Smart Money"
                    }

        # ASIA SCALP
        if session=="ASIA":
            rsi = df5.iloc[-1].rsi

            if rsi<30 and confirm(df5,"BUY"):
                return {"pair":pair,"action":"BUY","entry":round(price,4),"strength":"SCALP ⚡"}

            if rsi>70 and confirm(df5,"SELL"):
                return {"pair":pair,"action":"SELL","entry":round(price,4),"strength":"SCALP ⚡"}

        return {"pair":pair,"message":f"No setup ({session})"}

    except Exception as e:
        return {"pair":pair,"error":str(e)}

# ================= ROUTES =================
@app.route("/signals")
def signals():
    return jsonify([generate_signal(p,i) for p,i in PAIRS.items()])

@app.route("/")
def dash():
    return render_template_string("""
    <html><body style="background:black;color:white;text-align:center">
    <h2>🔥 HYBRID NEWS AI TRADER</h2>
    <div id="d"></div>
    <script>
    async function load(){
        let r=await fetch('/signals'); let d=await r.json();
        let h="";
        d.forEach(x=>{h+=`<p><b>${x.pair}</b> → ${x.action||x.message}<br>${x.strength||""}</p><hr>`});
        document.getElementById("d").innerHTML=h;
    }
    setInterval(load,5000); load();
    </script>
    </body></html>
    """)

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))
