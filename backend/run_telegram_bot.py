import os
import sys
import time
import json
import uuid
import mimetypes
import urllib.request
import urllib.parse
from pathlib import Path
import django

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from django.conf import settings
from backend.config import TELEGRAM_BOT_TOKEN
from backend.agent.agent import OrderBotAgent
from backend.formatter import markdown_to_telegram_html
from apps.core.models import Customer, Order, Product, Transport
from backend.agent.tools import resolve_single_customer

def build_multipart_body(fields: dict, files: dict):
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()
    
    for key, value in fields.items():
        if value is not None:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")
            
    for key, (filename, file_bytes) in files.items():
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode("utf-8"))
        body.extend(f"Content-Type: {mime}\r\n\r\n".encode("utf-8"))
        body.extend(file_bytes)
        body.extend(b"\r\n")
        
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    content_type = f"multipart/form-data; boundary={boundary}"
    return bytes(body), content_type

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

def call_telegram_multipart(method: str, fields: dict, files: dict, max_retries: int = 3) -> dict:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data, content_type = build_multipart_body(fields, files)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": content_type
    }

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt == max_retries:
                print(f"[Telegram Multipart Exception] {method} (Attempt {attempt}/{max_retries}): {e}")
                return {"ok": False, "error": str(e)}
            time.sleep(1)

def download_telegram_photo(file_id: str) -> tuple[str, str] | tuple[None, None]:
    """Downloads a photo from Telegram servers and saves it into media/products/"""
    file_info = call_telegram_api("getFile", {"file_id": file_id})
    if not file_info or not file_info.get("ok") or not file_info.get("result", {}).get("file_path"):
        return None, None
    
    file_path = file_info["result"]["file_path"]
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    
    ext = Path(file_path).suffix or ".jpg"
    filename = f"prod_{uuid.uuid4().hex[:10]}{ext}"
    
    products_dir = Path(settings.MEDIA_ROOT) / "products"
    products_dir.mkdir(parents=True, exist_ok=True)
    
    local_file_path = products_dir / filename
    
    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            local_file_path.write_bytes(resp.read())
        
        media_url = f"/media/products/{filename}"
        return str(local_file_path), media_url
    except Exception as e:
        print(f"[Photo Download Error]: {e}")
        return None, None

def resolve_photo_path(photo_url_or_path: str) -> Path | None:
    """Resolves a photo URL or relative path to a local Path object if existing."""
    if not photo_url_or_path:
        return None
    raw = photo_url_or_path.strip()
    if raw.startswith("/media/") or raw.startswith("media/"):
        rel = raw.lstrip("/")
        p = Path(settings.BASE_DIR) / rel
        if p.exists():
            return p
    p_direct = Path(raw)
    if p_direct.exists():
        return p_direct
    return None

def send_photo(chat_id: int, photo_source: str, caption: str = None, reply_markup: dict = None) -> dict:
    """Sends a photo to chat. Uploads local file directly via multipart if local, or passes URL."""
    local_path = resolve_photo_path(photo_source)
    
    fields = {"chat_id": chat_id}
    if caption:
        fields["caption"] = caption
        fields["parse_mode"] = "HTML"
    if reply_markup:
        fields["reply_markup"] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup

    if local_path and local_path.is_file():
        files = {"photo": (local_path.name, local_path.read_bytes())}
        res = call_telegram_multipart("sendPhoto", fields, files)
    else:
        fields["photo"] = photo_source
        res = call_telegram_api("sendPhoto", fields)
        
    if res and res.get("ok") and res.get("result", {}).get("message_id"):
        track_message_id(chat_id, res["result"]["message_id"])
    return res

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
user_pending_photos = {}
pending_order_customers = {}  # chat_id -> True if waiting for customer selection
pending_transport_for_customer = {}  # chat_id -> customer_id waiting for transport input

