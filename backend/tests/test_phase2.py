import os
import sys
import django
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from backend.agent.tools import (
    tool_create_customer, tool_create_product, tool_create_order,
    tool_record_payment, tool_get_customer_ledger
)

def run_tests():
    print("=" * 65)
    print("      RUNNING PHASE 2 ACCOUNTING & LEDGER TEST SUITE      ")
    print("=" * 65)

    # 1. Onboard Customer & Create Product
    print("\n[1] Onboarding Customer & Product...")
    cust_res = tool_create_customer(name="Jaipur Toy World", phone="+919988776655", state_code="08")
    prod_res = tool_create_product(sku="TOY-CAR-99", name="Diecast Supercar", loose_price=500.0, full_carton_price=10000.0)
    assert cust_res["status"] == "success"
    assert prod_res["status"] == "success"

    # 2. Place Sales Order (Total = 10000 + 18% GST = 11800)
    print("\n[2] Placing Sales Order...")
    order_res = tool_create_order(
        customer_identifier="Jaipur Toy World",
        items=[{"product": "TOY-CAR-99", "quantity": 1, "unit_type": "full_carton"}]
    )
    print(f"Order Voucher: {order_res['voucher_no']}, Total Amount: Rs.{order_res['total_amount']}")
    assert order_res["status"] == "success"
    assert order_res["total_amount"] == 11800.0

    # 3. Record Payment of Rs.5000 via UPI
    print("\n[3] Recording Customer Payment of Rs.5000 via UPI...")
    pay_res = tool_record_payment(
        customer_identifier="Jaipur Toy World",
        amount=5000.0,
        payment_mode="Bank",
        narration="Advance payment via GPay"
    )
    print("Payment Record Result:", pay_res)
    assert pay_res["status"] == "success"
    assert pay_res["amount_paid"] == 5000.0
    assert pay_res["remaining_balance"] == 6800.0

    # 4. Fetch Ledger Statement
    print("\n[4] Fetching Customer Ledger Statement...")
    ledger_res = tool_get_customer_ledger(customer_identifier="Jaipur Toy World")
    print(f"Customer Balance: Rs.{ledger_res['balance_amount']}")
    print("Ledger Entries:")
    for entry in ledger_res["entries"]:
        print(f"  [{entry['entry_type'].upper()}] Voucher: {entry['voucher_number']} | Amount: Rs.{entry['amount']} | Narration: {entry['narration']}")

    assert ledger_res["status"] == "success"
    assert len(ledger_res["entries"]) > 0

    print("\n" + "=" * 65)
    print("    ALL PHASE 2 ACCOUNTING & LEDGER TESTS PASSED!         ")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
