from ninja import NinjaAPI, Schema
from typing import List, Optional
from decimal import Decimal
from django.shortcuts import get_object_or_404
from apps.core.models import Customer, Product, Order

api = NinjaAPI(title="OrderBot Django API", version="1.0.0")

class CustomerSchema(Schema):
    id: int
    name: str
    phone: str
    state_code: str
    balance_amount: float
    status: str

class CreateCustomerSchema(Schema):
    name: str
    phone: str
    state_code: Optional[str] = "08"

class CartItemInput(Schema):
    product_id: int
    quantity: int

class PriceCartInput(Schema):
    customer_id: int
    items: List[CartItemInput]

class SubmitOrderInput(Schema):
    customer_id: int
    items: List[CartItemInput]
    notes: Optional[str] = None

@api.get("/customers", response=List[CustomerSchema])
def list_customers(request):
    """Returns active customers (soft_deleted=0)."""
    return list(Customer.objects.all().values())

@api.post("/customers", response=CustomerSchema)
def create_customer(request, payload: CreateCustomerSchema):
    """Creates a new customer."""
    customer = Customer.objects.create(
        name=payload.name,
        phone=payload.phone,
        state_code=payload.state_code
    )
    return customer

@api.delete("/customers/{customer_id}")
def delete_customer(request, customer_id: int):
    """Soft deletes a customer (sets soft_deleted=1)."""
    customer = Customer.objects.get(id=customer_id)
    customer.delete()
    return {"status": "success", "message": f"Customer '{customer.name}' soft deleted."}

# --- Mini App Cart & Catalog Endpoints ---

@api.get("/cart/init")
def cart_init(request, customer_id: int):
    """
    Returns initial Mini App state for a customer:
    - Customer profile details
    - Usual items (frequently ordered SKUs)
    - Full product catalog (~300 SKUs) with live rates
    """
    customer = get_object_or_404(Customer, id=customer_id)
    products = Product.objects.filter(is_active=True)
    
    catalog = [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "base_price": float(p.base_price),
            "gst_rate": float(p.gst_rate),
            "hsn_code": p.hsn_code
        }
        for p in products
    ]

    # Pre-fill top usual items (fallback to first 3 products if new customer)
    usual_items = catalog[:3] if catalog else []

    return {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "state_code": customer.state_code,
            "balance_amount": float(customer.balance_amount)
        },
        "usual_items": usual_items,
        "catalog": catalog
    }

@api.post("/cart/price")
def price_cart(request, payload: PriceCartInput):
    """
    Computes authoritative line totals and GST server-side.
    Intra-state (CGST 9% + SGST 9%) vs Inter-state (IGST 18%).
    """
    customer = get_object_or_404(Customer, id=payload.customer_id)
    subtotal = Decimal("0.00")
    total_cgst = Decimal("0.00")
    total_sgst = Decimal("0.00")
    total_igst = Decimal("0.00")

    # Assuming business tenant state code is "08" (Rajasthan)
    seller_state_code = "08"
    is_intra_state = (customer.state_code == seller_state_code)

    line_details = []
    for item in payload.items:
        product = get_object_or_404(Product, id=item.product_id)
        qty = item.quantity
        rate = product.base_price

        line_subtotal = rate * qty
        gst_pct = product.gst_rate
        line_gst = (line_subtotal * gst_pct) / Decimal("100.00")
        line_total = line_subtotal + line_gst

        if is_intra_state:
            cgst = line_gst / Decimal("2.00")
            sgst = line_gst / Decimal("2.00")
            igst = Decimal("0.00")
            total_cgst += cgst
            total_sgst += sgst
        else:
            cgst = Decimal("0.00")
            sgst = Decimal("0.00")
            igst = line_gst
            total_igst += igst

        subtotal += line_subtotal
        line_details.append({
            "product_id": product.id,
            "name": product.name,
            "sku": product.sku,
            "quantity": qty,
            "unit_rate": float(rate),
            "line_subtotal": float(line_subtotal),
            "line_gst": float(line_gst),
            "line_total": float(line_total)
        })

    grand_total = subtotal + total_cgst + total_sgst + total_igst

    return {
        "subtotal": float(subtotal),
        "cgst_amount": float(total_cgst),
        "sgst_amount": float(total_sgst),
        "igst_amount": float(total_igst),
        "total_amount": float(grand_total),
        "is_intra_state": is_intra_state,
        "lines": line_details
    }

@api.post("/cart/submit")
def submit_order(request, payload: SubmitOrderInput):
    """Persists a new order from Mini App and generates invoice voucher number."""
    customer = get_object_or_404(Customer, id=payload.customer_id)
    
    # Calculate price
    price_res = price_cart(request, PriceCartInput(customer_id=customer.id, items=payload.items))
    
    import random
    voucher_no = f"ORD-2026-{random.randint(1000, 9999)}"

    order = Order.objects.create(
        customer=customer,
        voucher_no=voucher_no,
        total_amount=Decimal(str(price_res["total_amount"])),
        status="placed"
    )

    return {
        "status": "success",
        "order_id": order.id,
        "voucher_no": order.voucher_no,
        "total_amount": float(order.total_amount),
        "message": f"Order #{order.voucher_no} placed successfully!"
    }
