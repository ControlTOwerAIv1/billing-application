import os
import sys
import time
import json
import urllib.request
import urllib.parse
import django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from backend.config import TELEGRAM_BOT_TOKEN
from backend.agent.agent import OrderBotAgent

def call_telegram_api(method: str, params: dict = None) -> dict:
    if not params:
        params = {}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[Telegram API Error] {e}")
        return {"ok": False, "error": str(e)}

def send_message(chat_id: int, text: str):
    return call_telegram_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    })

def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("your_"):
        print("[!] TELEGRAM_BOT_TOKEN not configured in .env")
        return

    print("=" * 65)
    print("   ORDERBOT LIVE TELEGRAM BOT LISTENER (LITELLM ENGINE) RUNNING   ")
    print("=" * 65)
    print(f"[+] Bot Token Loaded: {TELEGRAM_BOT_TOKEN[:10]}...")
    print("[+] Polling for incoming messages on Telegram...\n")

    agent = OrderBotAgent()
    offset = 0
    chat_histories = {}  # chat_id -> list of message dicts

    while True:
        try:
            updates = call_telegram_api("getUpdates", {"offset": offset, "timeout": 5})
            if updates.get("ok") and updates.get("result"):
                for update in updates["result"]:
                    offset = update["update_id"] + 1
                    message = update.get("message")
                    if not message or "text" not in message:
                        continue

                    chat_id = message["chat"]["id"]
                    user_text = message["text"].strip()
                    first_name = message["from"].get("first_name", "User")

                    print(f"[Incoming Telegram Msg from {first_name} ({chat_id})]: {user_text}")

                    history = chat_histories.get(chat_id, [])
                    result = agent.process_message(user_text, chat_history=history)

                    if result.get("status") == "success":
                        reply_text = result.get("response", "Command processed.")
                        chat_histories[chat_id] = result.get("updated_history", history)
                    else:
                        reply_text = f"❌ <b>Error</b>: {result.get('message')}"

                    send_message(chat_id, reply_text)

            time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping Telegram Bot Listener.")
            break
        except Exception as e:
            print(f"[Error] {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