def dispatch_product_photos_if_any(chat_id: int, result_dict: dict, user_text: str = "", reply_text: str = ""):
    """Checks if any products were retrieved or created, and dispatches their photos to Telegram."""
    tool_calls = result_dict.get("tool_calls", [])
    products_to_show = []

    # 1. Match from tool calls
    for tc in tool_calls:
        tool_name = str(tc.get("tool", ""))
        args = tc.get("args", {}) or {}
        if "create_product" in tool_name:
            sku = args.get("sku", "")
            prod = Product.objects.filter(sku__iexact=sku).first()
            if prod and prod.image_url and prod not in products_to_show:
                products_to_show.append(prod)
        elif "search_products" in tool_name:
            q = args.get("query", "")
            cat = args.get("category", "")
            qs = Product.objects.filter(is_active=True)
            if q:
                qs = qs.filter(sku__icontains=q) | qs.filter(name__icontains=q)
            if cat:
                qs = qs.filter(category__iexact=cat)
            for p in qs[:3]:
                if p.image_url and p not in products_to_show:
                    products_to_show.append(p)

    # 2. Text scanning fallback across user message and AI reply
    combined_text = f"{user_text} {reply_text}".lower()
    for prod in Product.objects.filter(is_active=True).exclude(image_url="").exclude(image_url__isnull=True):
        if prod.sku.lower() in combined_text or (len(prod.name) > 3 and prod.name.lower() in combined_text):
            if prod not in products_to_show:
                products_to_show.append(prod)

    for prod in products_to_show:
        urls = [u.strip() for u in prod.image_url.split(",") if u.strip()]
        for u in urls:
            caption = f"📸 <b>{prod.name}</b> (SKU: <code>{prod.sku}</code>)\n💰 ₹{float(prod.loose_price):.2f} / pc | Carton: ₹{float(prod.full_carton_price):.2f}"
def send_customer_catalogue_link(chat_id: int, customer: Customer, first_name: str = ""):
    """Generates and dispatches the personalized Mini App catalogue link for the selected customer."""
    mini_app_url = f"http://127.0.0.1:8000/miniapp/?customer_id={customer.id}&chat_id={chat_id}"
    keyboard = {
        "inline_keyboard": [[
            {
                "text": f"🛒 Open Catalogue for {customer.name} (Browser)",
                "url": mini_app_url
            }
        ]]
    }
    loc_str = f"{customer.city}, State {customer.state_code}" if customer.city else f"State {customer.state_code}"
    bal_str = f"₹{float(customer.balance_amount):,.2f}"

    msg_text = (
        f"✅ <b>Order for: {customer.name}</b>\n"
        f"📍 <b>Location:</b> {loc_str}\n"
        f"💰 <b>Current Balance:</b> {bal_str}\n\n"
        f"Tap below to open the wholesale catalogue to select products and submit your order:"
    )
    res = send_message(chat_id, msg_text, reply_markup=keyboard)
    if not res or not res.get("ok"):
        send_message(chat_id, f"{msg_text}\n\nOpen catalogue: {mini_app_url}")

def prompt_for_order_customer(chat_id: int, first_name: str):
    """Asks user to clarify which customer the order is being created for, providing quick inline buttons."""
    active_customers = Customer.objects.filter(soft_deleted=False).order_by('-created_at')[:5]
    keyboard_buttons = []

    for c in active_customers:
        loc = f" ({c.city})" if c.city else f" ({c.state_code})"
        keyboard_buttons.append([{
            "text": f"👤 {c.name}{loc}",
            "callback_data": f"order_cust_{c.id}"
        }])

    keyboard_buttons.append([{
        "text": f"🙋 Myself ({first_name})",
        "callback_data": "order_cust_self"
    }])
    keyboard_buttons.append([{
        "text": "❌ Cancel",
        "callback_data": "order_cust_cancel"
    }])

    prompt = (
        f"👤 <b>Customer Clarification for New Order</b>\n\n"
        f"Who is this order for?\n"
        f"• Tap one of the customer buttons below, OR\n"
        f"• Reply with the customer's <b>Name</b>, <b>Business Name</b>, or <b>Phone Number</b>.\n\n"
        f"<i>(You can also type 'myself' to place the order for {first_name})</i>"
    )

    send_message(chat_id, prompt, reply_markup={"inline_keyboard": keyboard_buttons})

