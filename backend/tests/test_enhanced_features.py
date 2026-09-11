from decimal import Decimal
from django.test import TestCase
from apps.core.models import Customer, Product, Order, OrderItem, CustomerStatus, OrderStatus
from backend.agent.tools import (
    tool_create_customer, tool_search_customers, resolve_single_customer,
    tool_create_product, tool_create_order, tool_edit_order, tool_record_payment
)

class EnhancedFeaturesTests(TestCase):
    def setUp(self):
        # Create two customers with the exact same name in different cities
        self.cust_kolkata = Customer.objects.create(
            name="Raj Wholesalers",
            phone="+91-9876543210",
            city="Kolkata",
            state_code="19",
            business_name="Raj Wholesalers Bengal Pvt Ltd",
            credit_limit=Decimal("50000.00"),
            balance_amount=Decimal("0.00"),
            status=CustomerStatus.APPROVED
        )

        self.cust_jaipur = Customer.objects.create(
            name="Raj Wholesalers",
            phone="+91-9123456780",
            city="Jaipur",
            state_code="08",
            business_name="Raj Wholesalers Rajasthan Trading",
            credit_limit=Decimal("75000.00"),
            balance_amount=Decimal("1500.00"),
            status=CustomerStatus.APPROVED
        )

        # Create products with photos & multi-tier pricing
        self.prod_a4 = Product.objects.create(
            sku="STAT-A4-500",
            name="A4 Paper Copier 75GSM",
            category="Stationery",
            image_url="https://images.unsplash.com/photo-1586075010923-2dd4570fb338?w=500",
            base_price=Decimal("1000.00"),
            loose_price=Decimal("1000.00"),
            full_carton_price=Decimal("4800.00"),
            half_carton_price=Decimal("2500.00"),
            full_carton_quantity=5,
            gst_rate=Decimal("18.00")
        )

        self.prod_pen = Product.objects.create(
            sku="STAT-PEN-BLU",
            name="Ballpoint Pens Blue Box",
            category="Stationery",
            image_url="https://images.unsplash.com/photo-1583485088034-697b5bc54ccd?w=500",
            base_price=Decimal("200.00"),
            loose_price=Decimal("200.00"),
            full_carton_price=Decimal("1800.00"),
            half_carton_price=Decimal("950.00"),
            full_carton_quantity=10,
            gst_rate=Decimal("12.00")
        )

    def test_customer_search_filters_and_locations(self):
        """Test customer search filters by city, state, and balance status."""
        # Filter by City
        res_kol = tool_search_customers(city="Kolkata")
        self.assertEqual(res_kol["count"], 1)
        self.assertEqual(res_kol["customers"][0]["city"], "Kolkata")
        self.assertIn("Kolkata", res_kol["customers"][0]["location"])

        # Filter by State
        res_rj = tool_search_customers(state_code="08")
        self.assertEqual(res_rj["count"], 1)
        self.assertEqual(res_rj["customers"][0]["city"], "Jaipur")

        # Filter by Outstanding Balance
        res_bal = tool_search_customers(has_balance_due=True)
        self.assertEqual(res_bal["count"], 1)
        self.assertEqual(res_bal["customers"][0]["id"], self.cust_jaipur.id)

    def test_customer_disambiguation_when_names_match(self):
        """Test that resolve_single_customer triggers disambiguation when multiple customers share the name."""
        cust, err = resolve_single_customer("Raj Wholesalers")
        self.assertIsNone(cust)
        self.assertIsNotNone(err)
        self.assertEqual(err["status"], "disambiguation_required")
        self.assertEqual(len(err["matches"]), 2)
        # Check that location details are provided in disambiguation
        cities = [m["city"] for m in err["matches"]]
        self.assertIn("Kolkata", cities)
        self.assertIn("Jaipur", cities)

        # Resolving with unique phone or ID should succeed without ambiguity
        cust_by_phone, err2 = resolve_single_customer("+91-9876543210")
        self.assertIsNone(err2)
        self.assertEqual(cust_by_phone.id, self.cust_kolkata.id)

    def test_product_creation_requires_all_fields_including_photo(self):
        """Test strict validation on product onboarding (missing fields rejected)."""
        # Missing image_url / photo
        res_no_img = tool_create_product(
            sku="TEST-SKU-01",
            name="Test Product Without Image",
            category="Stationery",
            image_url="",
            base_price=100.0,
            full_carton_price=800.0,
            full_carton_quantity=10
        )
        self.assertEqual(res_no_img["status"], "missing_required_fields")
        self.assertTrue(any("image_url" in f for f in res_no_img["missing_fields"]))

        # Missing full_carton_price
        res_no_carton = tool_create_product(
            sku="TEST-SKU-02",
            name="Test Product Without Carton Price",
            category="Stationery",
            image_url="http://example.com/img.jpg",
            base_price=100.0,
            full_carton_price=0.0,
            full_carton_quantity=10
        )
        self.assertEqual(res_no_carton["status"], "missing_required_fields")

        # Valid product creation with photo
        res_valid = tool_create_product(
            sku="TEST-SKU-OK",
            name="Complete Test Product",
            category="Packaging",
            image_url="http://example.com/photo.jpg",
            base_price=150.0,
            full_carton_price=1200.0,
            full_carton_quantity=10,
            gst_rate=18.0
        )
        self.assertEqual(res_valid["status"], "success")
        self.assertEqual(res_valid["product"]["sku"], "TEST-SKU-OK")
        self.assertEqual(res_valid["product"]["image_url"], "http://example.com/photo.jpg")

    def test_order_creation_and_edit_flow(self):
        """Test creating an order and subsequent editing of items, status, and balance recalculation."""
        # 1. Create order for Jaipur customer (Intra-state RJ -> 08)
        create_res = tool_create_order(
            customer_identifier=str(self.cust_jaipur.id),
            items=[{"product": self.prod_a4.sku, "quantity": 2, "unit_type": "loose"}]
        )
        self.assertEqual(create_res["status"], "success")
        voucher_no = create_res["voucher_no"]
        # Subtotal: 2 * 1000 = 2000. 18% GST (CGST 9% + SGST 9%) = 360. Total = 2360.
        self.assertEqual(create_res["subtotal"], 2000.0)
        self.assertEqual(create_res["total_amount"], 2360.0)

        # Check customer balance updated
        self.cust_jaipur.refresh_from_db()
        self.assertEqual(self.cust_jaipur.balance_amount, Decimal("1500.00") + Decimal("2360.00"))

        # 2. Edit order: change quantity to 1 of A4 paper and add 5 Pens, change status to 'packed'
        edit_res = tool_edit_order(
            order_identifier=voucher_no,
            status="packed",
            items=[
                {"product": self.prod_a4.sku, "quantity": 1, "unit_type": "loose"},
                {"product": self.prod_pen.sku, "quantity": 5, "unit_type": "loose"}
            ]
        )
        self.assertEqual(edit_res["status"], "success")
        self.assertEqual(edit_res["order_status"], "packed")
        # Subtotal: (1 * 1000) + (5 * 200) = 2000.
        # A4 GST (18% of 1000 = 180), Pen GST (12% of 1000 = 120) => Total Tax = 300.
        # New Grand Total = 2300.00.
        self.assertEqual(edit_res["subtotal"], 2000.0)
        self.assertEqual(edit_res["total_amount"], 2300.0)

        # 3. Check customer balance adjusted by diff (2300 - 2360 = -60)
        self.cust_jaipur.refresh_from_db()
        self.assertEqual(self.cust_jaipur.balance_amount, Decimal("1500.00") + Decimal("2300.00"))
