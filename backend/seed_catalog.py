import os
import sys
import django
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from apps.core.models import Product

SAMPLE_SKUS = [
    {"sku": "STAT-A4-500", "name": "A4 Paper Copier 75GSM (Carton of 5 Reams)", "category": "Stationery", "base_price": Decimal("1150.00"), "hsn_code": "4802", "gst_rate": Decimal("18.00")},
    {"sku": "STAT-PEN-BLU", "name": "Ballpoint Pens Blue (Box of 50 Pcs)", "category": "Stationery", "base_price": Decimal("250.00"), "hsn_code": "9608", "gst_rate": Decimal("12.00")},
    {"sku": "STAT-NOTE-A5", "name": "Executive Spiral Notebook A5 200 Pages", "category": "Stationery", "base_price": Decimal("85.00"), "hsn_code": "4820", "gst_rate": Decimal("12.00")},
    {"sku": "PLAST-CONT-1L", "name": "Clear Plastic Food Container 1000ml (Pack of 100)", "category": "Plastics", "base_price": Decimal("650.00"), "hsn_code": "3924", "gst_rate": Decimal("18.00")},
    {"sku": "PLAST-BAG-MED", "name": "HDPE Heavy Duty Packaging Bags (Pack of 500)", "category": "Plastics", "base_price": Decimal("480.00"), "hsn_code": "3923", "gst_rate": Decimal("18.00")},
    {"sku": "PLAST-TAPE-2IN", "name": "Transparent Packing Tape 2 inch (Box of 36 Rolls)", "category": "Plastics", "base_price": Decimal("720.00"), "hsn_code": "3919", "gst_rate": Decimal("18.00")},
]

def seed():
    for item in SAMPLE_SKUS:
        p, created = Product.objects.get_or_create(sku=item["sku"], defaults=item)
        if created:
            print(f"[OK] Created SKU: {p.sku} - {p.name}")
        else:
            print(f"[INFO] SKU {p.sku} already exists.")

if __name__ == "__main__":
    seed()
