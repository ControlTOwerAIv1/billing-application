import json
import random
import urllib.request
import urllib.parse
from decimal import Decimal
from typing import List, Optional
from ninja import NinjaAPI, Schema
from django.shortcuts import get_object_or_404
import requests
from django.http import HttpResponse
from apps.core.models import Customer, Product, Order, OrderItem
from backend.config import TELEGRAM_BOT_TOKEN
from backend.invoice_generator import generate_order_pdf_bytes

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
    chat_id: Optional[int] = None
    notes: Optional[str] = None

def send_telegram_order_notification(chat_id: int, order: Order):
    """Helper to send instant Telegram chat notification and PDF invoice document when order is placed."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("your_"):
        return

    voucher_no = order.voucher_no
    customer_name = order.customer.name
    total_amount = float(order.total_amount)

    text = (
        f"🎉 <b>Your Order Has Been Successfully Created!</b>\n\n"
        f"📦 <b>Voucher No:</b> #{voucher_no}\n"
        f"👤 <b>Customer:</b> {customer_name}\n"
        f"💰 <b>Total Amount:</b> ₹{total_amount:,.2f}\n"
        f"🚚 <b>Status:</b> Placed & Sent to Wholesaler\n\n"
        f"📄 <b>Tax Invoice PDF</b> is attached below. You can download or forward it directly!"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[Telegram Notify Error]: {e}")

    # Send PDF Document via Telegram sendDocument API
    try:
        pdf_bytes = generate_order_pdf_bytes(order)
        doc_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        filename = f"Invoice_{voucher_no}.pdf"
        files = {"document": (filename, pdf_bytes, "application/pdf")}
        payload = {"chat_id": chat_id, "caption": f"📄 Tax Invoice #{voucher_no}"}
        requests.post(doc_url, data=payload, files=files, timeout=10)
    except Exception as e:
        print(f"[Telegram PDF Send Error]: {e}")

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

@api.get("/cart/init")
def cart_init(request, customer_id: int):
    """Returns initial Mini App state for a customer."""
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
    """Computes line totals and GST server-side."""
    customer = get_object_or_404(Customer, id=payload.customer_id)
    subtotal = Decimal("0.00")
    total_cgst = Decimal("0.00")
    total_sgst = Decimal("0.00")
    total_igst = Decimal("0.00")

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
    """Persists a new order from Mini App and sends Telegram chat notification with PDF invoice."""
    customer = get_object_or_404(Customer, id=payload.customer_id)
    price_res = price_cart(request, PriceCartInput(customer_id=customer.id, items=payload.items))
    
    voucher_no = f"ORD-2026-{random.randint(1000, 9999)}"

    order = Order.objects.create(
        customer=customer,
        voucher_no=voucher_no,
        total_amount=Decimal(str(price_res["total_amount"])),
        status="placed"
    )

    for item in payload.items:
        product = get_object_or_404(Product, id=item.product_id)
        unit_price = product.base_price
        taxable_amt = unit_price * Decimal(item.quantity)
        OrderItem.objects.create(
            order=order,
            product=product,
            unit_type="loose",
            quantity=item.quantity,
            unit_price=unit_price,
            taxable_amount=taxable_amt,
            gst_rate=product.gst_rate
        )

    order.calculate_taxes_and_totals(tenant_state_code="08")

    # Determine chat_id for Telegram notification
    target_chat_id = payload.chat_id
    if not target_chat_id and customer.phone and customer.phone.startswith("+91-"):
        try:
            target_chat_id = int(customer.phone.replace("+91-", ""))
        except ValueError:
            pass

    if target_chat_id:
        send_telegram_order_notification(target_chat_id, order)

    pdf_url = f"/api/orders/{order.id}/pdf"

    return {
        "status": "success",
        "order_id": order.id,
        "voucher_no": order.voucher_no,
        "total_amount": float(order.total_amount),
        "pdf_url": pdf_url,
        "message": f"Order #{order.voucher_no} placed successfully!"
    }

@api.get("/orders/{order_id}/pdf")
def download_order_pdf(request, order_id: int):
    """Generates and streams the PDF invoice for a given order ID."""
    order = get_object_or_404(Order, id=order_id)
    pdf_bytes = generate_order_pdf_bytes(order)
    
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Invoice_{order.voucher_no}.pdf"'
    return response
