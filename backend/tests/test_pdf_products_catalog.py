import os
import sys
import tempfile
from decimal import Decimal
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.core.models import Product, Customer
from apps.api.api import cart_init
from backend.agent.tools import tool_search_products, tool_create_product

class PdfProductsCatalogTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Test Wholesaler Client",
            phone="+91-9988776655",
            city="Jaipur",
            state_code="08"
        )
        self.prod = Product.objects.create(
            name="002 BN COL SCISSOR",
            sku="002-BN-COL-SCISSOR-002",
            group_alias="CUTLERY",
            category_alias="SCI",
            category="CUTLERY",
            opening_qty=Decimal("85.000"),
            closing_qty=Decimal("107.000"),
            base_price=Decimal("180.00"),
            loose_price=Decimal("180.00"),
            full_carton_price=Decimal("4104.00"),
            full_carton_quantity=24,
            gst_rate=Decimal("18.00"),
            image_url="https://images.unsplash.com/photo-1593618998160-e34014e67546",
            is_active=True
        )

    def test_product_fields_and_photo_property(self):
        """Verify group_alias, category_alias, quantities, and photo_url."""
        self.assertEqual(self.prod.group_alias, "CUTLERY")
        self.assertEqual(self.prod.category_alias, "SCI")
        self.assertEqual(self.prod.opening_qty, Decimal("85.000"))
        self.assertEqual(self.prod.closing_qty, Decimal("107.000"))
        self.assertTrue(self.prod.photo_url.startswith("https://images.unsplash.com"))

        # Test photo upload override
        small_gif = (
            b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\x05\x04\x04'
            b'\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44'
            b'\x01\x00\x3b'
        )
        uploaded = SimpleUploadedFile("sample_scissor.gif", small_gif, content_type="image/gif")
        self.prod.photo = uploaded
        self.prod.save()

        self.assertIn("products/sample_scissor", self.prod.photo_url)

    def test_cart_init_includes_new_pdf_fields(self):
        """Ensure /api/cart/init exposes group_alias, category_alias, opening_qty, closing_qty, and photo_url."""
        from django.test import RequestFactory
        req = RequestFactory().get(f"/api/cart/init?customer_id={self.customer.id}")
        data = cart_init(req, self.customer.id)

        item = next((p for p in data["catalog"] if p["id"] == self.prod.id), None)
        self.assertIsNotNone(item)
        self.assertEqual(item["group_alias"], "CUTLERY")
        self.assertEqual(item["category_alias"], "SCI")
        self.assertEqual(item["opening_qty"], 85.0)
        self.assertEqual(item["closing_qty"], 107.0)
        self.assertIn("CUTLERY", data["groups"])
        self.assertIn("SCI", data["category_aliases"])

    def test_agent_tool_search_by_group_and_category_alias(self):
        """Ensure agent search tool can find products by group alias or category alias."""
        res_by_group = tool_search_products(query="002 BN", group="CUTLERY")
        self.assertTrue(any(p["id"] == self.prod.id for p in res_by_group["products"]))

        res_by_cat = tool_search_products(query="002 BN", category="SCI")
        self.assertTrue(any(p["id"] == self.prod.id for p in res_by_cat["products"]))

        res_by_name = tool_search_products(query="002 BN COL SCISSOR")
        self.assertTrue(any(p["id"] == self.prod.id for p in res_by_name["products"]))
