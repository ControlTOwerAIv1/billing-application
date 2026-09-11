import os
import sys
import django
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from apps.core.models import Product, Customer, Account, AccountGroup, CustomerStatus

SAMPLE_SKUS = [
    {
        "sku": "STAT-A4-500",
        "name": "A4 Paper Copier 75GSM (Carton of 5 Reams)",
        "category": "Stationery",
        "image_url": "https://images.unsplash.com/photo-1586075010923-2dd4570fb338?w=500&auto=format&fit=crop&q=80",
        "base_price": Decimal("1150.00"),
        "loose_price": Decimal("1150.00"),
        "full_carton_price": Decimal("5400.00"),
        "half_carton_price": Decimal("2800.00"),
        "full_carton_quantity": 5,
        "hsn_code": "4802",
        "gst_rate": Decimal("18.00")
    },
    {
        "sku": "STAT-PEN-BLU",
        "name": "Ballpoint Pens Blue (Box of 50 Pcs)",
        "category": "Stationery",
        "image_url": "https://images.unsplash.com/photo-1583485088034-697b5bc54ccd?w=500&auto=format&fit=crop&q=80",
        "base_price": Decimal("250.00"),
        "loose_price": Decimal("250.00"),
        "full_carton_price": Decimal("2200.00"),
        "half_carton_price": Decimal("1150.00"),
        "full_carton_quantity": 10,
        "hsn_code": "9608",
        "gst_rate": Decimal("12.00")
    },
    {
        "sku": "STAT-NOTE-A5",
        "name": "Executive Spiral Notebook A5 200 Pages",
        "category": "Stationery",
        "image_url": "https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=500&auto=format&fit=crop&q=80",
        "base_price": Decimal("85.00"),
        "loose_price": Decimal("85.00"),
        "full_carton_price": Decimal("3800.00"),
        "half_carton_price": Decimal("1950.00"),
        "full_carton_quantity": 50,
        "hsn_code": "4820",
        "gst_rate": Decimal("12.00")
    },
    {
        "sku": "PLAST-CONT-1L",
        "name": "Clear Plastic Food Container 1000ml (Pack of 100)",
        "category": "Plastics",
        "image_url": "https://images.unsplash.com/photo-1614735241165-6756e1df61ab?w=500&auto=format&fit=crop&q=80",
        "base_price": Decimal("650.00"),
        "loose_price": Decimal("650.00"),
        "full_carton_price": Decimal("3600.00"),
        "half_carton_price": Decimal("1850.00"),
        "full_carton_quantity": 6,
        "hsn_code": "3924",
        "gst_rate": Decimal("18.00")
    },
    {
        "sku": "PLAST-BAG-MED",
        "name": "HDPE Heavy Duty Packaging Bags (Pack of 500)",
        "category": "Packaging",
        "image_url": "https://images.unsplash.com/photo-1530587191325-3db32d826c18?w=500&auto=format&fit=crop&q=80",
        "base_price": Decimal("480.00"),
        "loose_price": Decimal("480.00"),
        "full_carton_price": Decimal("4400.00"),
        "half_carton_price": Decimal("2300.00"),
        "full_carton_quantity": 10,
        "hsn_code": "3923",
        "gst_rate": Decimal("18.00")
    },
    {
        "sku": "PLAST-TAPE-2IN",
        "name": "Transparent Packing Tape 2 inch (Box of 36 Rolls)",
        "category": "Packaging",
        "image_url": "https://images.unsplash.com/photo-1607344645866-009c320c5ab8?w=500&auto=format&fit=crop&q=80",
        "base_price": Decimal("720.00"),
        "loose_price": Decimal("720.00"),
        "full_carton_price": Decimal("2700.00"),
        "half_carton_price": Decimal("1400.00"),
        "full_carton_quantity": 4,
        "hsn_code": "3919",
        "gst_rate": Decimal("18.00")
    },
    {
        "sku": "OFF-CALC-12D",
        "name": "12-Digit Desktop Business Calculator",
        "category": "Office Electronics",
        "image_url": "https://images.unsplash.com/photo-1594980596870-8aa52a78d8cd?w=500&auto=format&fit=crop&q=80",
        "base_price": Decimal("380.00"),
        "loose_price": Decimal("380.00"),
        "full_carton_price": Decimal("6800.00"),
        "half_carton_price": Decimal("3500.00"),
        "full_carton_quantity": 20,
        "hsn_code": "8470",
        "gst_rate": Decimal("18.00")
    }
]

SAMPLE_CUSTOMERS = [
    {
        "name": "Raj Wholesalers",
        "phone": "+91-9876543210",
        "city": "Kolkata",
        "state_code": "19",
        "business_name": "Raj Wholesalers Bengal Pvt Ltd",
        "credit_limit": Decimal("50000.00"),
        "balance_amount": Decimal("12500.00")
    },
    {
        "name": "Raj Wholesalers",
        "phone": "+91-9123456780",
        "city": "Jaipur",
        "state_code": "08",
        "business_name": "Raj Wholesalers Rajasthan Trading",
        "credit_limit": Decimal("75000.00"),
        "balance_amount": Decimal("0.00")
    },
    {
        "name": "Agarwal Paper Mart",
        "phone": "+91-9822011223",
        "city": "Jaipur",
        "state_code": "08",
        "business_name": "Agarwal Paper Mart & Packaging",
        "credit_limit": Decimal("100000.00"),
        "balance_amount": Decimal("4200.00")
    },
    {
        "name": "Metro Retailers",
        "phone": "+91-9988776655",
        "city": "Delhi",
        "state_code": "07",
        "business_name": "Metro Retail Enterprises",
        "credit_limit": Decimal("30000.00"),
        "balance_amount": Decimal("0.00")
    }
]

def seed():
    print("[*] Seeding Products with Multi-tier Pricing & Photos...")
    for item in SAMPLE_SKUS:
        p, created = Product.objects.get_or_create(sku=item["sku"], defaults=item)
        if not created:
            for k, v in item.items():
                setattr(p, k, v)
            p.save()
            print(f"[UPDATED] SKU: {p.sku} - {p.name}")
        else:
            print(f"[CREATED] SKU: {p.sku} - {p.name}")

    print("\n[*] Seeding Customers with Locations (for disambiguation testing)...")
    for cust_data in SAMPLE_CUSTOMERS:
        c, created = Customer.objects.get_or_create(
            phone=cust_data["phone"],
            defaults=cust_data
        )
        if not created:
            for k, v in cust_data.items():
                setattr(c, k, v)
            c.save()
            print(f"[UPDATED] Customer: {c.name} ({c.city}, {c.state_code})")
        else:
            print(f"[CREATED] Customer: {c.name} ({c.city}, {c.state_code})")

        Account.objects.get_or_create(
            name=f"Debtor - {c.name} ({c.city})",
            customer=c,
            defaults={"account_group": AccountGroup.DEBTORS}
        )

    print("\n[OK] Database successfully seeded!")

if __name__ == "__main__":
    seed()
