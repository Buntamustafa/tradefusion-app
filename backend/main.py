// ===============================
// 🔐 DERIV CONNECTION
// ===============================
const API_TOKEN = "pat_81f005f46e8ace4472e4e8c0e90e4a27422999b3dc1088cbf265b0b546da20a9";
const WS_URL = "wss://ws.derivws.com/websockets/v3?app_id=1089";

let ws;

// ===============================
// 📊 PAIRS (YOU REQUESTED)
// ===============================
const symbols = [
  "frxEURUSD",  // EUR/USD
  "frxXAUUSD",  // GOLD
  "frxUSOIL",   // OIL
  "cryBTCUSD",  // BTC
  "cryETHUSD"   // ETH
];

// ===============================
// 🔊 SOUND ALERT
// ===============================
function playSound() {
  const audio = new Audio("https://www.soundjay.com/buttons/sounds/beep-01a.mp3");
  audio.play();
}

// ===============================
// 🔌 CONNECT TO DERIV
// ===============================
function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log("✅ Connected to Deriv");
    authorize();
  };

  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);

    if (data.msg_type === "authorize") {
      console.log("🔐 Authorized");
      startFetching();
    }

    if (data.msg_type === "candles") {
      analyzeMarket(data);
    }
  };

  ws.onerror = (err) => console.log("❌ Error:", err);
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
// 📡 FETCH DATA (1m candles)
// ===============================
function startFetching() {
  symbols.forEach(symbol => {
    ws.send(JSON.stringify({
      ticks_history: symbol,
      style: "candles",
      granularity: 60,   // 1 minute
      count: 100
    }));
  });
}

// ===============================
// 🧠 MARKET ANALYSIS CORE
// ===============================
function analyzeMarket(data) {
  const candles = data.candles;
  const symbol = data.echo_req.ticks_history;

  if (!candles || candles.length < 20) return;

  const last = candles[candles.length - 1];
  const prev = candles[candles.length - 2];

  const high = last.high;
  const low = last.low;
  const close = last.close;

  // ===============================
  // 🧩 BOS (Break of Structure)
  // ===============================
  let bos = false;
  if (last.high > prev.high || last.low < prev.low) {
    bos = true;
  }

  // ===============================
  // 💧 LIQUIDITY SWEEP
  // ===============================
  let sweep = false;
  if (last.high > prev.high && close < prev.high) {
    sweep = true; // fake breakout up
  }
  if (last.low < prev.low && close > prev.low) {
    sweep = true; // fake breakout down
  }

  // ===============================
  // ⚡ MINI FVG (Fair Value Gap)
  // ===============================
  let fvg = false;
  const c1 = candles[candles.length - 3];
  const c2 = candles[candles.length - 2];
  const c3 = candles[candles.length - 1];

  if (c1.high < c3.low || c1.low > c3.high) {
    fvg = true;
  }

  // ===============================
  // 🎯 SNIPER ENTRY LOGIC
  // ===============================
  let signal = null;
  let quality = "⚠ Scalp";

  if (bos && sweep && fvg) {
    signal = "SNIPER ENTRY 🎯";
    quality = "🔥 STRONG";
  } 
  else if (bos && (sweep || fvg)) {
    signal = "ENTRY ⚡";
    quality = "⚡ MEDIUM";
  } 
  else if (bos) {
    signal = "QUICK SCALP ⚠";
    quality = "⚠ SCALP";
  }

  // ===============================
  // 📢 OUTPUT SIGNAL
  // ===============================
  if (signal) {
    console.log(`
==============================
📊 ${symbol}
${signal}
Quality: ${quality}

✔ BOS: ${bos ? "✅" : "❌"}
✔ Sweep: ${sweep ? "✅" : "❌"}
✔ Mini FVG: ${fvg ? "✅" : "❌"}
==============================
    `);

    playSound();
  }
}

// ===============================
// 🚀 START BOT
// ===============================
connect();
