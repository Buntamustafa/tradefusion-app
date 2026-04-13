from flask import Flask, jsonify
import websocket
import json
import threading
import time
import os

app = Flask(__name__)

# ENV VARIABLES
API_TOKEN = os.getenv("API_TOKEN")
APP_ID = os.getenv("APP_ID")

# GLOBAL STATE
connected = False
signals = []

# =========================
# CONNECT TO DERIV
# =========================
def connect_deriv():
    global connected, signals

    while True:
        try:
            print("🔄 Connecting to Deriv...")

            ws = websocket.WebSocket()
            ws.connect(f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}")

            # Authorize
            ws.send(json.dumps({
                "authorize": API_TOKEN
            }))

            response = json.loads(ws.recv())

            if "error" in response:
                print("❌ Auth failed:", response)
                connected = False
                time.sleep(5)
                continue

            print("✅ Connected to Deriv")
            connected = True

            # Subscribe to ticks (example: Volatility 75)
            ws.send(json.dumps({
                "ticks": "R_75"
            }))

            while True:
                data = json.loads(ws.recv())

                if "tick" in data:
                    price = data["tick"]["quote"]

                    # SIMPLE SIGNAL LOGIC (we will upgrade later)
                    signal = {
                        "symbol": "R_75",
                        "price": price,
                        "direction": "BUY" if int(price) % 2 == 0 else "SELL"
                    }

                    signals.append(signal)

                    # Keep only last 10 signals
                    signals = signals[-10:]

                    print("📊 Signal:", signal)

        except Exception as e:
            print("❌ Connection error:", e)
            connected = False
            time.sleep(5)

# =========================
# START BOT THREAD
# =========================
def start_bot():
    thread = threading.Thread(target=connect_deriv)
    thread.daemon = True
    thread.start()

start_bot()

# =========================
# ROUTES
# =========================

@app.route("/")
def home():
    return jsonify({"message": "⏳ Waiting for signals..."})

@app.route("/status")
def status():
    return jsonify({
        "connected": connected,
        "signals_count": len(signals)
    })

@app.route("/signals")
def get_signals():
    if not signals:
        return jsonify([{"message": "⏳ Waiting for signals..."}])
    return jsonify(signals)

@app.route("/check-token")
def check_token():
    return jsonify({
        "token_set": API_TOKEN is not None,
        "app_id_set": APP_ID is not None
    })

# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
