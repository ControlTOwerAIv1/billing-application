import io
from decimal import Decimal
from django.test import TestCase
from apps.core.models import Tenant, Customer, Product, Order, OrderItem
from backend.invoice_generator import generate_order_pdf_bytes
import pymupdf

class EstimatePDFFormatTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Hindustan Plast Tenant",
            state_code="08",
            gstin="08ABCDE1234F1Z5"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            name="Sharma Plastic Stores",
            business_name="Sharma Plastics",
            phone="9876543210",
            state_code="08"
        )
        self.product1 = Product.objects.create(
            tenant=self.tenant,
            sku="SOL-COMB-01",
            name="5\" LOVELY HANDLE",
            category="Hair Combs",
            colors="PL, GW, ALM, SHELL, BKDC, TOM",
            base_price=Decimal("12.50"),
            loose_price=Decimal("12.50")
        )
        self.product2 = Product.objects.create(
            tenant=self.tenant,
            sku="SCISSOR-002",
            name="002 DEX BLACK SCISSOR",
            category="Scissors",
            colors="Black",
            base_price=Decimal("45.00"),
            loose_price=Decimal("45.00")
        )

    def test_estimate_pdf_with_product_colors(self):
        """Verify non-GST order produces ESTIMATE PDF with product names and color breakdown."""
        order = Order.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            voucher_no="EST-2026-001",
            status="placed",
            gst_enabled=False
        )
        # Add multiple color variants for Product 1
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            color="red",
            quantity=2,
            unit_price=Decimal("12.50"),
            taxable_amount=Decimal("25.00"),
            total_amount=Decimal("25.00")
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            color="blue",
            quantity=2,
            unit_price=Decimal("12.50"),
            taxable_amount=Decimal("25.00"),
            total_amount=Decimal("25.00")
        )
        OrderItem.objects.create(
            order=order,
            product=self.product1,
            color="green",
            quantity=3,
            unit_price=Decimal("12.50"),
            taxable_amount=Decimal("37.50"),
            total_amount=Decimal("37.50")
        )
        # Add single color for Product 2
        OrderItem.objects.create(
            order=order,
            product=self.product2,
            color="Black",
            quantity=5,
            unit_price=Decimal("45.00"),
            taxable_amount=Decimal("225.00"),
            total_amount=Decimal("225.00")
        )
        # Add carton item
        OrderItem.objects.create(
            order=order,
            product=self.product2,
            color="Standard",
            quantity=2,
            unit_type="carton",
            unit_price=Decimal("102.00"),
            taxable_amount=Decimal("204.00"),
            total_amount=Decimal("204.00")
        )
        order.calculate_taxes_and_totals(tenant_state_code="08")

        pdf_bytes = generate_order_pdf_bytes(order)
        self.assertIsNotNone(pdf_bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

        # Extract text using PyMuPDF
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        self.assertGreater(len(doc), 0)
        full_text = "\n".join(page.get_text() for page in doc)

        # Verify title is ESTIMATE instead of INVOICE / BILL or TAX INVOICE
        self.assertIn("ESTIMATE", full_text)
        self.assertNotIn("INVOICE / BILL", full_text)
        self.assertNotIn("TAX INVOICE", full_text)
        self.assertNotIn("Payment:", full_text)

        # Verify product names appear and category names do not appear in the table
        self.assertIn('5" LOVELY HANDLE', full_text)
        self.assertIn("002 DEX BLACK SCISSOR", full_text)
        self.assertNotIn("Hair Combs", full_text)
        self.assertNotIn("Scissors", full_text)

        # Verify color details in single line
        self.assertIn("Color: red-2, blue-2, green-3", full_text)

        # Verify Qty, Rate, and Amount column headers and values
        self.assertIn("Qty", full_text)
        self.assertIn("Rate (Rs.)", full_text)
        self.assertIn("Amount (Rs.)", full_text)
        # Product 1 qty: 7
        self.assertIn("7", full_text)
        # Product 2 carton qty display: "ctn"
        self.assertIn("ctn", full_text)

        print("\n[OK] Estimate PDF format verified successfully with extracted text!")

if __name__ == "__main__":
    import unittest
    unittest.main()
