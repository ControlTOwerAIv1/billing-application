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

    def test_08_submit_and_edit_order_with_notes(self):
        # 1. Submit order with order note
        note_text = "Deliver before 5 PM at Godown, handle with care"
        submit_payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2}],
            "notes": note_text,
            "packing_charge": 50.0,
            "discount_amount": 0.0
        }
        res = self.client.post("/api/cart/submit", data=submit_payload, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["notes"], note_text)
        order_id = data["order_id"]

        # 2. Verify in database
        order = Order.objects.get(id=order_id)
        self.assertEqual(order.notes, note_text)

        # 3. Verify in order detail endpoint
        detail_res = self.client.get(f"/api/orders/{order_id}")
        self.assertEqual(detail_res.status_code, 200)
        self.assertEqual(detail_res.json()["notes"], note_text)

        # 4. Verify in order list endpoint
        list_res = self.client.get(f"/api/orders?customer_id={self.customer.id}")
        self.assertEqual(list_res.status_code, 200)
        order_entry = next((o for o in list_res.json()["orders"] if o["id"] == order_id), None)
        self.assertIsNotNone(order_entry)
        self.assertEqual(order_entry["notes"], note_text)

        # 5. Verify PDF generation includes note
        pdf_bytes = generate_order_pdf_bytes(order)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        import pymupdf
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        full_text = "\n".join(page.get_text() for page in doc)
        self.assertIn("Note:", full_text)
        self.assertIn("Deliver before 5 PM at Godown, handle with care", full_text)

        # 6. Edit order with updated note
        updated_note = "Updated: Urgent delivery at Main Gate"
        edit_payload = {
            "notes": updated_note
        }
        edit_res = self.client.post(f"/api/orders/{order_id}/edit", data=edit_payload, content_type="application/json")
        self.assertEqual(edit_res.status_code, 200)
        self.assertEqual(edit_res.json()["notes"], updated_note)

        order.refresh_from_db()
        self.assertEqual(order.notes, updated_note)
        print(f"[OK] Submit and edit order with notes verified successfully: '{order.notes}'")

    def test_09_hide_product_rate_pdf_and_api(self):
        import pymupdf

        # 1. Test price_cart reflects hide_product_rate
        price_payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 3}],
            "hide_product_rate": True
        }
        price_res = self.client.post("/api/cart/price", data=price_payload, content_type="application/json")
        self.assertEqual(price_res.status_code, 200)
        self.assertTrue(price_res.json()["hide_product_rate"])

        # 2. Submit order with hide_product_rate=True
        submit_payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 4}],
            "hide_product_rate": True,
            "packing_charge": 40.0,
            "discount_amount": 0.0
        }
        res = self.client.post("/api/cart/submit", data=submit_payload, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["hide_product_rate"])
        order_id = data["order_id"]

        # 3. Verify in database
        order = Order.objects.get(id=order_id)
        self.assertTrue(order.hide_product_rate)

        # 4. Verify in order detail endpoint
        detail_res = self.client.get(f"/api/orders/{order_id}")
        self.assertEqual(detail_res.status_code, 200)
        self.assertTrue(detail_res.json()["hide_product_rate"])

        # 5. Verify in order list endpoint
        list_res = self.client.get(f"/api/orders?customer_id={self.customer.id}")
        self.assertEqual(list_res.status_code, 200)
        order_entry = next((o for o in list_res.json()["orders"] if o["id"] == order_id), None)
        self.assertIsNotNone(order_entry)
        self.assertTrue(order_entry["hide_product_rate"])

        # 6. Verify PDF generation masks rates & prices
        pdf_bytes = generate_order_pdf_bytes(order)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        pdf_text = "\n".join(page.get_text() for page in doc)

        self.assertIn("DELIVERY CHALLAN / ESTIMATE", pdf_text)
        self.assertIn("Total Distinct Items", pdf_text)
        self.assertIn("Total Quantity", pdf_text)
        self.assertIn("Product rates and amounts are withheld", pdf_text)
        self.assertNotIn("Rate (Rs.)", pdf_text)
        self.assertNotIn("Amount (Rs.)", pdf_text)
        self.assertNotIn("Grand Total:", pdf_text)
        print("[OK] PDF with hidden rates generated and verified (challan format, rates & totals suppressed).")

        # 7. Edit order to reveal rates again
        edit_payload = {
            "hide_product_rate": False
        }
        edit_res = self.client.post(f"/api/orders/{order_id}/edit", data=edit_payload, content_type="application/json")
        self.assertEqual(edit_res.status_code, 200)
        self.assertFalse(edit_res.json()["hide_product_rate"])

        order.refresh_from_db()
        self.assertFalse(order.hide_product_rate)

        # 8. Verify PDF with rates restored
        pdf_bytes_restored = generate_order_pdf_bytes(order)
        doc_restored = pymupdf.open(stream=pdf_bytes_restored, filetype="pdf")
        pdf_text_restored = "\n".join(page.get_text() for page in doc_restored)
        self.assertIn("Rate (Rs.)", pdf_text_restored)
        self.assertIn("Amount (Rs.)", pdf_text_restored)
        print("[OK] Restored PDF contains rates and grand totals as expected.")

    def test_10_whatsapp_invoice_feature(self):
        from apps.api.api import format_whatsapp_phone, generate_whatsapp_invoice_data

        # 1. Test phone number normalization
        self.assertEqual(format_whatsapp_phone("9876543210"), "919876543210")
        self.assertEqual(format_whatsapp_phone("+91 98765 43210"), "919876543210")
        self.assertEqual(format_whatsapp_phone("+91-9876543210"), "919876543210")
        self.assertEqual(format_whatsapp_phone("09876543210"), "919876543210")

        # 2. Test submit_order includes WhatsApp link & image_url
        submit_payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2.5}],
            "notes": "WhatsApp Invoice Delivery test",
            "packing_charge": 25.0
        }
        res = self.client.post("/api/cart/submit", data=submit_payload, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("whatsapp_url", data)
        self.assertIn("whatsapp_phone", data)
        self.assertIn("customer_phone", data)
        self.assertIn("image_url", data)
        self.assertTrue(data["whatsapp_url"].startswith("https://wa.me/"))
        self.assertIn(data["whatsapp_phone"], data["whatsapp_url"])
        order_id = data["order_id"]

        # 3. Test GET /api/orders/{order_id}/whatsapp endpoint
        wa_res = self.client.get(f"/api/orders/{order_id}/whatsapp")
        self.assertEqual(wa_res.status_code, 200)
        wa_json = wa_res.json()
        self.assertEqual(wa_json["status"], "success")
        self.assertEqual(wa_json["voucher_no"], data["voucher_no"])
        self.assertTrue(wa_json["whatsapp_url"].startswith("https://wa.me/"))
        self.assertIn("image_url", wa_json)
        self.assertEqual(wa_json["message_text"], "") # Text message removed

        # 4. Test GET /api/orders/{order_id}/image photo invoice endpoint
        img_res = self.client.get(f"/api/orders/{order_id}/image")
        self.assertEqual(img_res.status_code, 200)
        self.assertEqual(img_res["Content-Type"], "image/png")
        self.assertGreater(len(img_res.content), 1000)

        # 5. Test GET /api/orders includes WhatsApp URL and image_url
        list_res = self.client.get(f"/api/orders?customer_id={self.customer.id}")
        self.assertEqual(list_res.status_code, 200)
        order_entry = next((o for o in list_res.json()["orders"] if o["id"] == order_id), None)
        self.assertIsNotNone(order_entry)
        self.assertIn("whatsapp_url", order_entry)
        self.assertIn("image_url", order_entry)
        self.assertTrue(order_entry["whatsapp_url"].startswith("https://wa.me/"))

        # 6. Test GET /api/orders/{order_id} detail includes WhatsApp URL and image_url
        detail_res = self.client.get(f"/api/orders/{order_id}")
        self.assertEqual(detail_res.status_code, 200)
        self.assertIn("whatsapp_url", detail_res.json())
        self.assertIn("image_url", detail_res.json())
        print(f"[OK] WhatsApp photo invoice link and image endpoint verified: {wa_json['image_url'][:60]}...")

    def test_11_order_specific_product_rate_change(self):
        # Base product rate is 500.0
        self.assertEqual(float(self.product.loose_price), 500.0)

        # 1. Test price_cart with order-specific custom unit_price (e.g. Rs. 600.0 instead of Rs. 500.0)
        custom_rate = 600.0
        price_payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2, "unit_price": custom_rate}],
            "gst_enabled": False
        }
        res = self.client.post("/api/cart/price", data=price_payload, content_type="application/json")
        self.assertEqual(res.status_code, 200)
        p_data = res.json()
        self.assertEqual(p_data["subtotal"], 1200.0)
        line = p_data["lines"][0]
        self.assertEqual(line["unit_rate"], custom_rate)
        self.assertEqual(line["standard_rate"], 500.0)
        self.assertTrue(line["is_custom_rate"])

        # 2. Submit order with order-specific custom rate (Rs. 600.0)
        submit_payload = {
            "customer_id": self.customer.id,
            "items": [{"product_id": self.product.id, "quantity": 2, "unit_price": custom_rate}],
            "gst_enabled": False,
            "packing_charge": 0.0,
            "discount_amount": 0.0
        }
        submit_res = self.client.post("/api/cart/submit", data=submit_payload, content_type="application/json")
        self.assertEqual(submit_res.status_code, 200)
        order_id = submit_res.json()["order_id"]

        order = Order.objects.get(id=order_id)
        self.assertEqual(float(order.subtotal), 1200.0)
        self.assertEqual(float(order.items.first().unit_price), 600.0)

        # Verify that catalog product rate was NOT altered in general
        self.product.refresh_from_db()
        self.assertEqual(float(self.product.loose_price), 500.0)
        print("[OK] Order submitted with order-specific rate Rs. 600.0. Product general rate untouched at Rs. 500.0.")

        # 3. Edit order specifically to change rate to Rs. 400.0 for this order
        new_specific_rate = 400.0
        edit_payload = {
            "items": [{"product_id": self.product.id, "quantity": 2, "unit_price": new_specific_rate}]
        }
        edit_res = self.client.post(f"/api/orders/{order_id}/edit", data=edit_payload, content_type="application/json")
        self.assertEqual(edit_res.status_code, 200)

        order.refresh_from_db()
        self.assertEqual(float(order.subtotal), 800.0)
        self.assertEqual(float(order.items.first().unit_price), 400.0)
        self.product.refresh_from_db()
        self.assertEqual(float(self.product.loose_price), 500.0)
        print("[OK] Order edited with new rate Rs. 400.0 specifically. Product general rate remains Rs. 500.0.")

        # 4. Test agent tools tool_create_order and tool_edit_order support order-specific rates
        from backend.agent.tools import tool_create_order, tool_edit_order
        agent_order_res = tool_create_order(
            customer_identifier=self.customer.phone,
            items=[{"product_sku": self.product.sku, "quantity": 3, "unit_price": 750.0}]
        )
        self.assertEqual(agent_order_res["status"], "success")
        agent_order = Order.objects.get(voucher_no=agent_order_res["voucher_no"])
        self.assertEqual(float(agent_order.items.first().unit_price), 750.0)
        self.assertEqual(float(agent_order.subtotal), 2250.0)

        # Edit order via agent tool with order-specific rate Rs. 350.0
        edit_agent_res = tool_edit_order(
            order_identifier=agent_order.voucher_no,
            items=[{"product_sku": self.product.sku, "quantity": 3, "unit_price": 350.0}]
        )
        self.assertEqual(edit_agent_res["status"], "success")
        agent_order.refresh_from_db()
        self.assertEqual(float(agent_order.items.first().unit_price), 350.0)
        self.assertEqual(float(agent_order.subtotal), 1050.0)
        print("[OK] Agent tools create_order & tool_edit_order verified with order-specific rate changes.")

if __name__ == "__main__":
    unittest.main()



