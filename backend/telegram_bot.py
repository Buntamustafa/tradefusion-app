import requests

BOT_TOKEN = "8672537389:AAH5e2SaNpwdOzfeOPKexT_IlZNr2k5s0BQ"
CHAT_ID = "7824834312"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass
