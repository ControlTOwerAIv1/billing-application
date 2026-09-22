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
from apps.core.models import Customer, Product, Order, OrderItem, OrderStatus, Transport
from backend.config import TELEGRAM_BOT_TOKEN
from backend.invoice_generator import generate_order_pdf_bytes

api = NinjaAPI(title="OrderBot Django API", version="1.0.0")

class TransportSchema(Schema):
    id: int
    name: str
    phone: Optional[str] = ""
    contact_person: Optional[str] = ""
    vehicle_number: Optional[str] = ""
    destination_notes: Optional[str] = ""
    is_active: bool

class CreateTransportSchema(Schema):
    name: str
    phone: Optional[str] = ""
    contact_person: Optional[str] = ""
    vehicle_number: Optional[str] = ""
    destination_notes: Optional[str] = ""

class CustomerSchema(Schema):
    id: int
    name: str
    phone: str
    city: Optional[str] = ""
    state_code: str
    balance_amount: float
    status: str
    transport_id: Optional[int] = None
    transport_name: Optional[str] = None

class CreateCustomerSchema(Schema):
    name: str
    phone: str
    city: Optional[str] = ""
    state_code: Optional[str] = "08"
    transport_id: Optional[int] = None

class CartItemInput(Schema):
    product_id: int
    quantity: int
    unit_type: Optional[str] = "loose"

class PriceCartInput(Schema):
    customer_id: int
    items: List[CartItemInput]
    packing_charge: Optional[float] = 0.0
    discount_amount: Optional[float] = 0.0
    gst_enabled: Optional[bool] = True
    gst_rate: Optional[float] = None

class SubmitOrderInput(Schema):
    customer_id: int
    items: List[CartItemInput]
    chat_id: Optional[int] = None
    notes: Optional[str] = None
    packing_charge: Optional[float] = 0.0
    discount_amount: Optional[float] = 0.0
    transport_id: Optional[int] = None
    gst_enabled: Optional[bool] = True
    gst_rate: Optional[float] = None

class EditOrderInput(Schema):
    status: Optional[str] = None
    items: Optional[List[CartItemInput]] = None
    notes: Optional[str] = None
    packing_charge: Optional[float] = None
    discount_amount: Optional[float] = None
    transport_id: Optional[int] = None
    gst_enabled: Optional[bool] = None
    gst_rate: Optional[float] = None

