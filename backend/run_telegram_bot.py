import os
import sys
import time
import json
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

def call_telegram_api(method: str, params: dict = None) -> dict:
    if not params:
        params = {}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    
    # If params contains reply_markup as dict, convert to JSON string
    if "reply_markup" in params and isinstance(params["reply_markup"], dict):
        params["reply_markup"] = json.dumps(params["reply_markup"])
        
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[Telegram API Error] {e}")
        return {"ok": False, "error": str(e)}

def send_message(chat_id: int, text: str, reply_markup: dict = None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        params["reply_markup"] = reply_markup
    return call_telegram_api("sendMessage", params)

def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("your_"):
        print("[!] TELEGRAM_BOT_TOKEN not configured in .env")
        return

    print("=" * 60)
    print("      ORDERBOT LIVE TELEGRAM BOT + MINI-APP RUNNER       ")
    print("=" * 60)
    print(f"[+] Bot Token Loaded: {TELEGRAM_BOT_TOKEN[:10]}...")
    print("[+] Listening for chat events & Mini-App submissions...\n")

    agent = OrderBotAgent()
    offset = 0
    pending_chats = {}

    while True:
        try:
            updates = call_telegram_api("getUpdates", {"offset": offset, "timeout": 5})
            if updates.get("ok") and updates.get("result"):
                for update in updates["result"]:
                    offset = update["update_id"] + 1
                    message = update.get("message")
                    if not message:
                        continue

                    chat_id = message["chat"]["id"]
                    first_name = message["from"].get("first_name", "Customer")

                    # Handle Telegram WebApp submitted data (Cart Data)
                    if "web_app_data" in message:
                        raw_data = message["web_app_data"]["data"]
                        order_info = json.loads(raw_data)
                        
                        summary_text = (
                            f"✅ <b>Order Confirmed #{order_info.get('voucher_no')}</b>\n\n"
                            f"Total Amount: <b>₹{order_info.get('total_amount'):,.2f}</b>\n"
                            f"Status: <i>Placed & Sent to Wholesaler</i>\n\n"
                            f"Thank you, <b>{first_name}</b>! The business owner has been notified."
                        )
                        send_message(chat_id, summary_text)
                        continue

                    user_text = message.get("text", "").strip()
                    if not user_text:
                        continue

                    print(f"[Incoming Msg from {first_name} ({chat_id})]: {user_text}")

                    # Trigger Mini App Order Link if user asks to order / buy / cart
                    if any(w in user_text.lower() for w in ["order", "cart", "buy", "miniapp", "reorder"]):
                        # Lookup or create customer
                        cust, _ = Customer.objects.get_or_create(
                            name=first_name,
                            defaults={"phone": f"+91-{chat_id}", "state_code": "08"}
                        )

                        mini_app_url = f"http://127.0.0.1:8000/miniapp/?customer_id={cust.id}"

                        keyboard = {
                            "inline_keyboard": [[
                                {
                                    "text": "🛒 Open Wholesale Cart",
                                    "web_app": {"url": mini_app_url}
                                }
                            ]]
                        }

                        send_message(
                            chat_id,
                            f"Hello <b>{first_name}</b>! Tap below to open your personalized wholesale cart (pre-filled with your usual reorders):",
                            reply_markup=keyboard
                        )
                        continue

                    # Handle phone follow-up for pending registration
                    if chat_id in pending_chats and pending_chats[chat_id].get("missing_field") == "phone":
                        account_name = pending_chats[chat_id].get("account")
                        response = agent.process_command(
                            user_intent="Create customer",
                            module_name="customers",
                            provided_data={"account": account_name, "phone": user_text, "state_code": "19"}
                        )
                        del pending_chats[chat_id]
                    else:
                        if "add" in user_text.lower() or "create" in user_text.lower():
                            parts = user_text.split("customer")
                            name = parts[-1].replace("from Kolkata", "").replace("named", "").strip() if len(parts) > 1 else user_text
                            response = agent.process_command(user_text, module_name="customers", provided_data={"account": name})
                        elif "delete" in user_text.lower() or "remove" in user_text.lower():
                            parts = user_text.split("customer")
                            name = parts[-1].strip() if len(parts) > 1 else user_text
                            response = agent.process_command(user_text, module_name="customers", provided_data={"account": name})
                        else:
                            response = agent.process_command(user_text, module_name="customers")

                    reply = f"<b>OrderBot</b>: {response.get('message')}"

                    if response.get("action") == "prompt_user":
                        pending_chats[chat_id] = {
                            "missing_field": response.get("missing_field"),
                            "account": response.get("message").split("'")[1] if "'" in response.get("message") else "Customer"
                        }

                    if response.get("result") and response["result"].get("type") == "select":
                        data = response["result"].get("data", [])
                        if data:
                            reply += "\n\n<b>Active Customer Records:</b>"
                            for row in data:
                                reply += f"\n• <b>{row.get('name')}</b> ({row.get('phone')}) - ID: {row.get('id')}"
                        else:
                            reply += "\n\n<i>[No active records found]</i>"

                    send_message(chat_id, reply)

            time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping Telegram Bot Listener.")
            break
        except Exception as e:
            print(f"[Error] {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
