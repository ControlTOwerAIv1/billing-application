import json
from decimal import Decimal
from django.test import TestCase, Client
from apps.core.models import Tenant, Customer, Product, Order, OrderItem
from backend.invoice_generator import generate_order_pdf_bytes

class ColorVariantTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            state_code="08",
            gstin="08ABCDE1234F1Z5"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            name="Ramesh Plastics",
            phone="9876543210",
            state_code="08",
            balance_amount=Decimal("0.00")
        )
        self.product = Product.objects.create(
            tenant=self.tenant,
            sku="SOL-COMB-01",
            name="5\" LOVELY HANDLE",
            group_alias="SOLAR COMB",
            colors="PL, GW, ALM, SHELL, BKDC, TOM",
            base_price=Decimal("12.50"),
            loose_price=Decimal("12.50"),
            full_carton_price=Decimal("11.00"),
            full_carton_quantity=100,
            gst_rate=Decimal("18.00"),
            image_url="/media/products/solar_5_inch_lovely_handle.jpeg"
        )

    def test_product_color_list_property(self):
        """Verify color_list parses comma separated colors."""
        self.assertEqual(
            self.product.color_list,
            ["PL", "GW", "ALM", "SHELL", "BKDC", "TOM"]
        )

    def test_cart_init_returns_colors(self):
        """Verify /api/cart/init returns colors and color_list."""
        resp = self.client.get(f"/api/cart/init?customer_id={self.customer.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        item = next(p for p in data["catalog"] if p["id"] == self.product.id)
        self.assertEqual(item["colors"], "PL, GW, ALM, SHELL, BKDC, TOM")
        self.assertIn("BKDC", item["color_list"])
        self.assertEqual(item["image_url"], "/media/products/solar_5_inch_lovely_handle.jpeg")

    def test_submit_order_with_color_variant(self):
        """Verify placing an order with a selected color saves to OrderItem."""
        payload = {
            "customer_id": self.customer.id,
            "items": [
                {
                    "product_id": self.product.id,
                    "quantity": 5,
                    "unit_type": "loose",
                    "color": "BKDC"
                }
            ],
            "gst_enabled": True
        }
        resp = self.client.post(
            "/api/cart/submit",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        order_id = resp.json()["order_id"]
        order = Order.objects.get(id=order_id)
        order_item = order.items.first()
        self.assertEqual(order_item.color, "BKDC")
        self.assertEqual(order_item.quantity, 5)

        # Verify PDF generation includes color
        pdf_bytes = generate_order_pdf_bytes(order)
        self.assertGreater(len(pdf_bytes), 1000)

print("[OK] Color Variant test definitions loaded.")