def send_telegram_order_notification(chat_id: int, order: Order, action_label: str = "Created"):
    """Helper to send instant Telegram chat notification and PDF invoice document when order is placed or updated."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("your_"):
        return

    voucher_no = order.voucher_no
    customer_name = order.customer.name
    total_amount = float(order.total_amount)

    extra_details = ""
    if order.packing_charge > Decimal("0.00"):
        extra_details += f"\n📦 <b>Packing Charge:</b> ₹{float(order.packing_charge):,.2f}"
    if order.discount_amount > Decimal("0.00"):
        extra_details += f"\n🏷️ <b>Discount:</b> -₹{float(order.discount_amount):,.2f}"
    trans_name = order.transport.name if order.transport else (order.customer.transport.name if order.customer.transport else None)
    if trans_name:
        extra_details += f"\n🚚 <b>Transport:</b> {trans_name}"

    text = (
        f"🎉 <b>Your Order Has Been Successfully {action_label}!</b>\n\n"
        f"📦 <b>Voucher No:</b> #{voucher_no}\n"
        f"👤 <b>Customer:</b> {customer_name}\n"
        f"💰 <b>Total Amount:</b> ₹{total_amount:,.2f}"
        f"{extra_details}\n"
        f"🚚 <b>Status:</b> {order.get_status_display() if hasattr(order, 'get_status_display') else order.status.capitalize()}\n\n"
        f"📄 <b>Tax Invoice PDF</b> is attached below."
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"[Telegram Notify Error]: {e}")

    try:
        pdf_bytes = generate_order_pdf_bytes(order)
        doc_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
        filename = f"Invoice_{voucher_no}.pdf"
        files = {"document": (filename, pdf_bytes, "application/pdf")}
        payload = {"chat_id": chat_id, "caption": f"📄 Tax Invoice #{voucher_no}"}
        requests.post(doc_url, data=payload, files=files, timeout=10)
    except Exception as e:
        print(f"[Telegram PDF Send Error]: {e}")

@api.get("/transports", response=List[TransportSchema])
def list_transports_api(request):
    """Returns active logistics/transport carriers."""
    return list(Transport.objects.filter(is_active=True, soft_deleted=False).values())

@api.post("/transports", response=TransportSchema)
def create_transport_api(request, payload: CreateTransportSchema):
    """Registers a new logistics/transport carrier."""
    transport = Transport.objects.create(
        name=payload.name.strip(),
        phone=payload.phone or "",
        contact_person=payload.contact_person or "",
        vehicle_number=payload.vehicle_number or "",
        destination_notes=payload.destination_notes or ""
    )
    return transport

@api.get("/customers", response=List[CustomerSchema])
def list_customers(request):
    """Returns active customers (soft_deleted=0)."""
    customers = Customer.objects.select_related("transport").filter(soft_deleted=False)
    results = []
    for c in customers:
        results.append({
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "city": c.city or "",
            "state_code": c.state_code,
            "balance_amount": float(c.balance_amount),
            "status": c.status,
            "transport_id": c.transport_id,
            "transport_name": c.transport.name if c.transport else None,
        })
    return results

@api.post("/customers", response=CustomerSchema)
def create_customer(request, payload: CreateCustomerSchema):
    """Creates a new customer."""
    trans = None
    if payload.transport_id:
        trans = Transport.objects.filter(id=payload.transport_id, soft_deleted=False).first()
    customer = Customer.objects.create(
        name=payload.name,
        phone=payload.phone,
        city=payload.city or "",
        state_code=payload.state_code or "08",
        transport=trans
    )
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "city": customer.city or "",
        "state_code": customer.state_code,
        "balance_amount": float(customer.balance_amount),
        "status": customer.status,
        "transport_id": customer.transport_id,
        "transport_name": customer.transport.name if customer.transport else None,
    }

@api.delete("/customers/{customer_id}")
def delete_customer(request, customer_id: int):
    """Soft deletes a customer (sets soft_deleted=1)."""
    customer = Customer.objects.get(id=customer_id)
    customer.delete()
    return {"status": "success", "message": f"Customer '{customer.name}' soft deleted."}

@api.get("/cart/init")
def cart_init(request, customer_id: Optional[int] = None):
    """Returns initial Mini App state for a customer including categories, images, and pricing tiers."""
    customer = None
    if customer_id:
        customer = Customer.objects.filter(id=customer_id, soft_deleted=False).first()
    if not customer:
        customer = Customer.objects.filter(soft_deleted=False).first()
    if not customer:
        customer = get_object_or_404(Customer, id=customer_id or 1)
    products = Product.objects.filter(is_active=True, soft_deleted=0)
    
    categories = sorted(list(set(products.values_list("category", flat=True).distinct())))
    groups = sorted([g for g in set(products.values_list("group_alias", flat=True).distinct()) if g])
    category_aliases = sorted([c for c in set(products.values_list("category_alias", flat=True).distinct()) if c])
    
    catalog = [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "group_alias": p.group_alias or "",
            "category_alias": p.category_alias or "",
            "category": p.group_alias or p.category or "General",
            "opening_qty": float(p.opening_qty),
            "closing_qty": float(p.closing_qty),
            "image_url": p.photo_url or p.image_url or "",
            "photo_url": p.photo_url or p.image_url or "",
            "base_price": float(p.base_price),
            "loose_price": float(p.loose_price or p.base_price),
            "full_carton_price": float(p.full_carton_price),
            "half_carton_price": float(p.half_carton_price),
            "full_carton_quantity": p.full_carton_quantity,
            "gst_rate": float(p.gst_rate),
            "hsn_code": p.hsn_code
        }
        for p in products
    ]

    usual_items = catalog[:6] if catalog else []
    loc_str = f"{customer.city}, {customer.state_code}" if customer.city else f"State {customer.state_code}"

    transports = [
        {
            "id": t.id,
            "name": t.name,
            "phone": t.phone or "",
            "vehicle_number": t.vehicle_number or ""
        }
        for t in Transport.objects.filter(is_active=True, soft_deleted=False).order_by("name")
    ]

    return {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "city": customer.city or "",
            "location": loc_str,
            "phone": customer.phone,
            "state_code": customer.state_code,
            "balance_amount": float(customer.balance_amount),
            "credit_limit": float(customer.credit_limit),
            "transport_id": customer.transport_id,
            "transport_name": customer.transport.name if customer.transport else None,
            "transport": {
                "id": customer.transport.id,
                "name": customer.transport.name,
                "phone": customer.transport.phone or "",
                "vehicle_number": customer.transport.vehicle_number or ""
            } if customer.transport else None
        },
        "transports": transports,
        "categories": categories,
        "groups": groups,
        "category_aliases": category_aliases,
        "usual_items": usual_items,
        "catalog": catalog
    }

@api.post("/cart/price")
def price_cart(request, payload: PriceCartInput):
    """Computes line totals and GST server-side with unit type support."""
    customer = get_object_or_404(Customer, id=payload.customer_id)
    subtotal = Decimal("0.00")
    total_cgst = Decimal("0.00")
    total_sgst = Decimal("0.00")
    total_igst = Decimal("0.00")
    packing_charge = Decimal(str(payload.packing_charge or 0.0)).quantize(Decimal("0.01"))
    discount_amount = Decimal(str(payload.discount_amount or 0.0)).quantize(Decimal("0.01"))

    gst_enabled = True if payload.gst_enabled is None else bool(payload.gst_enabled)
    custom_rate = Decimal(str(payload.gst_rate)).quantize(Decimal("0.01")) if (payload.gst_rate is not None and str(payload.gst_rate).strip() != "") else None
    if custom_rate is not None and custom_rate <= Decimal("0.00"):
        gst_enabled = False

    seller_state_code = "08"
    is_intra_state = (customer.state_code == seller_state_code)

    line_details = []
    for item in payload.items:
        product = get_object_or_404(Product, id=item.product_id)
        qty = item.quantity
        if qty <= 0:
            continue
        unit_type = item.unit_type or "loose"
        rate = product.get_price(unit_type)

        line_subtotal = rate * Decimal(qty)
        if not gst_enabled:
            effective_gst_pct = Decimal("0.00")
            line_gst = Decimal("0.00")
            cgst = Decimal("0.00")
            sgst = Decimal("0.00")
            igst = Decimal("0.00")
        else:
            effective_gst_pct = custom_rate if custom_rate is not None else product.gst_rate
            line_gst = (line_subtotal * effective_gst_pct) / Decimal("100.00")
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

        line_total = line_subtotal + line_gst

        subtotal += line_subtotal
        line_details.append({
            "product_id": product.id,
            "name": product.name,
            "sku": product.sku,
            "unit_type": unit_type,
            "quantity": qty,
            "unit_rate": float(rate),
            "gst_rate": float(effective_gst_pct),
            "line_subtotal": float(line_subtotal),
            "line_gst": float(line_gst),
            "line_total": float(line_total)
        })

    calc_total = subtotal + total_cgst + total_sgst + total_igst + packing_charge - discount_amount
    grand_total = max(Decimal("0.00"), calc_total)

    return {
        "subtotal": float(subtotal),
        "gst_enabled": gst_enabled,
        "gst_rate": float(custom_rate) if custom_rate is not None else None,
        "cgst_amount": float(total_cgst),
        "sgst_amount": float(total_sgst),
        "igst_amount": float(total_igst),
        "packing_charge": float(packing_charge),
        "discount_amount": float(discount_amount),
        "total_amount": float(grand_total),
        "is_intra_state": is_intra_state,
        "lines": line_details
    }

@api.post("/cart/submit")
def submit_order(request, payload: SubmitOrderInput):
    """Persists a new order from Mini App and sends Telegram chat notification with PDF invoice."""
    customer = get_object_or_404(Customer, id=payload.customer_id)
    packing_charge = Decimal(str(payload.packing_charge or 0.0)).quantize(Decimal("0.01"))
    discount_amount = Decimal(str(payload.discount_amount or 0.0)).quantize(Decimal("0.01"))

    gst_enabled = True if payload.gst_enabled is None else bool(payload.gst_enabled)
    custom_rate = Decimal(str(payload.gst_rate)).quantize(Decimal("0.01")) if (payload.gst_rate is not None and str(payload.gst_rate).strip() != "") else None
    if custom_rate is not None and custom_rate <= Decimal("0.00"):
        gst_enabled = False

    price_res = price_cart(request, PriceCartInput(
        customer_id=customer.id,
        items=payload.items,
        packing_charge=float(packing_charge),
        discount_amount=float(discount_amount),
        gst_enabled=gst_enabled,
        gst_rate=float(custom_rate) if custom_rate is not None else None
    ))
    
    voucher_no = f"ORD-2026-{random.randint(1000, 9999)}"

    order_transport = None
    if payload.transport_id:
        order_transport = Transport.objects.filter(id=payload.transport_id, soft_deleted=False).first()
    if not order_transport and customer.transport:
        order_transport = customer.transport

    order = Order.objects.create(
        customer=customer,
        transport=order_transport,
        voucher_no=voucher_no,
        packing_charge=packing_charge,
        discount_amount=discount_amount,
        gst_enabled=price_res.get("gst_enabled", gst_enabled),
        custom_gst_rate=custom_rate,
        total_amount=Decimal(str(price_res["total_amount"])),
        status="placed"
    )

    for item in payload.items:
        if item.quantity <= 0:
            continue
        product = get_object_or_404(Product, id=item.product_id)
        unit_type = item.unit_type or "loose"
        unit_price = product.get_price(unit_type)
        taxable_amt = unit_price * Decimal(item.quantity)
        effective_rate = custom_rate if (custom_rate is not None and gst_enabled) else product.gst_rate
        OrderItem.objects.create(
            order=order,
            product=product,
            unit_type=unit_type,
            quantity=item.quantity,
            unit_price=unit_price,
            taxable_amount=taxable_amt,
            gst_rate=effective_rate
        )

    order.calculate_taxes_and_totals(tenant_state_code="08")
    customer.balance_amount += order.total_amount
    customer.save()

    # Determine chat_id for Telegram notification
    target_chat_id = payload.chat_id
    if not target_chat_id and customer.phone and customer.phone.startswith("+91-"):
        try:
            target_chat_id = int(customer.phone.replace("+91-", ""))
        except ValueError:
            pass

    if target_chat_id:
        send_telegram_order_notification(target_chat_id, order, action_label="Created")

    pdf_url = f"/api/orders/{order.id}/pdf"

    return {
        "status": "success",
        "order_id": order.id,
        "voucher_no": order.voucher_no,
        "transport_id": order.transport_id,
        "transport_name": order.transport.name if order.transport else "Direct / Self",
        "gst_enabled": order.gst_enabled,
        "gst_rate": float(order.custom_gst_rate) if order.custom_gst_rate else None,
        "packing_charge": float(order.packing_charge),
        "discount_amount": float(order.discount_amount),
        "total_amount": float(order.total_amount),
        "pdf_url": pdf_url,
        "message": f"Order #{order.voucher_no} placed successfully!"
    }

@api.get("/orders")
def list_orders(request, customer_id: Optional[int] = None, status: Optional[str] = None):
    """Lists orders with optional customer and status filters."""
    qs = Order.objects.select_related("customer", "transport", "customer__transport").all().order_by("-created_at")
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if status:
        qs = qs.filter(status__iexact=status)

    orders_data = []
    for o in qs[:30]:
        items_list = [
            {
                "product_id": item.product.id,
                "product_name": item.product.name,
                "sku": item.product.sku,
                "unit_type": item.unit_type,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "total_amount": float(item.total_amount)
            }
            for item in o.items.all()
        ]
        orders_data.append({
            "id": o.id,
            "voucher_no": o.voucher_no,
            "customer_id": o.customer.id,
            "customer_name": o.customer.name,
            "customer_location": f"{o.customer.city}, {o.customer.state_code}" if o.customer.city else o.customer.state_code,
            "transport_id": o.transport_id,
            "transport_name": o.transport.name if o.transport else (o.customer.transport.name if o.customer.transport else "Self / Direct"),
            "gst_enabled": o.gst_enabled,
            "gst_rate": float(o.custom_gst_rate) if o.custom_gst_rate else None,
            "status": o.status,
            "subtotal": float(o.subtotal),
            "cgst_amount": float(o.cgst_amount),
            "sgst_amount": float(o.sgst_amount),
            "igst_amount": float(o.igst_amount),
            "packing_charge": float(o.packing_charge),
            "discount_amount": float(o.discount_amount),
            "total_amount": float(o.total_amount),
            "item_count": len(items_list),
            "items": items_list,
            "pdf_url": f"/api/orders/{o.id}/pdf",
            "created_at": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else ""
        })

    return {"status": "success", "count": len(orders_data), "orders": orders_data}

@api.get("/orders/{order_id}")
def get_order_detail(request, order_id: int):
    """Gets complete details of an order."""
    order = get_object_or_404(Order.objects.select_related("customer", "transport", "customer__transport"), id=order_id)
    items_list = [
        {
            "id": item.id,
            "product_id": item.product.id,
            "product_name": item.product.name,
            "sku": item.product.sku,
            "group_alias": item.product.group_alias or "",
            "category_alias": item.product.category_alias or "",
            "image_url": item.product.photo_url or item.product.image_url or "",
            "photo_url": item.product.photo_url or item.product.image_url or "",
            "unit_type": item.unit_type,
            "quantity": item.quantity,
            "unit_price": float(item.unit_price),
            "taxable_amount": float(item.taxable_amount),
            "total_amount": float(item.total_amount)
        }
        for item in order.items.all()
    ]
    return {
        "status": "success",
        "id": order.id,
        "voucher_no": order.voucher_no,
        "customer": {
            "id": order.customer.id,
            "name": order.customer.name,
            "city": order.customer.city or "",
            "location": f"{order.customer.city}, {order.customer.state_code}" if order.customer.city else order.customer.state_code,
            "phone": order.customer.phone
        },
        "transport_id": order.transport_id,
        "transport_name": order.transport.name if order.transport else (order.customer.transport.name if order.customer.transport else "Self / Direct"),
        "gst_enabled": order.gst_enabled,
        "gst_rate": float(order.custom_gst_rate) if order.custom_gst_rate else None,
        "status": order.status,
        "subtotal": float(order.subtotal),
        "cgst_amount": float(order.cgst_amount),
        "sgst_amount": float(order.sgst_amount),
        "igst_amount": float(order.igst_amount),
        "packing_charge": float(order.packing_charge),
        "discount_amount": float(order.discount_amount),
        "total_amount": float(order.total_amount),
        "pdf_url": f"/api/orders/{order.id}/pdf",
        "items": items_list
    }

@api.post("/orders/{order_id}/edit")
def edit_order_api(request, order_id: int, payload: EditOrderInput):
    """Edits order status, items, packing charge, and/or discount amount, recalculates taxes, and adjusts customer balance."""
    order = get_object_or_404(Order.objects.select_related("customer", "transport"), id=order_id)
    old_total = order.total_amount

    if payload.status:
        clean_status = payload.status.lower().strip()
        valid_statuses = [choice[0] for choice in OrderStatus.choices]
        if clean_status in valid_statuses:
            order.status = clean_status
        else:
            return {"status": "error", "message": f"Invalid status '{payload.status}'. Valid: {valid_statuses}"}

    if payload.packing_charge is not None:
        order.packing_charge = Decimal(str(payload.packing_charge)).quantize(Decimal("0.01"))
    if payload.discount_amount is not None:
        order.discount_amount = Decimal(str(payload.discount_amount)).quantize(Decimal("0.01"))

    if payload.gst_enabled is not None:
        order.gst_enabled = bool(payload.gst_enabled)
    if payload.gst_rate is not None:
        if str(payload.gst_rate).strip() == "":
            order.custom_gst_rate = None
        else:
            order.custom_gst_rate = Decimal(str(payload.gst_rate)).quantize(Decimal("0.01"))
            if order.custom_gst_rate <= Decimal("0.00"):
                order.gst_enabled = False

    if payload.transport_id is not None:
        if payload.transport_id == 0:
            order.transport = None
        else:
            order.transport = Transport.objects.filter(id=payload.transport_id).first()
        order.save(update_fields=["transport"])

    if payload.items is not None:
        order.items.all().delete()
        for item in payload.items:
            if item.quantity <= 0:
                continue
            product = get_object_or_404(Product, id=item.product_id)
            unit_type = item.unit_type or "loose"
            unit_price = product.get_price(unit_type)
            taxable_amt = unit_price * Decimal(item.quantity)
            effective_rate = order.custom_gst_rate if (order.custom_gst_rate is not None and order.gst_enabled) else product.gst_rate

            OrderItem.objects.create(
                order=order,
                product=product,
                unit_type=unit_type,
                quantity=item.quantity,
                unit_price=unit_price,
                taxable_amount=taxable_amt,
                gst_rate=effective_rate
            )

        order.calculate_taxes_and_totals(tenant_state_code="08")
    else:
        order.calculate_taxes_and_totals(tenant_state_code="08")

    diff = order.total_amount - old_total
    cust = order.customer
    cust.balance_amount += diff
    cust.save()

    return {
        "status": "success",
        "order_id": order.id,
        "voucher_no": order.voucher_no,
        "order_status": order.status,
        "transport_id": order.transport_id,
        "transport_name": order.transport.name if order.transport else "Direct / Self",
        "gst_enabled": order.gst_enabled,
        "gst_rate": float(order.custom_gst_rate) if order.custom_gst_rate else None,
        "subtotal": float(order.subtotal),
        "cgst_amount": float(order.cgst_amount),
        "sgst_amount": float(order.sgst_amount),
        "igst_amount": float(order.igst_amount),
        "packing_charge": float(order.packing_charge),
        "discount_amount": float(order.discount_amount),
        "total_amount": float(order.total_amount),
        "balance_adjustment": float(diff),
        "customer_new_balance": float(cust.balance_amount),
        "pdf_url": f"/api/orders/{order.id}/pdf",
        "message": f"Order #{order.voucher_no} updated successfully!"
    }

@api.get("/orders/{order_id}/pdf")
def download_order_pdf(request, order_id: int):
    """Generates and streams the PDF invoice for a given order ID."""
    order = get_object_or_404(Order, id=order_id)
    pdf_bytes = generate_order_pdf_bytes(order)
    
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Invoice_{order.voucher_no}.pdf"'
    return response
