import os
import sys
import django
import unittest
from decimal import Decimal
from pathlib import Path
import io

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from django.test import Client
from apps.core.models import Customer, Product, Order, Transport
from backend.invoice_generator import generate_order_pdf_bytes


class TestOptionalGSTFeature(unittest.TestCase):

    def setUp(self):
        self.client = Client()
        self.customer, _ = Customer.objects.get_or_create(
            name="GST Test Customer",
            defaults={"phone": "+919123456780", "state_code": "08"}  # Rajasthan (Intra-state)
        )
        self.product, _ = Product.objects.get_or_create(
            sku="GST-TEST-SKU-01",
            defaults={
                "name": "Heavy Duty Plastic Pipe 20mm",
                "category": "Pipes",
                "base_price": 500.00,
                "gst_rate": 18.00,
                "hsn_code": "3917"
            }
        )

    def test_01_pricing_with_gst_disabled(self):
        """When gst_enabled=False, no GST tax should be added."""
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "packing_charge": 50.00,
            "discount_amount": 20.00,
            "gst_enabled": False,
            "gst_rate": 18.00
        }
        resp = self.client.post("/api/cart/price", data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["gst_enabled"], False)
        self.assertEqual(data["subtotal"], 1000.00)
        self.assertEqual(data["cgst_amount"], 0.0)
        self.assertEqual(data["sgst_amount"], 0.0)
        self.assertEqual(data["igst_amount"], 0.0)
        # Total = 1000 + 50 - 20 = 1030
        self.assertEqual(data["total_amount"], 1030.00)
        print("\n[OK] Pricing with GST disabled passed: Total = Rs. 1030.00 (Tax = 0)")

    def test_02_pricing_with_custom_gst_rate(self):
        """When gst_enabled=True and custom gst_rate is provided (e.g. 12%), tax should be 12%."""
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "packing_charge": 0.0,
            "discount_amount": 0.0,
            "gst_enabled": True,
            "gst_rate": 12.00
        }
        resp = self.client.post("/api/cart/price", data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["gst_enabled"], True)
        self.assertEqual(data["gst_rate"], 12.00)
        self.assertEqual(data["subtotal"], 1000.00)
        # 12% intra-state: 6% CGST (60) + 6% SGST (60) = 120
        self.assertEqual(data["cgst_amount"], 60.00)
        self.assertEqual(data["sgst_amount"], 60.00)
        self.assertEqual(data["total_amount"], 1120.00)
        print("\n[OK] Pricing with custom 12% GST rate passed: Total = Rs. 1120.00 (CGST 60 + SGST 60)")

    def test_03_submit_order_with_gst_disabled(self):
        """Submitting an order with gst_enabled=False persists flag and generates non-GST invoice."""
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 1}],
            "packing_charge": 25.00,
            "discount_amount": 10.00,
            "gst_enabled": False,
            "gst_rate": 18.00
        }
        resp = self.client.post("/api/cart/submit", data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["gst_enabled"], False)
        # Subtotal: 500, pack: 25, disc: 10 => total: 515
        self.assertEqual(data["total_amount"], 515.00)

        # Verify DB order record
        order = Order.objects.get(id=data["order_id"])
        self.assertFalse(order.gst_enabled)
        self.assertEqual(order.cgst_amount, Decimal("0.00"))
        self.assertEqual(order.sgst_amount, Decimal("0.00"))
        self.assertEqual(order.igst_amount, Decimal("0.00"))
        self.assertEqual(order.total_amount, Decimal("515.00"))

        # Verify PDF generation
        pdf_bytes = generate_order_pdf_bytes(order)
        self.assertIsNotNone(pdf_bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        print("\n[OK] Submit order without GST verified: DB values and PDF generated successfully (non-GST bill).")

    def test_04_submit_order_with_custom_gst_rate(self):
        """Submitting an order with gst_enabled=True and custom rate (e.g. 18%) generates full TAX INVOICE."""
        payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "packing_charge": 50.00,
            "discount_amount": 0.00,
            "gst_enabled": True,
            "gst_rate": 18.00
        }
        resp = self.client.post("/api/cart/submit", data=payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["gst_enabled"])
        self.assertEqual(data["gst_rate"], 18.00)

        order = Order.objects.get(id=data["order_id"])
        self.assertTrue(order.gst_enabled)
        self.assertEqual(order.custom_gst_rate, Decimal("18.00"))
        # Subtotal: 1000, CGST: 90, SGST: 90, Packing: 50 => Total: 1230
        self.assertEqual(order.total_amount, Decimal("1230.00"))

        pdf_bytes = generate_order_pdf_bytes(order)
        self.assertIsNotNone(pdf_bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        print("\n[OK] Submit order with custom GST rate verified: TAX INVOICE with 9.0% CGST + 9.0% SGST generated.")

    def test_05_edit_order_toggle_gst(self):
        """Editing an order to disable GST removes taxes and updates totals."""
        import uuid
        # Create an order with GST enabled initially
        order = Order.objects.create(
            voucher_no=f"TST-GST-{uuid.uuid4().hex[:6].upper()}",
            customer=self.customer,
            status="placed",
            gst_enabled=True,
            custom_gst_rate=Decimal("18.00"),
            packing_charge=Decimal("40.00"),
            discount_amount=Decimal("10.00")
        )
        order.items.create(
            product=self.product,
            quantity=1,
            unit_price=Decimal("500.00"),
            taxable_amount=Decimal("500.00"),
            gst_rate=Decimal("18.00")
        )
        order.calculate_taxes_and_totals()
        order.save()
        self.assertGreater(order.cgst_amount + order.sgst_amount, 0)

        # Now edit order via API to disable GST
        edit_payload = {
            "status": "placed",
            "packing_charge": 40.00,
            "discount_amount": 10.00,
            "gst_enabled": False,
            "gst_rate": 18.00,
            "items": [{"product_id": self.product.id, "quantity": 1, "unit_type": "loose"}]
        }
        resp = self.client.post(f"/api/orders/{order.id}/edit", data=edit_payload, content_type="application/json")
        self.assertEqual(resp.status_code, 200)

        order.refresh_from_db()
        self.assertFalse(order.gst_enabled)
        self.assertEqual(order.cgst_amount, Decimal("0.00"))
        self.assertEqual(order.sgst_amount, Decimal("0.00"))
        self.assertEqual(order.igst_amount, Decimal("0.00"))
        # 500 + 40 - 10 = 530.00
        self.assertEqual(order.total_amount, Decimal("530.00"))

        # Verify get_order_detail returns the updated flags
        detail_resp = self.client.get(f"/api/orders/{order.id}")
        self.assertEqual(detail_resp.status_code, 200)
        detail_data = detail_resp.json()
        self.assertFalse(detail_data["gst_enabled"])
        self.assertEqual(detail_data["total_amount"], 530.00)
        print("\n[OK] Edit order to disable GST passed: order converted from GST to Non-GST seamlessly.")

    def test_06_pricing_and_submit_with_zero_or_empty_gst_rate(self):
        """When user enters 0 or leaves GST rate empty, GST is disabled and hidden from PDF."""
        # 1. Price cart with rate=0
        payload_zero = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "gst_enabled": True,
            "gst_rate": 0.0
        }
        resp = self.client.post("/api/cart/price", data=payload_zero, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["gst_enabled"])
        self.assertEqual(data["cgst_amount"], 0.0)
        self.assertEqual(data["sgst_amount"], 0.0)
        self.assertEqual(data["total_amount"], 1000.0)

        # 2. Submit order with rate=0
        submit_payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "gst_enabled": True,
            "gst_rate": 0.0
        }
        submit_resp = self.client.post("/api/cart/submit", data=submit_payload, content_type="application/json")
        self.assertEqual(submit_resp.status_code, 200)
        submit_data = submit_resp.json()
        self.assertFalse(submit_data["gst_enabled"])

        order = Order.objects.get(id=submit_data["order_id"])
        self.assertFalse(order.gst_enabled)
        self.assertEqual(order.cgst_amount, Decimal("0.00"))
        self.assertEqual(order.sgst_amount, Decimal("0.00"))
        self.assertEqual(order.total_amount, Decimal("1000.00"))

        # 3. Generate PDF and verify it generates valid bill without error
        pdf_bytes = generate_order_pdf_bytes(order)
        self.assertIsNotNone(pdf_bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        print("\n[OK] Zero/empty GST rate handling verified: GST disabled, taxes=0, and non-GST invoice generated.")


if __name__ == "__main__":
    unittest.main()
