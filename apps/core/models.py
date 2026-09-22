from django.db import models
from decimal import Decimal

class SoftDeleteManager(models.Manager):
    """Custom manager that excludes soft_deleted = 1 records by default."""
    def get_queryset(self):
        return super().get_queryset().filter(soft_deleted=0)

    def all_with_deleted(self):
        return super().get_queryset()

class SoftDeleteModel(models.Model):
    """Abstract model providing soft-delete support across all tables."""
    soft_deleted = models.IntegerField(default=0, help_text="0 = Active, 1 = Soft Deleted")

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    def delete(self, using=None, keep_parents=False):
        """Soft delete interceptor."""
        self.soft_deleted = 1
        self.save()

    class Meta:
        abstract = True

class Tenant(SoftDeleteModel):
    name = models.CharField(max_length=150)
    gstin = models.CharField(max_length=15, blank=True, null=True)
    state_code = models.CharField(max_length=2, default="08", help_text="e.g. 08 for RJ, 27 for MH, 19 for WB")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class Transport(SoftDeleteModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True, related_name="transports")
    name = models.CharField(max_length=150, unique=True, help_text="Transport or Logistics Agency Name")
    phone = models.CharField(max_length=30, blank=True, null=True, help_text="Contact Phone / Mobile")
    contact_person = models.CharField(max_length=100, blank=True, null=True, help_text="Booking Agent / Driver / Manager")
    vehicle_number = models.CharField(max_length=50, blank=True, null=True, help_text="Vehicle / Truck / Lorry No.")
    destination_notes = models.CharField(max_length=200, blank=True, null=True, help_text="Routes covered / Hub locations")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        detail = f" ({self.phone})" if self.phone else ""
        return f"{self.name}{detail}"

class CustomerStatus(models.TextChoices):
    PENDING = "pending", "Pending Approval"
    APPROVED = "approved", "Approved"
    BLOCKED = "blocked", "Blocked"

class Customer(SoftDeleteModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="customers", null=True, blank=True)
    transport = models.ForeignKey(Transport, on_delete=models.SET_NULL, null=True, blank=True, related_name="customers", help_text="Default preferred transport for shipping")
    phone = models.CharField(max_length=20, db_index=True)
    name = models.CharField(max_length=150)
    business_name = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True, default="")
    state_code = models.CharField(max_length=2, default="08")
    gstin = models.CharField(max_length=15, blank=True, null=True)
    pan = models.CharField(max_length=10, blank=True, null=True)
    credit_limit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    balance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=20, choices=CustomerStatus.choices, default=CustomerStatus.APPROVED)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        loc = f" ({self.city}, {self.state_code})" if self.city else f" ({self.state_code})"
        return f"{self.name}{loc} - {self.phone}"