def prompt_for_customer_transport(chat_id: int, customer: Customer):
    """Prompts user to select or add a transport carrier for the newly created customer with inline buttons."""
    active_transports = Transport.objects.filter(is_active=True, soft_deleted=False).order_by("name")[:8]
    keyboard_buttons = []

    for t in active_transports:
        phone_hint = f" ({t.phone})" if t.phone else ""
        keyboard_buttons.append([{
            "text": f"🚚 {t.name}{phone_hint}",
            "callback_data": f"set_cust_trans_{customer.id}_{t.id}"
        }])

    keyboard_buttons.append([{
        "text": "➕ Add New Transport Carrier",
        "callback_data": f"new_trans_for_cust_{customer.id}"
    }])
    keyboard_buttons.append([{
        "text": "⏩ Skip / Self Transport",
        "callback_data": f"skip_cust_trans_{customer.id}"
    }])

    prompt = (
        f"🚚 <b>Transport Carrier Selection for {customer.name}</b>\n\n"
        f"Which transport carrier should orders for <b>{customer.name}</b> travel through?\n"
        f"• Tap a carrier button below\n"
        f"• Tap <b>➕ Add New Transport Carrier</b> to register a new transport\n"
        f"• Or tap <b>⏩ Skip</b> for Direct / Self Transport"
    )

    send_message(chat_id, prompt, reply_markup={"inline_keyboard": keyboard_buttons})

def is_new_order_intent(text: str) -> bool:
    """Detects whether the user's message indicates an intent to create/add an order or open the catalogue."""
    t = text.lower().strip()
    if any(q in t for q in ["list order", "show order", "track order", "status of order", "order status", "order history", "edit order", "cancel order"]):
        return False
    new_order_keywords = [
        "add order", "add an order", "create order", "create an order",
        "new order", "place order", "place an order", "make an order",
        "want to order", "i want to add an order", "i want to order",
        "open catalogue", "open catalog", "show catalogue", "show catalog",
        "open cart", "wholesale cart", "miniapp"
    ]
    if any(k in t for k in new_order_keywords):
        return True
    if t in ["order", "cart", "buy", "reorder", "catalogue", "catalog"]:
        return True
    if "order for" in t or "buy for" in t or "cart for" in t:
        return True
    return False

