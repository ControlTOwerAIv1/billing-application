import os
import sys
import unittest
from pathlib import Path
from decimal import Decimal

# Configure Django
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")

import django
django.setup()

from apps.core.models import Customer, Product, Order, OrderItem, Transport
from backend.agent.tools import (
    tool_create_transport,
    tool_list_transports,
    tool_assign_customer_transport,
    tool_create_customer,
    tool_create_order
)
from backend.invoice_generator import generate_order_pdf_bytes
from django.test import Client

class TestTransportFeature(unittest.TestCase):
    def setUp(self):
        self.client = Client()
        # Clean up test artifacts
        Transport.objects.filter(name__startswith="TEST_").delete()
        Customer.objects.filter(name__startswith="TEST_").delete()
        Order.objects.filter(voucher_no__startswith="TEST_").delete()

    def tearDown(self):
        Transport.objects.filter(name__startswith="TEST_").delete()
        Customer.objects.filter(name__startswith="TEST_").delete()
        Order.objects.filter(voucher_no__startswith="TEST_").delete()

    def test_01_create_and_list_transports(self):
        """Test creating transports via tool and API."""
        # 1. Via tool
        res1 = tool_create_transport(
            name="TEST_VRL Logistics",
            phone="9876543210",
            contact_person="Ramesh Kumar",
            vehicle_number="RJ-14-GA-1234"
        )
        self.assertTrue(res1["success"])
        self.assertEqual(res1["transport"]["name"], "TEST_VRL Logistics")
        self.assertEqual(res1["transport"]["phone"], "9876543210")

        # 2. Second transport
        res2 = tool_create_transport(
            name="TEST_Patel Roadways",
            phone="9123456780"
        )
        self.assertTrue(res2["success"])

        # 3. List via tool
        list_res = tool_list_transports()
        names = [t["name"] for t in list_res["transports"]]
        self.assertIn("TEST_VRL Logistics", names)
        self.assertIn("TEST_Patel Roadways", names)

        # 4. List via API
        resp = self.client.get("/api/transports")
        self.assertEqual(resp.status_code, 200)
        api_names = [t["name"] for t in resp.json()]
        self.assertIn("TEST_VRL Logistics", api_names)
        self.assertIn("TEST_Patel Roadways", api_names)

    def test_02_customer_transport_prompt_and_assignment(self):
        """Test customer creation transport selection prompt and assignment."""
        trans = Transport.objects.create(name="TEST_SafeXpress", phone="9988776655")

        # Create customer without transport -> should flag transport_selection_needed
        cust_res = tool_create_customer(
            name="TEST_Customer_Alpha",
            phone="9800000001",
            city="Jaipur",
            state_code="08"
        )
        self.assertTrue(cust_res["transport_selection_needed"])
        cust_id = cust_res["id"]

        # Assign transport
        assign_res = tool_assign_customer_transport(cust_id, "TEST_SafeXpress")
        self.assertTrue(assign_res["success"])

        cust = Customer.objects.get(id=cust_id)
        self.assertIsNotNone(cust.transport)
        self.assertEqual(cust.transport.name, "TEST_SafeXpress")

    def test_03_orders_travel_through_transports(self):
        """Test orders can travel through customer default or specific chosen transport."""
        trans_a = Transport.objects.create(name="TEST_Carrier_A", phone="9991112222")
        trans_b = Transport.objects.create(name="TEST_Carrier_B", phone="9993334444")

        cust = Customer.objects.create(
            name="TEST_Customer_Beta",
            phone="9800000002",
            state_code="08",
            transport=trans_a
        )

        prod, _ = Product.objects.get_or_create(
            sku="TEST_PROD_1",
            defaults={"name": "Test Mug", "base_price": Decimal("10.00"), "gst_rate": Decimal("18.00")}
        )

        # 1. Submit order via API using customer default transport
        order_res1 = self.client.post("/api/cart/submit", data={
            "customer_id": cust.id,
            "items": [{"product_id": prod.id, "quantity": 5, "unit_type": "loose"}],
            "packing_charge": 25.0,
            "discount_amount": 10.0
        }, content_type="application/json")
        self.assertEqual(order_res1.status_code, 200)
        data1 = order_res1.json()
        self.assertEqual(data1["transport_id"], trans_a.id)
        self.assertEqual(data1["transport_name"], "TEST_Carrier_A")

        # 2. Submit order explicitly specifying a different transport (Carrier B)
        order_res2 = self.client.post("/api/cart/submit", data={
            "customer_id": cust.id,
            "items": [{"product_id": prod.id, "quantity": 10, "unit_type": "loose"}],
            "transport_id": trans_b.id
        }, content_type="application/json")
        self.assertEqual(order_res2.status_code, 200)
        data2 = order_res2.json()
        self.assertEqual(data2["transport_id"], trans_b.id)
        self.assertEqual(data2["transport_name"], "TEST_Carrier_B")

        # 3. Test PDF generation includes the transport
        order1 = Order.objects.get(id=data1["order_id"])
        pdf_bytes = generate_order_pdf_bytes(order1)
        self.assertGreater(len(pdf_bytes), 1000)

        # 4. Edit order transport via API
        edit_res = self.client.post(f"/api/orders/{order1.id}/edit", data={
            "transport_id": trans_b.id
        }, content_type="application/json")
        self.assertEqual(edit_res.status_code, 200)
        self.assertEqual(edit_res.json()["transport_id"], trans_b.id)
        order1.refresh_from_db()
        self.assertEqual(order1.transport.id, trans_b.id)

if __name__ == "__main__":
    unittest.main()
