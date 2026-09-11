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

from apps.core.models import Order
from backend.invoice_generator import generate_order_pdf_bytes

def test_pdf_generation():
    print("=" * 65)
    print("      TESTING ORDERBOT PDF INVOICE GENERATOR             ")
    print("=" * 65)

    order = Order.objects.filter(items__isnull=False).first()
    if not order:
        order = Order.objects.first()

    assert order is not None, "No orders found in database to test PDF generation"
    print(f"Generating PDF invoice for Order #{order.voucher_no} ({order.customer.name})...")

    pdf_bytes = generate_order_pdf_bytes(order)
    print(f"Generated PDF Size: {len(pdf_bytes)} bytes")

    assert pdf_bytes is not None, "PDF bytes should not be None"
    assert len(pdf_bytes) > 500, "PDF size should be at least 500 bytes"
    assert pdf_bytes.startswith(b"%PDF"), "PDF output must start with standard %PDF header magic bytes"

    # Also test multi-item multi-category order
    multi_item_order = Order.objects.filter(items__isnull=False).filter(items__product__isnull=False).distinct()
    for candidate in multi_item_order:
        if candidate.items.count() > 1:
            multi_order_pdf = generate_order_pdf_bytes(candidate)
            assert multi_order_pdf.startswith(b"%PDF")
            print(f"Verified multi-item order #{candidate.voucher_no} ({candidate.items.count()} items): {len(multi_order_pdf)} bytes")
            break

    print("\n" + "=" * 65)
    print("     PDF INVOICE GENERATION TEST COMPLETED SUCCESSFULLY!  ")
    print("=" * 65)

if __name__ == "__main__":
    test_pdf_generation()
