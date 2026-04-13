import os
import json
import websocket
import threading
from flask import Flask, jsonify

app = Flask(__name__)

API_TOKEN = os.getenv("API_TOKEN")
APP_ID = os.getenv("APP_ID")

connected = False
signals = []

def on_open(ws):
    global connected
    print("Connected to Deriv")

    auth_data = {
        "authorize": API_TOKEN
    }
    ws.send(json.dumps(auth_data))

def on_message(ws, message):
    global connected, signals
    data = json.loads(message)

    if "authorize" in data:
        connected = True
        print("Authorized successfully")

        # Subscribe to ticks
        ws.send(json.dumps({
            "ticks": "R_100"
        }))

    if "tick" in data:
        price = data["tick"]["quote"]

        signal = {
            "symbol": "R_100",
            "price": price
        }

        signals.append(signal)

def on_error(ws, error):
    global connected
    connected = False
    print("Error:", error)

def on_close(ws, close_status_code, close_msg):
    global connected
    connected = False
    print("Disconnected")

def start_ws():
    url = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"

    ws = websocket.WebSocketApp(
        url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever()

# Start WebSocket in background
threading.Thread(target=start_ws).start()

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
    return jsonify(signals[-10:])

@app.route("/check-token")
def check_token():
    return jsonify({
        "token": API_TOKEN,
        "app_id": APP_ID
    })

if __name__ == "__main__":
    app.run()
