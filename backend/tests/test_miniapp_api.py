import os
import sys
import django
import unittest
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from django.test import Client
from apps.core.models import Customer, Product, Order

class TestMiniAppAPI(unittest.TestCase):

    def setUp(self):
        self.client = Client()
        self.customer, _ = Customer.objects.get_or_create(
            name="Test Retailer Shop",
            defaults={"phone": "+919988776655", "state_code": "08"}
        )
        self.product, _ = Product.objects.get_or_create(
            sku="TEST-SKU-01",
            defaults={
                "name": "Test Stationery A4 Paper",
                "category": "Stationery",
                "base_price": 500.00,
                "gst_rate": 18.00,
                "hsn_code": "4802"
            }
        )

    def test_01_cart_init_endpoint(self):
        response = self.client.get(f"/api/cart/init?customer_id={self.customer.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customer"]["id"], self.customer.id)
        self.assertGreaterEqual(len(data["catalog"]), 1)
        print("\n[OK] Mini App Cart Init API test passed.")

    def test_02_cart_price_endpoint(self):
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}]
        }
        response = self.client.post("/api/cart/price", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtotal"], 1000.0)
        self.assertEqual(data["total_amount"], 1180.0) # 1000 + 18% GST (180)
        print("[OK] Mini App Server-side GST Pricing API test passed (1000 Subtotal + 18% GST = 1180 Total).")

    def test_03_submit_order_endpoint(self):
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 1}]
        }
        response = self.client.post("/api/cart/submit", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("ORD-2026-", data["voucher_no"])
        print(f"[OK] Mini App Submit Order API test passed -> Voucher: #{data['voucher_no']}")

if __name__ == "__main__":
    unittest.main()
