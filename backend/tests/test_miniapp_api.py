import os
import sys
import django
import unittest
from decimal import Decimal
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from django.test import Client
from apps.core.models import Customer, Product, Order
from backend.invoice_generator import generate_order_pdf_bytes

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
                "loose_price": 500.00,
                "gst_rate": 18.00,
                "hsn_code": "4802"
            }
        )
        self.product.base_price = Decimal("500.00")
        self.product.loose_price = Decimal("500.00")
        self.product.save()

    def test_01_cart_init_endpoint(self):
        response = self.client.get(f"/api/cart/init?customer_id={self.customer.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["customer"]["id"], self.customer.id)
        self.assertGreaterEqual(len(data["catalog"]), 1)
        print("\n[OK] Mini App Cart Init API test passed.")

    def test_02_cart_price_endpoint(self):
        # 1. Standard calculation without packing/discount
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}]
        }
        response = self.client.post("/api/cart/price", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["subtotal"], 1000.0)
        self.assertEqual(data["total_amount"], 1180.0) # 1000 + 18% GST (180)
        
        # 2. Calculation with packing charge and discount amount
        payload_with_adjustments = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "packing_charge": 50.0,
            "discount_amount": 30.0
        }
        response_adj = self.client.post("/api/cart/price", data=payload_with_adjustments, content_type="application/json")
        self.assertEqual(response_adj.status_code, 200)
        data_adj = response_adj.json()
        self.assertEqual(data_adj["subtotal"], 1000.0)
        self.assertEqual(data_adj["packing_charge"], 50.0)
        self.assertEqual(data_adj["discount_amount"], 30.0)
        # 1000 subtotal + 180 GST + 50 packing - 30 discount = 1200
        self.assertEqual(data_adj["total_amount"], 1200.0)
        print("[OK] Mini App Server-side GST Pricing with Packing & Discount API test passed (1000 + 180 + 50 - 30 = 1200).")

    def test_03_submit_order_endpoint_with_adjustments(self):
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "packing_charge": 75.0,
            "discount_amount": 25.0
        }
        response = self.client.post("/api/cart/submit", data=payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("ORD-2026-", data["voucher_no"])
        self.assertEqual(data["packing_charge"], 75.0)
        self.assertEqual(data["discount_amount"], 25.0)
        # 1000 subtotal + 180 GST + 75 packing - 25 discount = 1230.0
        self.assertEqual(data["total_amount"], 1230.0)

        # Verify database record
        order = Order.objects.get(id=data["order_id"])
        self.assertEqual(float(order.packing_charge), 75.0)
        self.assertEqual(float(order.discount_amount), 25.0)
        self.assertEqual(float(order.total_amount), 1230.0)

        # Verify PDF invoice generation with packing and discount
        pdf_bytes = generate_order_pdf_bytes(order)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        print(f"[OK] Mini App Submit Order with Packing & Discount API test passed -> Order #{order.voucher_no} Total: Rs.{order.total_amount}")

    def test_04_edit_order_endpoint(self):
        # Create an order first
        submit_payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 1}],
            "packing_charge": 20.0,
            "discount_amount": 10.0
        }
        submit_res = self.client.post("/api/cart/submit", data=submit_payload, content_type="application/json")
        order_id = submit_res.json()["order_id"]

        # Edit order: change quantity to 3, status to packed, packing to 40, discount to 50
        edit_payload = {
            "status": "packed",
            "packing_charge": 40.0,
            "discount_amount": 50.0,
            "items": [{"product_id": self.product.id, "quantity": 3, "unit_type": "loose"}]
        }
        edit_res = self.client.post(f"/api/orders/{order_id}/edit", data=edit_payload, content_type="application/json")
        self.assertEqual(edit_res.status_code, 200)
        data = edit_res.json()
        self.assertEqual(data["order_status"], "packed")
        self.assertEqual(data["packing_charge"], 40.0)
        self.assertEqual(data["discount_amount"], 50.0)
        # Subtotal: 3 * 500 = 1500 + 18% GST (270) + 40 packing - 50 discount = 1760.0
        self.assertEqual(data["subtotal"], 1500.0)
        self.assertEqual(data["total_amount"], 1760.0)
        print("[OK] Mini App Edit Order API with Packing & Discount test passed.")

    def test_05_list_orders_and_detail_endpoint(self):
        response = self.client.get(f"/api/orders?customer_id={self.customer.id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertGreaterEqual(len(data["orders"]), 1)
        
        first_order = data["orders"][0]
        self.assertIn("packing_charge", first_order)
        self.assertIn("discount_amount", first_order)

        # Test single order detail endpoint
        detail_res = self.client.get(f"/api/orders/{first_order['id']}")
        self.assertEqual(detail_res.status_code, 200)
        detail_data = detail_res.json()
        self.assertIn("packing_charge", detail_data)
        self.assertIn("discount_amount", detail_data)
        print("[OK] Mini App List & Detail Orders API test passed.")

    def test_06_percentage_discount_pricing_and_submission(self):
        # 1. Price cart with 10% discount on total
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "packing_charge": 50.0,
            "discount_type": "percent",
            "discount_percent": 10.0
        }
        res = self.client.post("/api/cart/price", data=payload, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Gross before discount: 1000 subtotal + 180 GST + 50 packing = 1230.0
        # 10% discount = 123.0
        self.assertEqual(data["discount_amount"], 123.0)
        self.assertEqual(data["discount_type"], "percent")
        self.assertEqual(data["discount_percent"], 10.0)
        self.assertEqual(data["total_amount"], 1107.0)

        # 2. Submit order with 10% discount
        submit_res = self.client.post("/api/cart/submit", data=payload, content_type="application/json")
        self.assertEqual(submit_res.status_code, 200)
        sub_data = submit_res.json()
        self.assertEqual(sub_data["discount_amount"], 123.0)
        self.assertEqual(sub_data["total_amount"], 1107.0)

        order = Order.objects.get(id=sub_data["order_id"])
        self.assertEqual(float(order.discount_amount), 123.0)
        self.assertEqual(float(order.total_amount), 1107.0)

        # 3. Verify PDF generation works
        pdf_bytes = generate_order_pdf_bytes(order)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        print(f"[OK] Percentage discount test passed: 10% on Rs. 1,230 = -Rs. 123.00, Net Total: Rs. {order.total_amount}")

    def test_07_edit_order_with_percentage_discount(self):
        # Create an order
        submit_payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "packing_charge": 50.0,
            "discount_amount": 0.0
        }
        res = self.client.post("/api/cart/submit", data=submit_payload, content_type="application/json")
        order_id = res.json()["order_id"]

        # Edit order with 5% discount
        edit_payload = {
            "discount_type": "percent",
            "discount_percent": 5.0,
            "packing_charge": 50.0
        }
        edit_res = self.client.post(f"/api/orders/{order_id}/edit", data=edit_payload, content_type="application/json")
        self.assertEqual(edit_res.status_code, 200)

        order = Order.objects.get(id=order_id)
        # Gross = 1000 + 180 + 50 = 1230. 5% = 61.50
        self.assertEqual(float(order.discount_amount), 61.5)
        self.assertEqual(float(order.total_amount), 1168.5)
        print(f"[OK] Edit order percentage discount passed: 5% on Rs. 1,230 = -Rs. 61.50, Net Total: Rs. {order.total_amount}")

if __name__ == "__main__":
    unittest.main()

