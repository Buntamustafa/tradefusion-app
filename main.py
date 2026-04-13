from flask import Flask, jsonify
import websocket
import json
import threading
import time
import os

app = Flask(__name__)

signals = []
connected = False

# Get token from Render environment
DERIV_TOKEN = os.getenv("DERIV_TOKEN")


def connect_deriv():
    global connected, signals

    def on_message(ws, message):
        global signals
        data = json.loads(message)

        if "tick" in data:
            tick = data["tick"]

            signal = {
                "symbol": tick["symbol"],
                "price": tick["quote"],
                "time": tick["epoch"]
            }

            signals.append(signal)

            # Keep last 20 signals only
            signals = signals[-20:]

    def on_open(ws):
        global connected
        print("Connected to Deriv")

        ws.send(json.dumps({
            "authorize": DERIV_TOKEN
        }))

        ws.send(json.dumps({
            "ticks": "R_100"
        }))

        connected = True

    def on_close(ws, close_status_code, close_msg):
        global connected
        print("Disconnected from Deriv")
        connected = False

    def on_error(ws, error):
        global connected
        print("Error:", error)
        connected = False

    ws = websocket.WebSocketApp(
        "wss://ws.derivws.com/websockets/v3",
        on_open=on_open,
        on_message=on_message,
        on_close=on_close,
        on_error=on_error
    )

    ws.run_forever()


# 🔁 Bulletproof background runner
def start_ws():
    while True:
        try:
            connect_deriv()
        except Exception as e:
            print("Reconnect error:", e)
            time.sleep(5)


# Start WebSocket thread
threading.Thread(target=start_ws, daemon=True).start()


@app.route("/")
def home():
    return jsonify({"message": "⏳ Waiting for signals..."})


@app.route("/signals")
def get_signals():
    return jsonify(signals)


@app.route("/status")
def status():
    return jsonify({
        "connected": connected,
        "signals_count": len(signals)
    })


@app.route("/check-token")
def check_token():
    return jsonify({
        "token": DERIV_TOKEN
    })