class Product(SoftDeleteModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="products", null=True, blank=True)
    sku = models.CharField(max_length=100, db_index=True)
    name = models.CharField(max_length=250)
    group_alias = models.CharField(max_length=150, blank=True, default="", db_index=True, help_text="Group Alias e.g. CUTLERY, SOLAR COMB")
    category_alias = models.CharField(max_length=150, blank=True, default="", db_index=True, help_text="Category Alias e.g. SCI, NAILCUTTER")
    category = models.CharField(max_length=150, default="General")
    photo = models.ImageField(upload_to="products/", blank=True, null=True, help_text="Uploaded product photo")
    image_url = models.CharField(max_length=1000, blank=True, null=True, default="")
    opening_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"), help_text="Opening Quantity")
    closing_qty = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"), help_text="Closing Quantity / Current Stock")
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    
    # Multi-tier Pricing
    full_carton_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    half_carton_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    loose_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    full_carton_quantity = models.IntegerField(default=1, help_text="Number of loose pieces in a full carton")
    
    stuffed_full_carton_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    stuffed_loose_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    hsn_code = models.CharField(max_length=10, default="3926")
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"))
    is_active = models.BooleanField(default=True)

    @property
    def photo_url(self) -> str:
        if self.photo:
            try:
                return self.photo.url
            except Exception:
                pass
        return self.image_url or ""

    def get_price(self, tier: str = "loose") -> Decimal:
        tier_lower = tier.lower()
        if tier_lower in ["full_carton", "full carton", "carton"]:
            return self.full_carton_price or (self.base_price * Decimal(self.full_carton_quantity))
        elif tier_lower in ["half_carton", "half carton"]:
            return self.half_carton_price or (self.base_price * Decimal(self.full_carton_quantity // 2))
        elif tier_lower == "stuffed_full_carton":
            return self.stuffed_full_carton_price or self.full_carton_price
        elif tier_lower == "stuffed_loose":
            return self.stuffed_loose_price or self.loose_price
        return self.loose_price or self.base_price

    def __str__(self):
        return f"{self.sku} - {self.name}"

class Warehouse(SoftDeleteModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="warehouses", null=True, blank=True)
    name = models.CharField(max_length=150)
    location = models.CharField(max_length=200, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

class WarehouseProduct(SoftDeleteModel):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name="stocks")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="warehouse_stocks")
    quantity = models.IntegerField(default=0)

    class Meta:
        unique_together = ("warehouse", "product")

class OrderStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PLACED = "placed", "Placed"
    PACKED = "packed", "Packed"
    DISPATCHED = "dispatched", "Dispatched"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"

class PaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PARTIAL = "partial", "Partially Paid"
    PAID = "paid", "Fully Paid"

class OrderType(models.TextChoices):
    SALES = "sales", "Sales Order"
    ADVANCE_PURCHASE = "advance_purchase", "Advance Purchase Order"

class Order(SoftDeleteModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    transport = models.ForeignKey(Transport, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders", help_text="Assigned transport carrier for this order shipment")
    voucher_no = models.CharField(max_length=50, unique=True)
    order_type = models.CharField(max_length=30, choices=OrderType.choices, default=OrderType.SALES)
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PLACED)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    packing_charge = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    gst_enabled = models.BooleanField(default=True, help_text="Whether GST is applied and shown on the PDF invoice")
    custom_gst_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Custom GST rate percentage applied to the order")
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def calculate_taxes_and_totals(self, tenant_state_code: str = "08"):
        items = self.items.all()
        subtotal = Decimal("0.00")
        cgst_total = Decimal("0.00")
        sgst_total = Decimal("0.00")
        igst_total = Decimal("0.00")

        is_intra_state = (self.customer.state_code == tenant_state_code)

        has_zero_rate = (self.custom_gst_rate is not None and self.custom_gst_rate <= Decimal("0.00"))
        if not self.gst_enabled or has_zero_rate:
            self.gst_enabled = False

        for item in items:
            subtotal += item.taxable_amount
            if not self.gst_enabled:
                item.cgst_amount = Decimal("0.00")
                item.sgst_amount = Decimal("0.00")
                item.igst_amount = Decimal("0.00")
            else:
                effective_rate = self.custom_gst_rate if self.custom_gst_rate is not None else item.gst_rate
                if is_intra_state:
                    half_rate = effective_rate / Decimal("2.0")
                    item.cgst_amount = (item.taxable_amount * half_rate / Decimal("100.0")).quantize(Decimal("0.01"))
                    item.sgst_amount = (item.taxable_amount * half_rate / Decimal("100.0")).quantize(Decimal("0.01"))
                    item.igst_amount = Decimal("0.00")
                else:
                    item.cgst_amount = Decimal("0.00")
                    item.sgst_amount = Decimal("0.00")
                    item.igst_amount = (item.taxable_amount * effective_rate / Decimal("100.0")).quantize(Decimal("0.01"))

            item.total_amount = item.taxable_amount + item.cgst_amount + item.sgst_amount + item.igst_amount
            item.save()

            cgst_total += item.cgst_amount
            sgst_total += item.sgst_amount
            igst_total += item.igst_amount

        self.subtotal = subtotal
        self.cgst_amount = cgst_total
        self.sgst_amount = sgst_total
        self.igst_amount = igst_total
        packing = self.packing_charge or Decimal("0.00")
        discount = self.discount_amount or Decimal("0.00")
        calc_total = subtotal + cgst_total + sgst_total + igst_total + packing - discount
        self.total_amount = max(Decimal("0.00"), calc_total)
        self.save()

    def __str__(self):
        return f"{self.voucher_no} - {self.customer.name}"

class OrderItem(SoftDeleteModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="order_items")
    unit_type = models.CharField(max_length=20, default="loose", help_text="loose, half_carton, full_carton, stuffed")
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("18.00"))
    cgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    sgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    igst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

class PurchaseOrder(SoftDeleteModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    supplier_name = models.CharField(max_length=150)
    po_number = models.CharField(max_length=50, unique=True)
    status = models.CharField(max_length=20, default="placed", help_text="placed, received, cancelled")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

class PoItem(SoftDeleteModel):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    import_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

class AccountGroup(models.TextChoices):
    DEBTORS = "debtors", "Sundry Debtors (Customers)"
    CREDITORS = "creditors", "Sundry Creditors (Suppliers)"
    CASH = "cash", "Cash Account"
    BANK = "bank", "Bank Account"
    REVENUE = "revenue", "Sales Revenue"

class Account(SoftDeleteModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=150)
    account_group = models.CharField(max_length=30, choices=AccountGroup.choices, default=AccountGroup.DEBTORS)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name="accounts")
    balance_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return f"{self.name} ({self.account_group})"

class EntryType(models.TextChoices):
    DEBIT = "debit", "Debit"
    CREDIT = "credit", "Credit"

class Ledger(SoftDeleteModel):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, null=True, blank=True)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="ledger_entries")
    against_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="counter_entries")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    entry_type = models.CharField(max_length=10, choices=EntryType.choices)
    voucher_number = models.CharField(max_length=50, blank=True, null=True)
    narration = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