def main():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("your_"):
        print("[!] TELEGRAM_BOT_TOKEN not configured in .env")
        return

    print("=" * 60)
    print("      ORDERBOT LIVE TELEGRAM BOT + MINI-APP RUNNER       ")
    print("=" * 60)
    print(f"[+] Bot Token Loaded: {TELEGRAM_BOT_TOKEN[:10]}...")
    print("[+] Multi-turn Conversation Memory: ACTIVE")
    print("[+] Photo Upload & Catalog Media Storage: READY\n")

    agent = OrderBotAgent()
    offset = 0

    while True:
        try:
            updates = call_telegram_api("getUpdates", {"offset": offset, "timeout": 0})
            if updates and updates.get("ok") and updates.get("result"):
                for update in updates["result"]:
                    offset = update["update_id"] + 1

                    # 1. Handle Inline Keyboard Callback Queries (e.g. quick customer selection)
                    callback_query = update.get("callback_query")
                    if callback_query:
                        cq_id = callback_query.get("id")
                        cq_data = callback_query.get("data", "")
                        cq_message = callback_query.get("message", {})
                        chat_id = cq_message.get("chat", {}).get("id")
                        from_first_name = callback_query.get("from", {}).get("first_name", "Customer")

                        call_telegram_api("answerCallbackQuery", {"callback_query_id": cq_id})

                        if cq_data == "order_cust_cancel":
                            pending_order_customers.pop(chat_id, None)
                            send_message(chat_id, "❌ Order creation cancelled.")
                            continue
                        elif cq_data == "order_cust_self":
                            pending_order_customers.pop(chat_id, None)
                            cust, _ = Customer.objects.get_or_create(
                                name=from_first_name,
                                defaults={"phone": f"+91-{chat_id}", "state_code": "08"}
                            )
                            send_customer_catalogue_link(chat_id, cust, from_first_name)
                            continue
                        elif cq_data.startswith("order_cust_"):
                            cust_id_str = cq_data.replace("order_cust_", "")
                            if cust_id_str.isdigit():
                                cust = Customer.objects.filter(id=int(cust_id_str)).first()
                                if cust:
                                    pending_order_customers.pop(chat_id, None)
                                    send_customer_catalogue_link(chat_id, cust, from_first_name)
                                    continue
                        elif cq_data.startswith("set_cust_trans_"):
                            parts = cq_data.replace("set_cust_trans_", "").split("_")
                            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                                cust_id, trans_id = int(parts[0]), int(parts[1])
                                cust = Customer.objects.filter(id=cust_id).first()
                                trans = Transport.objects.filter(id=trans_id).first()
                                if cust and trans:
                                    cust.transport = trans
                                    cust.save(update_fields=["transport"])
                                    pending_transport_for_customer.pop(chat_id, None)
                                    send_message(chat_id, f"✅ Transport <b>{trans.name}</b> assigned to customer <b>{cust.name}</b>.")
                            continue
                        elif cq_data.startswith("skip_cust_trans_"):
                            cust_id_str = cq_data.replace("skip_cust_trans_", "")
                            pending_transport_for_customer.pop(chat_id, None)
                            if cust_id_str.isdigit():
                                cust = Customer.objects.filter(id=int(cust_id_str)).first()
                                name = cust.name if cust else "Customer"
                                send_message(chat_id, f"⏩ Transport selection skipped for <b>{name}</b> (default: Self / Direct).")
                            continue
                        elif cq_data.startswith("new_trans_for_cust_"):
                            cust_id_str = cq_data.replace("new_trans_for_cust_", "")
                            if cust_id_str.isdigit():
                                cust = Customer.objects.filter(id=int(cust_id_str)).first()
                                if cust:
                                    pending_transport_for_customer[chat_id] = cust.id
                                    send_message(
                                        chat_id,
                                        f"🚚 <b>Add New Transport for {cust.name}</b>\n\n"
                                        f"Please reply with the carrier details, e.g.:\n"
                                        f"<code>VRL Logistics, phone: 9876543210</code>\n"
                                        f"<i>(or type 'cancel' to abort)</i>"
                                    )
                            continue

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

                    # Handle Incoming Photos
                    has_photo = bool(message.get("photo"))
                    if has_photo:
                        best_photo = message["photo"][-1]
                        file_id = best_photo["file_id"]
                        local_path, media_url = download_telegram_photo(file_id)
                        
                        if media_url:
                            user_pending_photos.setdefault(chat_id, []).append(media_url)
                            print(f"[Photo Downloaded]: Saved to {local_path} ({media_url})")

                    caption = message.get("caption", "").strip()
                    user_text = message.get("text", "").strip()

                    # Handle /clear command
                    if user_text.lower() == "/clear":
                        deleted = 0
                        for mid in tracked_ids.pop(chat_id, []):
                            if delete_message(chat_id, mid).get("ok"):
                                deleted += 1
                        agent.clear_memory(str(chat_id))
                        user_pending_photos.pop(chat_id, None)
                        pending_order_customers.pop(chat_id, None)
                        pending_transport_for_customer.pop(chat_id, None)
                        print(f"[Clear] Deleted {deleted} messages + memory for chat {chat_id}")
                        send_message(chat_id, "🧹 Chat cleared. Memory reset — what would you like to do?")
                        continue

                    # If user only uploaded photo without caption
                    if has_photo and not caption:
                        num_photos = len(user_pending_photos.get(chat_id, []))
                        photo_label = f"{num_photos} photo(s)"
                        send_message(
                            chat_id,
                            f"📸 <b>{photo_label.capitalize()} received and saved to catalog media!</b>\n\n"
                            f"Now please tell me the product details:\n"
                            f"• <b>SKU</b> (e.g. <code>STAT-A4-500</code>)\n"
                            f"• <b>Product Name</b>\n"
                            f"• <b>Category</b> (e.g. Stationery, Plastics)\n"
                            f"• <b>Unit Price & Full Carton Price</b>\n"
                            f"• <b>Full Carton Quantity & GST Rate</b>\n\n"
                            f"I will automatically attach your uploaded photo(s) to this product!"
                        )
                        continue

                    prompt_text = caption if has_photo else user_text
                    if not prompt_text:
                        continue

                    # If user has previously uploaded pending photos, attach their URLs to the prompt
                    pending = user_pending_photos.pop(chat_id, [])
                    if pending:
                        photos_str = ", ".join(pending)
                        prompt_text = f"{prompt_text}\n[Attached Product Image URL(s): {photos_str}]"

                    print(f"[Incoming Msg from {first_name} ({chat_id})]: {prompt_text}")

                    # 1. Handle user response if chat is waiting for new transport details for a customer
                    if chat_id in pending_transport_for_customer:
                        cust_id = pending_transport_for_customer.pop(chat_id)
                        if prompt_text.lower() in ["cancel", "exit", "stop", "/cancel", "skip"]:
                            send_message(chat_id, "❌ Adding transport cancelled.")
                            continue

                        cust = Customer.objects.filter(id=cust_id).first()
                        import re
                        raw_t = prompt_text.strip()
                        phone_match = re.search(r'(?:\+?91[\-\s]?)?[6-9]\d{9}', raw_t)
                        phone = phone_match.group(0) if phone_match else ""
                        name_cand = re.sub(r'(?:\+?91[\-\s]?)?[6-9]\d{9}', '', raw_t)
                        name_cand = re.sub(r'phone\s*[:\-]?', '', name_cand, flags=re.IGNORECASE)
                        name_cand = name_cand.strip().strip(",.-")
                        trans_name = name_cand if name_cand else raw_t

                        new_trans = Transport.objects.create(
                            name=trans_name,
                            phone=phone
                        )
                        if cust:
                            cust.transport = new_trans
                            cust.save(update_fields=["transport"])
                            send_message(
                                chat_id,
                                f"✅ Transport carrier <b>{new_trans.name}</b> added successfully and linked to customer <b>{cust.name}</b>!"
                            )
                        else:
                            send_message(
                                chat_id,
                                f"✅ Transport carrier <b>{new_trans.name}</b> added successfully!"
                            )
                        continue

                    # 2. Quick command for listing transports
                    if prompt_text.lower() in ["/transports", "transports", "list transports", "show transports"]:
                        all_trans = Transport.objects.filter(soft_deleted=False, is_active=True).order_by("name")
                        if not all_trans.exists():
                            send_message(chat_id, "🚚 <b>No transport carriers registered yet.</b>\nType: <i>'add transport [name] phone [number]'</i> to add one.")
                        else:
                            t_lines = []
                            for idx, t in enumerate(all_trans, 1):
                                ph = f" | 📞 {t.phone}" if t.phone else ""
                                vn = f" | 🚛 {t.vehicle_number}" if t.vehicle_number else ""
                                cp = f" ({t.contact_person})" if t.contact_person else ""
                                t_lines.append(f"{idx}. <b>{t.name}</b>{cp}{ph}{vn}")
                            msg = "🚚 <b>Registered Transport Carriers:</b>\n\n" + "\n".join(t_lines) + "\n\n<i>Use /transports or ask me to add/assign transports anytime!</i>"
                            send_message(chat_id, msg)
                        continue

                    # 1. Handle user response if chat is waiting for customer clarification
                    if chat_id in pending_order_customers:
                        if prompt_text.lower() in ["cancel", "exit", "stop", "/cancel"]:
                            pending_order_customers.pop(chat_id, None)
                            send_message(chat_id, "❌ Order creation cancelled.")
                            continue

                        # Check if user meant themselves
                        if prompt_text.lower() in ["myself", "me", "for me", "for myself", first_name.lower()]:
                            pending_order_customers.pop(chat_id, None)
                            cust, _ = Customer.objects.get_or_create(
                                name=first_name,
                                defaults={"phone": f"+91-{chat_id}", "state_code": "08"}
                            )
                            send_customer_catalogue_link(chat_id, cust, first_name)
                            continue

                        # Attempt customer resolution
                        cust, err = resolve_single_customer(prompt_text)
                        if cust:
                            pending_order_customers.pop(chat_id, None)
                            send_customer_catalogue_link(chat_id, cust, first_name)
                            continue
                        elif err and err.get("status") == "disambiguation_required":
                            matches = err.get("matches", [])
                            buttons = [
                                [{"text": f"👤 {m['display']}", "callback_data": f"order_cust_{m['id']}"}]
                                for m in matches[:6]
                            ]
                            buttons.append([{"text": "❌ Cancel", "callback_data": "order_cust_cancel"}])
                            send_message(
                                chat_id,
                                f"Multiple customers found matching '<b>{prompt_text}</b>'. Please select the intended customer:",
                                reply_markup={"inline_keyboard": buttons}
                            )
                            continue
                        else:
                            # If prompt clearly looks like a general agent query/command, release pending state and pass to agent
                            lower_p = prompt_text.lower()
                            if any(lower_p.startswith(w) for w in ["what", "show", "list", "search", "how", "tell", "/"]):
                                pending_order_customers.pop(chat_id, None)
                            else:
                                active_customers = Customer.objects.filter(soft_deleted=False).order_by('-created_at')[:4]
                                buttons = [[{"text": f"👤 {c.name}", "callback_data": f"order_cust_{c.id}"}] for c in active_customers]
                                buttons.append([{"text": f"🙋 Myself ({first_name})", "callback_data": "order_cust_self"}])
                                buttons.append([{"text": "❌ Cancel", "callback_data": "order_cust_cancel"}])
                                send_message(
                                    chat_id,
                                    f"❌ Could not find customer matching '<b>{prompt_text}</b>'.\n\n"
                                    f"Please reply with a valid customer name, business name, or phone number (or tap below):",
                                    reply_markup={"inline_keyboard": buttons}
                                )
                                continue

                    # 2. Check for New Order / Open Catalogue intent
                    if is_new_order_intent(prompt_text):
                        lower_p = prompt_text.lower()
                        # Check if customer was directly specified (e.g. "add order for Raj Wholesalers")
                        if " for " in lower_p:
                            candidate = prompt_text.split(" for ", 1)[1].strip().rstrip(".!?")
                            if candidate.lower() in ["myself", "me", first_name.lower()]:
                                cust, _ = Customer.objects.get_or_create(
                                    name=first_name,
                                    defaults={"phone": f"+91-{chat_id}", "state_code": "08"}
                                )
                                send_customer_catalogue_link(chat_id, cust, first_name)
                                continue

                            cust, err = resolve_single_customer(candidate)
                            if cust:
                                send_customer_catalogue_link(chat_id, cust, first_name)
                                continue
                            elif err and err.get("status") == "disambiguation_required":
                                pending_order_customers[chat_id] = True
                                matches = err.get("matches", [])
                                buttons = [
                                    [{"text": f"👤 {m['display']}", "callback_data": f"order_cust_{m['id']}"}]
                                    for m in matches[:6]
                                ]
                                buttons.append([{"text": "❌ Cancel", "callback_data": "order_cust_cancel"}])
                                send_message(
                                    chat_id,
                                    f"Multiple customers found matching '<b>{candidate}</b>'. Please select the intended customer:",
                                    reply_markup={"inline_keyboard": buttons}
                                )
                                continue

                        # Customer was not specified in prompt -> Clarify before opening catalogue!
                        pending_order_customers[chat_id] = True
                        prompt_for_order_customer(chat_id, first_name)
                        continue

                    # Process via LangGraph AI agent with thread memory
                    response_dict = agent.process_message(prompt_text, thread_id=str(chat_id))
                    reply_text = response_dict.get("response") or response_dict.get("message") or "Done."

                    html_reply = markdown_to_telegram_html(reply_text)
                    formatted_reply = f"<b>OrderBot AI</b>:\n{html_reply}"
                    send_message(chat_id, formatted_reply)

                    # Send associated product photos if a product was retrieved/created
                    dispatch_product_photos_if_any(chat_id, response_dict, prompt_text, reply_text)

                    # Prompt transport carrier selection if a customer was newly created without an assigned transport
                    for tc in response_dict.get("tool_calls", []):
                        if tc.get("tool") == "create_customer":
                            res_data = tc.get("result", {})
                            if isinstance(res_data, dict) and res_data.get("transport_selection_needed"):
                                cid = res_data.get("id")
                                if cid:
                                    created_cust = Customer.objects.filter(id=cid).first()
                                    if created_cust and not created_cust.transport:
                                        prompt_for_customer_transport(chat_id, created_cust)

            time.sleep(1.5)
        except KeyboardInterrupt:
            print("\nStopping Telegram Bot Listener.")
            break
        except Exception as e:
            print(f"[Error] {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()

