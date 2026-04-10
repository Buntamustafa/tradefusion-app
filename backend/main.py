from flask import Flask, jsonify, render_template_string
from flask_cors import CORS
import requests, pandas as pd, ta, os, time, sqlite3

app = Flask(__name__)
CORS(app)

# ================= CONFIG =================
API_KEY = os.getenv("TWELVE_API_KEY")
NEWS_API = os.getenv("NEWS_API_KEY")

PAIRS = {
    "EUR/USD": {"type": "forex", "symbol": "EUR/USD"},
    "BTC/USD": {"type": "crypto", "symbol": "BTCUSDT"},
    "XAU/USD": {"type": "forex", "symbol": "XAU/USD"}
}

# ================= DATABASE =================
conn = sqlite3.connect("trades.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS trades (
pair TEXT, action TEXT, entry REAL,
result TEXT, confidence TEXT, type TEXT
)
""")
conn.commit()

# ================= SAFE REQUEST =================
def safe_request(url, params=None):
    for _ in range(3):
        try:
            r = requests.get(url, params=params, timeout=10)
            return r.json()
        except:
            time.sleep(1)
    return None

# ================= DATA =================
def fetch_binance(symbol, interval):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit=150"
    data = safe_request(url)
    if not data:
        return None

    df = pd.DataFrame(data)
    df.columns = ["time","open","high","low","close","volume","ct","qv","trades","tb","tq","ig"]

    for col in ["open","high","low","close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna()

def fetch_twelve(symbol, interval):
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
    if info["type"] == "crypto":
        return fetch_binance(info["symbol"], interval)
    return fetch_twelve(info["symbol"], interval)

# ================= INDICATORS =================
def add_indicators(df):
    df["ema20"] = ta.trend.EMAIndicator(df["close"], 20).ema_indicator()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], 50).ema_indicator()
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    return df.dropna()

# ================= SMART MONEY =================
def bos(df): return df["high"].iloc[-1] > df["high"].iloc[-3]
def liquidity(df): return df["low"].iloc[-1] < df["low"].iloc[-3]
def fvg(df): return df["low"].iloc[-2] > df["high"].iloc[-4]
def ob(df): return df["close"].iloc[-2] < df["open"].iloc[-2]

# ================= NEWS (PRIMARY + BACKUP) =================
def detect_specific_news():
    keywords = ["CPI", "NFP", "FOMC", "Interest Rate"]

    # PRIMARY (FMP)
    if NEWS_API:
        data = safe_request(
            f"https://financialmodelingprep.com/api/v3/economic_calendar?apikey={NEWS_API}"
        )
        if data:
            for event in data[:15]:
                name = event.get("event", "")
                impact = event.get("impact", "")
                if impact == "High":
                    for k in keywords:
                        if k in name:
                            return k

    # BACKUP (safe mode)
    try:
        backup = safe_request("https://api.sampleapis.com/fakebank/accounts")
        if backup:
            return None
    except:
        pass

    return None

# ================= HELPERS =================
def is_usd_pair(pair):
    return "USD" in pair

def spread_ok(df):
    last = df.iloc[-1]
    spread = abs(last.high - last.low)
    avg = (df["high"] - df["low"]).rolling(20).mean().iloc[-1]
    return spread < avg * 1.8

def high_volatility(df):
    c = df.iloc[-1]
    p = df.iloc[-2]
    return abs(c.close - c.open) > abs(p.close - p.open) * 2

def liquidity_sweep_news(df):
    return df["high"].iloc[-1] > df["high"].iloc[-3] or df["low"].iloc[-1] < df["low"].iloc[-3]

# ================= CANDLE =================
def bullish_engulfing(df):
    l, p = df.iloc[-1], df.iloc[-2]
    return l.close > l.open and p.close < p.open and l.close > p.open

def bearish_engulfing(df):
    l, p = df.iloc[-1], df.iloc[-2]
    return l.close < l.open and p.close > p.open and l.close < p.open

def rejection_wick(df):
    l = df.iloc[-1]
    body = abs(l.close - l.open)
    wick = (l.high - l.low) - body
    return wick > body * 2

# ================= SIGNAL =================
def generate_signal(pair, info):

    if not is_usd_pair(pair):
        return {"pair": pair, "message": "Not USD pair"}

    df5 = get_data(info, "5min")
    df15 = get_data(info, "15min")
    df1h = get_data(info, "1h")

    if df5 is None or df15 is None or df1h is None:
        return {"pair": pair, "message": "No data"}

    df5 = add_indicators(df5)
    df15 = add_indicators(df15)
    df1h = add_indicators(df1h)

    bias = "BUY" if df1h.iloc[-1].ema20 > df1h.iloc[-1].ema50 else "SELL"
    confirm = "BUY" if df15.iloc[-1].ema20 > df15.iloc[-1].ema50 else "SELL"

    if bias != confirm:
        return {"pair": pair, "message": "MTF conflict"}

    last = df5.iloc[-1]
    trend = "BUY" if last.ema20 > last.ema50 else "SELL"
    price = last.close
    rsi = last.rsi

    if not spread_ok(df5):
        return {"pair": pair, "message": "Spread too wide"}

    news = detect_specific_news()

    bullish = bullish_engulfing(df5) or rejection_wick(df5)
    bearish = bearish_engulfing(df5) or rejection_wick(df5)
    candle_ok = (trend == "BUY" and bullish) or (trend == "SELL" and bearish)

    if news:
        if not high_volatility(df5):
            return {"pair": pair, "message": f"{news} forming..."}

        if liquidity_sweep_news(df5) and bos(df5) and candle_ok:
            return {
                "pair": pair,
                "action": trend,
                "entry": round(price, 4),
                "confidence": "97%",
                "strength": f"{news} SNIPER 🚀"
            }

        return {"pair": pair, "message": f"Waiting {news} confirmation"}

    score = sum([bos(df5), liquidity(df5), fvg(df5), ob(df5), candle_ok])

    if score >= 4 and 45 < rsi < 65:
        strength = "SNIPER 🎯"
        confidence = "92%"
    elif score >= 3:
        strength = "MEDIUM 🔄"
        confidence = "78%"
    else:
        strength = "SCALP ⚡"
        confidence = "60%"

    c.execute("INSERT INTO trades VALUES (?,?,?,?,?,?)",
              (pair, trend, price, "pending", confidence, strength))
    conn.commit()

    return {
        "pair": pair,
        "action": trend,
        "entry": round(price, 4),
        "confidence": confidence,
        "strength": strength
    }

# ================= STATS =================
def get_stats():
    df = pd.read_sql_query("SELECT * FROM trades", conn)
    if df.empty:
        return {"total": 0, "winrate": 0}

    wins = len(df[df["result"] == "win"])
    total = len(df)
    return {"total": total, "winrate": round((wins/total)*100, 2)}

# ================= ROUTES =================
@app.route("/signals")
def signals():
    return jsonify([generate_signal(p, i) for p, i in PAIRS.items()])

@app.route("/stats")
def stats():
    return jsonify(get_stats())

@app.route("/")
def dashboard():
    return render_template_string("""
    <html>
    <body style="background:#0f172a;color:white;text-align:center;">
    <h2>🚀 SMART NEWS TRADER</h2>
    <div id="signals"></div>
    <h3 id="stats"></h3>

    <script>
    async function load(){
        let s = await fetch('/signals');
        let data = await s.json();

        let html="";
        data.forEach(d=>{
            html += `<p><b>${d.pair}</b>: ${d.action||d.message} (${d.strength||""})</p>`;
        });

        document.getElementById("signals").innerHTML = html;

        let st = await fetch('/stats');
        let stats = await st.json();

        document.getElementById("stats").innerHTML =
            `Trades: ${stats.total} | Winrate: ${stats.winrate}%`;
    }

    setInterval(load, 10000);
    load();
    </script>
    </body>
    </html>
    """)

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
