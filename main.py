import os
import json
import threading
import websocket
from flask import Flask, jsonify

app = Flask(__name__)

APP_ID = os.getenv("APP_ID")
API_TOKEN = os.getenv("DERIV_API_TOKEN")

connected = False
authorized = False
last_error = None
logs = []
signals = []

def log(msg):
    print(msg)
    logs.append(msg)
    if len(logs) > 50:
        logs.pop(0)

def connect_deriv():
    global connected, authorized, last_error

    if not APP_ID:
        log("❌ APP_ID is missing")
        return

    if not API_TOKEN:
        log("❌ API_TOKEN is missing")
        return

    ws_url = f"wss://ws.derivws.com/websockets/v3?app_id={APP_ID}"
    log(f"🔌 Connecting with APP_ID: {APP_ID}")

    def on_open(ws):
        global connected
        connected = True
        log("✅ WebSocket connection opened")

        ws.send(json.dumps({
            "authorize": API_TOKEN
        }))
        log("🔑 Sending authorization...")

    def on_message(ws, message):
        global authorized, last_error

        data = json.loads(message)

        # DEBUG: log raw message
        log(f"📩 {data}")

        if "error" in data:
            last_error = data["error"]["message"]
            log(f"❌ API Error: {last_error}")

        if "authorize" in data:
            authorized = True
            log("✅ Authorized successfully")

            ws.send(json.dumps({
                "ticks": "R_100"
            }))
            log("📡 Subscribed to ticks")

        elif "tick" in data:
            tick = data["tick"]["quote"]
            signals.append({"price": tick})

    def on_error(ws, error):
        global last_error
        last_error = str(error)
        log(f"❌ WebSocket Error: {error}")

    def on_close(ws, close_status_code, close_msg):
        global connected, authorized
        connected = False
        authorized = False
        log("🔌 Connection closed")

    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever()

# Run in background
threading.Thread(target=connect_deriv).start()


# ROUTES

@app.route("/")
def home():
    return jsonify({"message": "Bot running..."})

@app.route("/status")
def status():
    return jsonify({
        "connected": connected,
        "authorized": authorized,
        "signals_count": len(signals),
        "last_error": last_error,
        "app_id_used": APP_ID
    })

@app.route("/logs")
def get_logs():
    return jsonify(logs)

@app.route("/check")
def check():
    return jsonify({
        "APP_ID_exists": bool(APP_ID),
        "TOKEN_exists": bool(API_TOKEN),
        "APP_ID_value": APP_ID
    })


if __name__ == "__main__":
    app.run()
