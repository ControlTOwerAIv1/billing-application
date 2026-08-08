import os
import sys
import time
import json
import socket
import urllib.request
import urllib.parse
import django
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from backend.config import TELEGRAM_BOT_TOKEN
from backend.agent.agent import OrderBotAgent
from apps.core.models import Customer, Order

def call_telegram_api(method: str, params: dict = None, max_retries: int = 3) -> dict:
    if not params:
        params = {}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    
    if "reply_markup" in params and isinstance(params["reply_markup"], dict):
        params["reply_markup"] = json.dumps(params["reply_markup"])
        
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    data = urllib.parse.urlencode(params).encode("utf-8")

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt == max_retries:
                print(f"[Telegram Network Exception] {method} (Attempt {attempt}/{max_retries}): {e}")
                return {"ok": False, "error": str(e)}
            time.sleep(1)

def send_message(chat_id: int, text: str, reply_markup: dict = None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        params["reply_markup"] = reply_markup
    res = call_telegram_api("sendMessage", params)
    if res and res.get("ok") and res.get("result", {}).get("message_id"):
        track_message_id(chat_id, res["result"]["message_id"])
    return res

def delete_message(chat_id: int, message_id: int) -> dict:
    return call_telegram_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id})

def track_message_id(chat_id: int, message_id: int):
    tracked_ids.setdefault(chat_id, []).append(message_id)

tracked_ids = {}

def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("your_"):
        print("[!] TELEGRAM_BOT_TOKEN not configured in .env")
        return

    print("=" * 60)
    print("      ORDERBOT LIVE TELEGRAM BOT + MINI-APP RUNNER       ")
    print("=" * 60)
    print(f"[+] Bot Token Loaded: {TELEGRAM_BOT_TOKEN[:10]}...")
    print("[+] Multi-turn Conversation Memory: ACTIVE\n")

    agent = OrderBotAgent()
    offset = 0

    while True:
        try:
            updates = call_telegram_api("getUpdates", {"offset": offset, "timeout": 0})
            if updates and updates.get("ok") and updates.get("result"):
                for update in updates["result"]:
                    offset = update["update_id"] + 1
                    message = update.get("message")
                    if not message:
                        continue

                    chat_id = message["chat"]["id"]
                    first_name = message["from"].get("first_name", "Customer")
                    track_message_id(chat_id, message["message_id"])

                    # Handle WebApp submitted cart data
                    if "web_app_data" in message:
                        raw_data = message["web_app_data"]["data"]
                        order_info = json.loads(raw_data)
                        
                        summary_text = (
                            f"🎉 <b>Your Order Has Been Successfully Created!</b>\n\n"
                            f"📦 <b>Voucher No:</b> #{order_info.get('voucher_no')}\n"
                            f"💰 <b>Total Amount:</b> ₹{order_info.get('total_amount'):,.2f}\n"
                            f"🚚 <b>Status:</b> Placed & Sent to Wholesaler\n\n"
                            f"Thank you, <b>{first_name}</b>! The business owner has been notified."
                        )
                        send_message(chat_id, summary_text)
                        continue

                    user_text = message.get("text", "").strip()

                    if user_text.lower() == "/clear":
                        deleted = 0
                        for mid in tracked_ids.pop(chat_id, []):
                            if delete_message(chat_id, mid).get("ok"):
                                deleted += 1
                        agent.clear_memory(str(chat_id))
                        print(f"[Clear] Deleted {deleted} messages + memory for chat {chat_id}")
                        send_message(chat_id, "🧹 Chat cleared. Memory reset — what would you like to do?")
                        continue

                    if not user_text:
                        continue

                    print(f"[Incoming Msg from {first_name} ({chat_id})]: {user_text}")

                    # Trigger Mini App Order Link if user asks to order / buy / cart
                    if any(w in user_text.lower() for w in ["order", "cart", "buy", "miniapp", "reorder"]):
                        cust, _ = Customer.objects.get_or_create(
                            name=first_name,
                            defaults={"phone": f"+91-{chat_id}", "state_code": "08"}
                        )

                        mini_app_url = f"http://127.0.0.1:8000/miniapp/?customer_id={cust.id}&chat_id={chat_id}"

                        keyboard = {
                            "inline_keyboard": [[
                                {
                                    "text": "🛒 Open Wholesale Cart (Browser)",
                                    "url": mini_app_url
                                }
                            ]]
                        }

                        res = send_message(
                            chat_id,
                            f"Hello <b>{first_name}</b>! Tap below to open your personalized wholesale cart (pre-filled with your usual reorders):",
                            reply_markup=keyboard
                        )
                        if not res or not res.get("ok"):
                            send_message(
                                chat_id,
                                f"Hello <b>{first_name}</b>! Open your wholesale cart here: {mini_app_url}"
                            )
                        continue

                    # Process via LangGraph AI agent with thread memory
                    response_dict = agent.process_message(user_text, thread_id=str(chat_id))
                    reply_text = response_dict.get("response") or response_dict.get("message") or "Done."

                    formatted_reply = f"<b>OrderBot</b>:\n{reply_text}"
                    send_message(chat_id, formatted_reply)

            time.sleep(1.5)
        except KeyboardInterrupt:
            print("\nStopping Telegram Bot Listener.")
            break
        except Exception as e:
            print(f"[Error] {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
