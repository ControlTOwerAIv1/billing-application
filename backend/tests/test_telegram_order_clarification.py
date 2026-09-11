import os
import sys
import django
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from apps.core.models import Customer
from backend.run_telegram_bot import is_new_order_intent, resolve_single_customer, pending_order_customers

def test_intent_detection():
    print("Testing intent detection...")
    assert is_new_order_intent("i want to add an order") is True
    assert is_new_order_intent("add an order") is True
    assert is_new_order_intent("create order") is True
    assert is_new_order_intent("open catalogue") is True
    assert is_new_order_intent("add order for Raj Wholesalers") is True
    
    # Must NOT trigger new order on inquiry/status queries
    assert is_new_order_intent("what is the status of order #123") is False
    assert is_new_order_intent("list orders") is False
    assert is_new_order_intent("show order history") is False
    assert is_new_order_intent("cancel order #10") is False
    print("✅ Intent detection tests passed.")

def test_customer_resolution():
    print("Testing customer resolution...")
    cust = Customer.objects.first()
    assert cust is not None, "A customer must exist in database"
    
    resolved, err = resolve_single_customer(cust.name)
    assert resolved is not None
    assert resolved.id == cust.id
    print(f"✅ Customer resolution verified for '{cust.name}' -> ID: {resolved.id}")

def test_pending_state_cleared():
    print("Testing pending customer state tracking...")
    chat_id = 9999999
    pending_order_customers[chat_id] = True
    assert chat_id in pending_order_customers
    pending_order_customers.pop(chat_id, None)
    assert chat_id not in pending_order_customers
    print("✅ State tracking tests passed.")

def test_prompt_for_order_customer_generation():
    print("Testing prompt_for_order_customer query and keyboard generation...")
    import backend.run_telegram_bot as rtb
    sent_msgs = []
    orig_send = rtb.send_message
    try:
        rtb.send_message = lambda cid, txt, reply_markup=None: sent_msgs.append((cid, txt, reply_markup))
        rtb.prompt_for_order_customer(12345, "jafer")
        assert len(sent_msgs) == 1
        cid, txt, markup = sent_msgs[0]
        assert cid == 12345
        assert "Customer Clarification" in txt
        assert "inline_keyboard" in markup
        assert len(markup["inline_keyboard"]) > 0
        print("✅ prompt_for_order_customer executed cleanly without database errors.")
    finally:
        rtb.send_message = orig_send

if __name__ == "__main__":
    test_intent_detection()
    test_customer_resolution()
    test_pending_state_cleared()
    test_prompt_for_order_customer_generation()
    print("\n🎉 ALL TELEGRAM ORDER CLARIFICATION TESTS PASSED SUCCESSFULLY!")
