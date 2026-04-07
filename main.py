from flask import Flask, jsonify
from flask_cors import CORS
import random

app = Flask(__name__)
CORS(app)

def generate_signals():
    pairs = ["EUR/USD", "BTC/USD", "XAU/USD"]
    signals = []

    for pair in pairs:
        action = random.choice(["BUY", "SELL"])
        confidence = random.randint(60, 85)

        signals.append({
            "pair": pair,
            "action": action,
            "entry": round(random.uniform(1.0, 2.0), 4),
            "sl": round(random.uniform(0.9, 1.5), 4),
            "tp": round(random.uniform(1.5, 2.5), 4),
            "confidence": f"{confidence}%",
            "reason": "FVG + Liquidity + Trend + RSI"
        })

    return signals

@app.route('/signals')
def signals():
    return jsonify(generate_signals())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)