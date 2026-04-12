// ===============================
// 🔐 DERIV CONNECTION
// ===============================
const API_TOKEN = "pat_e7824954e7059f0eaf5adda6be29c4f468e349e9027e1b23a5b93d5aa9803d58";
const WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089";

let ws;

// ===============================
// 📊 PAIRS
// ===============================
const symbols = [
  "frxEURUSD",
  "frxXAUUSD",
  "frxUSOIL",
  "cryBTCUSD",
  "cryETHUSD"
];

// ===============================
// 🔊 SOUND ALERT
// ===============================
function playSound() {
  const audio = new Audio("https://www.soundjay.com/buttons/sounds/beep-01a.mp3");
  audio.play();
}

// ===============================
// 🧠 STATE CONTROL
// ===============================
const lastSignalTime = {};

// ===============================
// 🔌 CONNECT
// ===============================
function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log("✅ Connected");
    authorize();
  };

  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);

    if (data.msg_type === "authorize") {
      console.log("🔐 Authorized");
      startFetching();
      setInterval(startFetching, 60000);
    }

    if (data.msg_type === "candles") {
      analyzeMarket(data);
    }
  };

  ws.onerror = (err) => console.log("❌ Error:", err);

  ws.onclose = () => {
    console.log("🔄 Reconnecting...");
    setTimeout(connect, 3000);
  };
}

// ===============================
// 🔐 AUTHORIZE
// ===============================
function authorize() {
  ws.send(JSON.stringify({
    authorize: API_TOKEN
  }));
}

// ===============================
// 📡 FETCH DATA
// ===============================
function startFetching() {
  symbols.forEach(symbol => {
    ws.send(JSON.stringify({
      ticks_history: symbol,
      style: "candles",
      granularity: 60,
      count: 100,
      end: "latest"
    }));
  });
}

// ===============================
// 🧠 MARKET ANALYSIS
// ===============================
function analyzeMarket(data) {
  const candles = data.candles;
  const symbol = data.echo_req.ticks_history;

  if (!candles || candles.length < 20) return;

  const c1 = candles[candles.length - 3];
  const c2 = candles[candles.length - 2];
  const c3 = candles[candles.length - 1];

  // ===============================
  // 🧩 ORIGINAL LOGIC (UNCHANGED)
  // ===============================
  let bosUp = c3.high > c2.high && c2.high > c1.high;
  let bosDown = c3.low < c2.low && c2.low < c1.low;
  let bos = bosUp || bosDown;

  let sweepUp = c3.high > c2.high && c3.close < c2.high;
  let sweepDown = c3.low < c2.low && c3.close > c2.low;
  let sweep = sweepUp || sweepDown;

  let fvgUp = c1.high < c3.low;
  let fvgDown = c1.low > c3.high;
  let fvg = fvgUp || fvgDown;

  // ===============================
  // 🧠 NEW: SWING DETECTION
  // ===============================
  let swingHigh = null;
  let swingLow = null;

  for (let i = candles.length - 10; i < candles.length - 2; i++) {
    if (
      candles[i].high > candles[i - 1].high &&
      candles[i].high > candles[i + 1].high
    ) {
      swingHigh = candles[i].high;
    }

    if (
      candles[i].low < candles[i - 1].low &&
      candles[i].low < candles[i + 1].low
    ) {
      swingLow = candles[i].low;
    }
  }

  // ===============================
  // 🧩 STRONG BOS (SWING BASED)
  // ===============================
  let strongBosUp = swingHigh && c3.close > swingHigh;
  let strongBosDown = swingLow && c3.close < swingLow;

  // ===============================
  // 📈 TREND STRUCTURE
  // ===============================
  let trend = "RANGE";

  if (strongBosUp) trend = "UPTREND";
  else if (strongBosDown) trend = "DOWNTREND";

  // ===============================
  // 🎯 DIRECTION FILTER
  // ===============================
  let direction = null;

  if (trend === "UPTREND" && (sweepUp || fvgUp)) {
    direction = "BUY";
  }

  if (trend === "DOWNTREND" && (sweepDown || fvgDown)) {
    direction = "SELL";
  }

  // ===============================
  // 🎯 SIGNAL + QUALITY
  // ===============================
  let signal = null;
  let quality = "";

  if (trend !== "RANGE" && strongBosUp && sweep && fvg) {
    signal = "SNIPER ENTRY 🎯";
    quality = "🔥 STRONG";
  } 
  else if (trend !== "RANGE" && bos && (sweep || fvg)) {
    signal = "ENTRY ⚡";
    quality = "⚡ MEDIUM";
  } 
  else {
    signal = "SCALP ⚠";
    quality = "⚠ SCALP (RANGE)";
  }

  // ===============================
  // 📊 ENTRY / SL / TP
  // ===============================
  let entry = null;
  let sl = null;
  let tp = null;

  if (direction) {
    entry = c3.close;

    if (direction === "BUY") {
      sl = swingLow || Math.min(c1.low, c2.low, c3.low);
      let risk = entry - sl;
      tp = entry + (risk * 2);
    }

    if (direction === "SELL") {
      sl = swingHigh || Math.max(c1.high, c2.high, c3.high);
      let risk = sl - entry;
      tp = entry - (risk * 2);
    }
  }

  // ===============================
  // ⏱ ANTI-SPAM
  // ===============================
  const now = Date.now();
  if (lastSignalTime[symbol] && now - lastSignalTime[symbol] < 60000) {
    return;
  }

  // ===============================
  // 📢 OUTPUT
  // ===============================
  if (direction) {
    lastSignalTime[symbol] = now;

    console.log(`
==============================
📊 ${symbol}
${signal}
Quality: ${quality}

📈 Trend: ${trend}
📍 Direction: ${direction}

🎯 Entry: ${entry}
🛑 Stop Loss: ${sl}
💰 Take Profit: ${tp}

✔ BOS: ${bos ? "✅" : "❌"}
✔ Strong BOS: ${(strongBosUp || strongBosDown) ? "✅" : "❌"}
✔ Sweep: ${sweep ? "✅" : "❌"}
✔ FVG: ${fvg ? "✅" : "❌"}

📌 Resistance: ${swingHigh || "N/A"}
📌 Support: ${swingLow || "N/A"}
==============================
    `);

    playSound();
  }
}

// ===============================
// 🚀 START
// ===============================
connect();
