import os
from pathlib import Path
from django.test import TestCase, Client
from apps.core.models import Product, Customer, Tenant

class CatalogImagesTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Solar Combs Ltd")
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            name="Apex Retailers",
            phone="9876543210",
            city="Mumbai",
            state_code="27",
            status="active",
            balance_amount=50000.00
        )
        self.product = Product.objects.create(
            tenant=self.tenant,
            sku="SOLAR-WESTON-4-TEST",
            name="WESTON 4\" SPECIAL",
            group_alias="SOLAR COMB",
            photo="products/solar_weston_4_inch_composite.png",
            image_url="/media/products/solar_weston_4_inch_composite.png",
            gallery_images=[
                "/media/products/solar_weston_4_inch_composite.png",
                "/media/products/solar_4in_weston_opec_1.png",
                "/media/products/solar_4in_weston_opec_2.png"
            ],
            color_images={
                "PL": "/media/products/solar_4in_weston_opec_1.png",
                "GW": "/media/products/solar_4in_weston_opec_2.png"
            },
            colors="PL, GW, ALM, ICE",
            base_price=25.00,
            loose_price=25.00,
            full_carton_price=1200.00,
            full_carton_quantity=50
        )

    def test_product_model_images_properties(self):
        self.assertEqual(self.product.photo_url, "/media/products/solar_weston_4_inch_composite.png")
        self.assertEqual(len(self.product.all_images), 3)
        self.assertIn("/media/products/solar_4in_weston_opec_1.png", self.product.all_images)
        self.assertEqual(self.product.color_images["PL"], "/media/products/solar_4in_weston_opec_1.png")

    def test_cart_init_api_returns_all_image_fields(self):
        resp = self.client.get(f"/api/cart/init?customer_id={self.customer.id}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("catalog", data)
        item = next((p for p in data["catalog"] if p["id"] == self.product.id), None)
        self.assertIsNotNone(item)
        self.assertEqual(item["photo_url"], "/media/products/solar_weston_4_inch_composite.png")
        self.assertEqual(len(item["gallery_images"]), 3)
        self.assertIn("PL", item["color_images"])
        self.assertEqual(item["color_images"]["PL"], "/media/products/solar_4in_weston_opec_1.png")
        self.assertEqual(len(item["all_images"]), 3)

    def test_image_files_exist_on_disk(self):
        from django.conf import settings
        media_products = Path(settings.MEDIA_ROOT) / "products"
        self.assertTrue(media_products.exists())
        # Check that composite images and sample brochure images exist
        self.assertTrue((media_products / "solar_weston_4_inch_composite.png").exists())
        self.assertTrue((media_products / "solar_077_red_gold_1.png").exists())
        self.assertTrue((media_products / "solar_c4_opec_composite.png").exists())
