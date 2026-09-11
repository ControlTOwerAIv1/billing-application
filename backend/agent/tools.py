import os
import sys
import json
import uuid
from decimal import Decimal
from pathlib import Path

from langchain_core.tools import tool

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from apps.core.models import (
    Customer, Product, Order, OrderItem, Warehouse, WarehouseProduct,
    PurchaseOrder, PoItem, Account, Ledger, CustomerStatus, OrderStatus, OrderType, PaymentStatus, AccountGroup, EntryType, Transport
)
from backend.db import execute_sql_query

MODULES_DIR = BASE_DIR / "modules"

# --- Disambiguation & Resolution Helpers ---

def resolve_single_customer(customer_identifier: str) -> tuple[Customer | None, dict | None]:
    """
    Finds a customer by ID, phone, or name.
    If multiple customers match the name, returns (None, disambiguation_dict) with location details.
    If no customer matches, returns (None, error_dict).
    If exactly one customer matches, returns (customer, None).
    """
    if not customer_identifier:
        return None, {"status": "error", "message": "Customer identifier is required."}

    ident_str = str(customer_identifier).strip()

    # 1. Check ID if integer
    if ident_str.isdigit():
        cust = Customer.objects.filter(id=int(ident_str)).first()
        if cust:
            return cust, None

    # 2. Check exact phone match
    cust = Customer.objects.filter(phone=ident_str).first()
    if cust:
        return cust, None

    # 3. Search name or business name or phone
    qs = Customer.objects.filter(name__icontains=ident_str) | Customer.objects.filter(business_name__icontains=ident_str) | Customer.objects.filter(phone__icontains=ident_str)
    qs = qs.distinct()

    count = qs.count()
    if count == 0:
        return None, {"status": "error", "message": f"No customer found matching '{ident_str}'."}

    if count > 1:
        # If there's an exact case-insensitive match on name and it's unique, use it
        exact_matches = Customer.objects.filter(name__iexact=ident_str)
        if exact_matches.count() == 1:
            return exact_matches.first(), None
        elif exact_matches.count() > 1:
            qs = exact_matches

        matches = []
        for c in qs[:10]:
            city_str = c.city or "Unknown City"
            matches.append({
                "id": c.id,
                "name": c.name,
                "city": c.city or "",
                "state_code": c.state_code,
                "phone": c.phone,
                "display": f"{c.name} from {city_str} (State {c.state_code}, Phone: {c.phone})"
            })

        clarification_msg = (
            f"Multiple customers found matching '{ident_str}'. Please clarify which one you mean:\n" +
            "\n".join([f"- {m['display']} [ID: {m['id']}]" for m in matches])
        )
        return None, {
            "status": "disambiguation_required",
            "message": clarification_msg,
            "matches": matches
        }

    return qs.first(), None

# --- Tool Implementations ---

def tool_create_transport(name: str, phone: str = "", contact_person: str = "", vehicle_number: str = "", destination_notes: str = "") -> dict:
    """Creates a new transport / logistics carrier service or updates an existing one."""
    if not name:
        return {"status": "error", "message": "Transport name is required."}

    t = Transport.objects.filter(name__iexact=name.strip()).first()
    created = False
    if not t:
        t = Transport.objects.create(
            name=name.strip(),
            phone=phone.strip() if phone else "",
            contact_person=contact_person.strip() if contact_person else "",
            vehicle_number=vehicle_number.strip() if vehicle_number else "",
            destination_notes=destination_notes.strip() if destination_notes else "",
            is_active=True
        )
        created = True
    else:
        if phone: t.phone = phone.strip()
        if contact_person: t.contact_person = contact_person.strip()
        if vehicle_number: t.vehicle_number = vehicle_number.strip()
        if destination_notes: t.destination_notes = destination_notes.strip()
        t.is_active = True
        t.save()

    return {
        "status": "success",
        "success": True,
        "action": "created" if created else "updated",
        "transport": {
            "id": t.id,
            "name": t.name,
            "phone": t.phone or "",
            "contact_person": t.contact_person or "",
            "vehicle_number": t.vehicle_number or "",
            "destination_notes": t.destination_notes or "",
            "is_active": t.is_active
        },
        "message": f"Transport '{t.name}' {'created' if created else 'updated'} successfully."
    }

def tool_list_transports(search: str = "") -> dict:
    """Lists all active transport services available for orders and customer shipping."""
    qs = Transport.objects.filter(soft_deleted=False, is_active=True).order_by("name")
    if search:
        qs = qs.filter(name__icontains=search.strip())
    transports = [
        {
            "id": t.id,
            "name": t.name,
            "phone": t.phone or "",
            "contact_person": t.contact_person or "",
            "vehicle_number": t.vehicle_number or "",
            "destination_notes": t.destination_notes or ""
        }
        for t in qs
    ]
    return {
        "status": "success",
        "count": len(transports),
        "transports": transports
    }

def tool_assign_customer_transport(customer_identifier: str, transport_identifier: str) -> dict:
    """Assigns or updates a customer's preferred transport carrier."""
    cust, err = resolve_single_customer(customer_identifier)
    if not cust:
        return err or {"status": "error", "message": f"Customer '{customer_identifier}' not found."}

    trans = None
    if str(transport_identifier).isdigit():
        trans = Transport.objects.filter(id=int(transport_identifier), soft_deleted=False).first()
    if not trans:
        trans = Transport.objects.filter(name__icontains=str(transport_identifier).strip(), soft_deleted=False).first()

    if not trans:
        avail = list(Transport.objects.filter(soft_deleted=False, is_active=True).values_list("name", flat=True))
        return {"status": "error", "message": f"Transport '{transport_identifier}' not found. Available transports: {avail}"}

    cust.transport = trans
    cust.save()
    return {
        "status": "success",
        "success": True,
        "message": f"Transport '{trans.name}' successfully assigned to customer '{cust.name}'.",
        "customer_id": cust.id,
        "customer_name": cust.name,
        "transport": trans.name
    }

def tool_create_customer(name: str, phone: str, city: str = "", state_code: str = "08", business_name: str = "", email: str = "", gstin: str = "", pan: str = "", credit_limit: float = 0.0, transport: str = "", transport_id: int = 0) -> dict:
    """Creates a new customer record with location and optional transport assignment, linking an Account in Debtors."""
    if not name:
        return {"status": "error", "message": "Customer name is required."}
    if not phone:
        return {"status": "error", "message": "Phone number is required."}

    # Resolve transport if provided
    assigned_trans = None
    if transport_id:
        assigned_trans = Transport.objects.filter(id=transport_id, soft_deleted=False).first()
    if not assigned_trans and transport:
        assigned_trans = Transport.objects.filter(name__icontains=str(transport).strip(), soft_deleted=False).first()

    customer, created = Customer.objects.get_or_create(
        name=name.strip(),
        defaults={
            "phone": phone.strip(),
            "city": city.strip(),
            "state_code": state_code.strip() or "08",
            "business_name": business_name.strip(),
            "email": email.strip(),
            "gstin": gstin.strip(),
            "pan": pan.strip(),
            "credit_limit": Decimal(str(credit_limit or 0.0)),
            "transport": assigned_trans
        }
    )

    if not created:
        if phone: customer.phone = phone.strip()
        if city: customer.city = city.strip()
        if state_code: customer.state_code = state_code.strip()
        if business_name: customer.business_name = business_name.strip()
        if email: customer.email = email.strip()
        if gstin: customer.gstin = gstin.strip()
        if pan: customer.pan = pan.strip()
        if credit_limit: customer.credit_limit = Decimal(str(credit_limit))
        if assigned_trans: customer.transport = assigned_trans
        customer.save()

    Account.objects.get_or_create(
        name=f"Debtor - {customer.name}",
        customer=customer,
        defaults={"account_group": AccountGroup.DEBTORS}
    )

    available_transports = [
        {"id": t.id, "name": t.name, "phone": t.phone or ""}
        for t in Transport.objects.filter(soft_deleted=False, is_active=True).order_by("name")
    ]

    res = {
        "status": "success",
        "success": True,
        "id": customer.id,
        "action": "created" if created else "updated",
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "city": customer.city or "",
            "location": f"{customer.city}, {customer.state_code}" if customer.city else customer.state_code,
            "phone": customer.phone,
            "state_code": customer.state_code,
            "transport": customer.transport.name if customer.transport else None,
            "transport_id": customer.transport.id if customer.transport else None,
            "credit_limit": float(customer.credit_limit),
            "balance_amount": float(customer.balance_amount)
        }
    }

    if not customer.transport:
        res["transport_selection_needed"] = True
        res["available_transports"] = available_transports
        res["prompt"] = (
            f"Customer '{customer.name}' created! Note: No transport is assigned yet. "
            f"Available transports: {[t['name'] for t in available_transports]}. "
            f"Ask the user which transport this customer should travel/ship through."
        )

    return res

def tool_search_customers(query: str = "", city: str = "", state_code: str = "", status: str = "", has_balance_due: bool = False) -> dict:
    """Searches active customers with filters for query, city/location, state_code, status, and outstanding balance."""
    qs = Customer.objects.all()
    if query:
        qs = qs.filter(name__icontains=query) | qs.filter(phone__icontains=query) | qs.filter(business_name__icontains=query) | qs.filter(city__icontains=query)
    if city:
        qs = qs.filter(city__icontains=city)
    if state_code:
        qs = qs.filter(state_code__iexact=state_code)
    if status:
        qs = qs.filter(status__iexact=status)
    if has_balance_due:
        qs = qs.filter(balance_amount__gt=Decimal("0.00"))

    customers = [
        {
            "id": c.id,
            "name": c.name,
            "city": c.city or "",
            "state_code": c.state_code,
            "location": f"{c.city}, {c.state_code}" if c.city else f"State {c.state_code}",
            "phone": c.phone,
            "business_name": c.business_name or "",
            "credit_limit": float(c.credit_limit),
            "balance_amount": float(c.balance_amount),
            "status": c.status
        }
        for c in qs[:30]
    ]
    return {
        "status": "success",
        "count": len(customers),
        "filters_applied": {
            "query": query,
            "city": city,
            "state_code": state_code,
            "status": status,
            "has_balance_due": has_balance_due
        },
        "customers": customers
    }

def tool_soft_delete_customer(customer_identifier: str = "", customer_id: int = None, name: str = "") -> dict:
    """Soft deletes a customer record. Resolves ambiguity if multiple match."""
    ident = str(customer_id) if customer_id else (customer_identifier or name)
    cust, err = resolve_single_customer(ident)
    if err:
        return err

    deleted_name = cust.name
    deleted_loc = f"{cust.city}, {cust.state_code}" if cust.city else cust.state_code
    cust.delete()

    return {
        "status": "success",
        "deleted_customer": f"{deleted_name} ({deleted_loc})",
        "deleted_count": 1
    }

def tool_create_product(
    sku: str,
    name: str,
    category: str,
    image_url: str,
    base_price: float = 0.0,
    loose_price: float = 0.0,
    full_carton_price: float = 0.0,
    half_carton_price: float = 0.0,
    full_carton_quantity: int = 1,
    gst_rate: float = 18.0,
    hsn_code: str = "3926"
) -> dict:
    """
    Creates or updates a product in the catalog.
    Requires SKU, Name, Category, Photo/Image URL, Unit Pricing, Full Carton Pricing, and Carton Quantity.
    """
    missing = []
    if not sku: missing.append("sku (Unique SKU code)")
    if not name: missing.append("name (Product Name)")
    if not category: missing.append("category")
    if not image_url: missing.append("image_url (Product Photo link or URL)")
    if base_price <= 0 and loose_price <= 0: missing.append("base_price or loose_price (Unit price > 0)")
    if full_carton_price <= 0: missing.append("full_carton_price (Full carton box price > 0)")
    if full_carton_quantity <= 0: missing.append("full_carton_quantity (Units per carton >= 1)")

    if missing:
        return {
            "status": "missing_required_fields",
            "message": f"Cannot create product. Missing required fields: {', '.join(missing)}. Please ask the user to provide all required product details including the product photo/image URL.",
            "missing_fields": missing
        }

    p_base = Decimal(str(base_price or loose_price))
    p_loose = Decimal(str(loose_price or base_price))
    p_carton = Decimal(str(full_carton_price))
    p_half = Decimal(str(half_carton_price or (p_carton / Decimal("2.0"))))

    product, created = Product.objects.get_or_create(
        sku=sku,
        defaults={
            "name": name,
            "category": category,
            "image_url": image_url,
            "base_price": p_base,
            "loose_price": p_loose,
            "full_carton_price": p_carton,
            "half_carton_price": p_half,
            "full_carton_quantity": full_carton_quantity,
            "gst_rate": Decimal(str(gst_rate)),
            "hsn_code": hsn_code,
            "is_active": True
        }
    )
    if not created:
        product.name = name
        product.category = category
        product.image_url = image_url
        product.base_price = p_base
        product.loose_price = p_loose
        product.full_carton_price = p_carton
        product.half_carton_price = p_half
        product.full_carton_quantity = full_carton_quantity
        product.gst_rate = Decimal(str(gst_rate))
        product.hsn_code = hsn_code
        product.is_active = True
        product.save()

    return {
        "status": "success",
        "action": "created" if created else "updated",
        "product": {
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
            "category": product.category,
            "image_url": product.image_url,
            "loose_price": float(product.loose_price),
            "full_carton_price": float(product.full_carton_price),
            "full_carton_quantity": product.full_carton_quantity,
            "gst_rate": float(product.gst_rate)
        }
    }

def tool_search_products(query: str = "", category: str = "") -> dict:
    """Searches active products by SKU, name, or category."""
    qs = Product.objects.filter(is_active=True)
    if query:
        qs = qs.filter(sku__icontains=query) | qs.filter(name__icontains=query) | qs.filter(category__icontains=query)
    if category:
        qs = qs.filter(category__iexact=category)

    products = [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "image_url": p.image_url or "",
            "base_price": float(p.base_price),
            "loose_price": float(p.loose_price),
            "full_carton_price": float(p.full_carton_price),
            "half_carton_price": float(p.half_carton_price),
            "full_carton_quantity": p.full_carton_quantity,
            "gst_rate": float(p.gst_rate)
        }
        for p in qs[:30]
    ]
    return {"status": "success", "count": len(products), "products": products}

def tool_create_order(customer_identifier: str, items: list, order_type: str = "sales", tenant_state_code: str = "08", transport: str = "", transport_id: int = 0) -> dict:
    """Creates a new order with multi-tier pricing, tax calculation, and optional transport assignment."""
    cust, err = resolve_single_customer(customer_identifier)
    if err:
        return err

    if isinstance(items, str):
        try:
            items = json.loads(items)
        except Exception:
            items = [{"product": items, "quantity": 1}]

    if not items or not isinstance(items, list):
        return {"status": "error", "message": "No order items provided. Please specify products and quantities to create the order."}

    voucher_no = f"INV-{uuid.uuid4().hex[:8].upper()}"
    o_type = OrderType.ADVANCE_PURCHASE if "advance" in str(order_type).lower() else OrderType.SALES

    selected_transport = None
    if transport_id and int(transport_id) > 0:
        selected_transport = Transport.objects.filter(id=int(transport_id), soft_deleted=False).first()
    elif transport:
        selected_transport = Transport.objects.filter(name__icontains=str(transport).strip(), soft_deleted=False).first()
    if not selected_transport and cust.transport:
        selected_transport = cust.transport

    order = Order.objects.create(
        customer=cust,
        transport=selected_transport,
        voucher_no=voucher_no,
        order_type=o_type,
        status=OrderStatus.PLACED
    )

    created_items = []
    for item in items:
        if isinstance(item, str):
            prod_id_or_sku = item.strip()
            qty = 1
            unit_type = "loose"
        elif isinstance(item, dict):
            prod_id_or_sku = item.get("product") or item.get("sku") or item.get("product_id") or ""
            qty_val = item.get("quantity", 1)
            qty = int(qty_val) if str(qty_val).isdigit() else 1
            unit_type = str(item.get("unit_type", "loose")).lower()
        else:
            continue

        if not prod_id_or_sku:
            continue

        prod = Product.objects.filter(sku__iexact=str(prod_id_or_sku)).first()
        if not prod and str(prod_id_or_sku).isdigit():
            prod = Product.objects.filter(id=int(prod_id_or_sku)).first()
        if not prod:
            prod = Product.objects.filter(name__icontains=str(prod_id_or_sku)).first()

        if not prod:
            order.delete()
            return {"status": "error", "message": f"Product '{prod_id_or_sku}' not found."}

        unit_price = prod.get_price(unit_type)
        taxable_amt = unit_price * Decimal(qty)

        order_item = OrderItem.objects.create(
            order=order,
            product=prod,
            unit_type=unit_type,
            quantity=qty,
            unit_price=unit_price,
            taxable_amount=taxable_amt,
            gst_rate=prod.gst_rate
        )
        created_items.append({
            "product_sku": prod.sku,
            "product_name": prod.name,
            "unit_type": unit_type,
            "quantity": qty,
            "unit_price": float(unit_price),
            "taxable_amount": float(taxable_amt)
        })

    if not created_items:
        order.delete()
        return {"status": "error", "message": "No valid products found to create the order. Please specify product SKUs/names and quantities."}

    order.calculate_taxes_and_totals(tenant_state_code=tenant_state_code)
    cust.balance_amount += order.total_amount
    cust.save()

    credit_warning = None
    if cust.credit_limit > Decimal("0.00"):
        if cust.balance_amount > cust.credit_limit:
            credit_warning = f"WARNING: Customer balance (Rs.{float(cust.balance_amount):.2f}) exceeds credit limit (Rs.{float(cust.credit_limit):.2f})."

    pdf_url = f"/api/orders/{order.id}/pdf"
    customer_loc = f"{cust.city}, {cust.state_code}" if cust.city else f"State {cust.state_code}"

    return {
        "status": "success",
        "voucher_no": order.voucher_no,
        "order_id": order.id,
        "customer": cust.name,
        "customer_location": customer_loc,
        "transport": order.transport.name if order.transport else None,
        "order_type": order.order_type,
        "subtotal": float(order.subtotal),
        "cgst_amount": float(order.cgst_amount),
        "sgst_amount": float(order.sgst_amount),
        "igst_amount": float(order.igst_amount),
        "total_amount": float(order.total_amount),
        "pdf_url": pdf_url,
        "invoice_pdf_download_link": f"http://127.0.0.1:8000{pdf_url}",
        "credit_warning": credit_warning,
        "items": created_items
    }

def tool_edit_order(
    order_identifier: str,
    status: str = "",
    items: list = None,
    tenant_state_code: str = "08"
) -> dict:
    """Edits an existing order: modifies status, updates line items/quantities, recalculates taxes, and adjusts customer balance."""
    order = None
    ident = str(order_identifier).strip().replace("#", "")
    if ident.isdigit():
        order = Order.objects.filter(id=int(ident)).first()
    if not order:
        order = Order.objects.filter(voucher_no__iexact=ident).first()
    if not order:
        order = Order.objects.filter(voucher_no__icontains=ident).first()
    if not order:
        return {"status": "error", "message": f"Order matching '{order_identifier}' not found."}

    old_total = order.total_amount
    changes = []

    # Update status if provided
    if status:
        clean_status = status.lower().strip()
        valid_statuses = [choice[0] for choice in OrderStatus.choices]
        if clean_status in valid_statuses:
            order.status = clean_status
            changes.append(f"Status changed to '{clean_status}'")
        else:
            return {"status": "error", "message": f"Invalid status '{status}'. Valid options: {', '.join(valid_statuses)}"}

    # Update items if provided
    if items is not None:
        if isinstance(items, str):
            try:
                items = json.loads(items)
            except Exception:
                items = [{"product": items, "quantity": 1}]

        if isinstance(items, list) and len(items) > 0:
            # Remove old items and replace with new
            order.items.all().delete()
            created_items = []
            for item in items:
                if isinstance(item, str):
                    prod_id_or_sku = item.strip()
                    qty = 1
                    unit_type = "loose"
                elif isinstance(item, dict):
                    prod_id_or_sku = item.get("product") or item.get("sku") or item.get("product_id") or ""
                    qty_val = item.get("quantity", 1)
                    qty = int(qty_val) if str(qty_val).isdigit() else 1
                    unit_type = str(item.get("unit_type", "loose")).lower()
                else:
                    continue

                if not prod_id_or_sku:
                    continue

                prod = Product.objects.filter(sku__iexact=str(prod_id_or_sku)).first()
                if not prod and str(prod_id_or_sku).isdigit():
                    prod = Product.objects.filter(id=int(prod_id_or_sku)).first()
                if not prod:
                    prod = Product.objects.filter(name__icontains=str(prod_id_or_sku)).first()

                if not prod:
                    return {"status": "error", "message": f"Product '{prod_id_or_sku}' not found while updating order."}

                unit_price = prod.get_price(unit_type)
                taxable_amt = unit_price * Decimal(qty)

                order_item = OrderItem.objects.create(
                    order=order,
                    product=prod,
                    unit_type=unit_type,
                    quantity=qty,
                    unit_price=unit_price,
                    taxable_amount=taxable_amt,
                    gst_rate=prod.gst_rate
                )
                created_items.append({
                    "product_sku": prod.sku,
                    "product_name": prod.name,
                    "unit_type": unit_type,
                    "quantity": qty,
                    "unit_price": float(unit_price),
                    "taxable_amount": float(taxable_amt)
                })

            order.calculate_taxes_and_totals(tenant_state_code=tenant_state_code)
            changes.append(f"Updated line items ({len(created_items)} items in order)")
    else:
        order.save()

    # Recalculate balance difference
    cust = order.customer
    diff = order.total_amount - old_total
    cust.balance_amount += diff
    cust.save()

    pdf_url = f"/api/orders/{order.id}/pdf"
    customer_loc = f"{cust.city}, {cust.state_code}" if cust.city else f"State {cust.state_code}"

    updated_items = [
        {
            "product_sku": item.product.sku,
            "product_name": item.product.name,
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
        "voucher_no": order.voucher_no,
        "order_id": order.id,
        "customer": cust.name,
        "customer_location": customer_loc,
        "order_status": order.status,
        "changes": changes,
        "subtotal": float(order.subtotal),
        "cgst_amount": float(order.cgst_amount),
        "sgst_amount": float(order.sgst_amount),
        "igst_amount": float(order.igst_amount),
        "total_amount": float(order.total_amount),
        "balance_adjustment": float(diff),
        "customer_new_balance": float(cust.balance_amount),
        "pdf_url": pdf_url,
        "invoice_pdf_download_link": f"http://127.0.0.1:8000{pdf_url}",
        "items": updated_items
    }

def tool_list_orders(customer_identifier: str = "", status: str = "") -> dict:
    """Lists active orders, optionally filtered by customer or status."""
    qs = Order.objects.all().order_by("-created_at")
    if customer_identifier:
        qs = qs.filter(customer__name__icontains=customer_identifier) | qs.filter(customer__phone__icontains=customer_identifier)
    if status:
        qs = qs.filter(status__iexact=status)

    orders = [
        {
            "id": o.id,
            "voucher_no": o.voucher_no,
            "customer": o.customer.name,
            "customer_location": f"{o.customer.city}, {o.customer.state_code}" if o.customer.city else o.customer.state_code,
            "status": o.status,
            "order_type": o.order_type,
            "total_amount": float(o.total_amount),
            "item_count": o.items.count()
        }
        for o in qs[:25]
    ]
    return {"status": "success", "count": len(orders), "orders": orders}

def tool_record_payment(customer_identifier: str, amount: float, payment_mode: str = "Cash", voucher_number: str = "", narration: str = "") -> dict:
    """Records a payment received from a customer with disambiguation support."""
    cust, err = resolve_single_customer(customer_identifier)
    if err:
        return err

    pay_amount = Decimal(str(amount))
    if pay_amount <= 0:
        return {"status": "error", "message": "Payment amount must be greater than 0."}

    cash_bank_acct, _ = Account.objects.get_or_create(
        name=f"{payment_mode.capitalize()} Account",
        defaults={"account_group": AccountGroup.CASH if "cash" in payment_mode.lower() else AccountGroup.BANK}
    )

    debtor_acct, _ = Account.objects.get_or_create(
        name=f"Debtor - {cust.name}",
        customer=cust,
        defaults={"account_group": AccountGroup.DEBTORS}
    )

    v_no = voucher_number or f"PAY-{uuid.uuid4().hex[:6].upper()}"

    Ledger.objects.create(
        account=cash_bank_acct,
        against_account=debtor_acct,
        amount=pay_amount,
        entry_type=EntryType.DEBIT,
        voucher_number=v_no,
        narration=narration or f"Payment received from {cust.name} via {payment_mode}"
    )

    Ledger.objects.create(
        account=debtor_acct,
        against_account=cash_bank_acct,
        amount=pay_amount,
        entry_type=EntryType.CREDIT,
        voucher_number=v_no,
        narration=narration or f"Payment credited against {cust.name}"
    )

    cust.balance_amount -= pay_amount
    cust.save()

    customer_loc = f"{cust.city}, {cust.state_code}" if cust.city else f"State {cust.state_code}"
    bal_val = float(cust.balance_amount)
    bal_str = f"₹{abs(bal_val):,.2f} (Advance / Credit)" if bal_val < 0 else f"₹{bal_val:,.2f}"

    return {
        "status": "success",
        "voucher_number": v_no,
        "customer": cust.name,
        "customer_location": customer_loc,
        "amount_paid": float(pay_amount),
        "remaining_balance": bal_val,
        "balance_status": bal_str
    }

def tool_get_customer_ledger(customer_identifier: str) -> dict:
    """Retrieves double-entry ledger history for a customer with location disambiguation."""
    cust, err = resolve_single_customer(customer_identifier)
    if err:
        return err

    debtor_acct = Account.objects.filter(customer=cust).first()
    customer_loc = f"{cust.city}, {cust.state_code}" if cust.city else f"State {cust.state_code}"

    if not debtor_acct:
        return {
            "status": "success",
            "customer": cust.name,
            "customer_location": customer_loc,
            "balance_amount": float(cust.balance_amount),
            "entries": []
        }

    entries = Ledger.objects.filter(account=debtor_acct).order_by("-created_at")[:20]
    result_entries = [
        {
            "id": e.id,
            "voucher_number": e.voucher_number,
            "amount": float(e.amount),
            "entry_type": e.entry_type,
            "narration": e.narration,
            "created_at": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else ""
        }
        for e in entries
    ]

    return {
        "status": "success",
        "customer": cust.name,
        "customer_location": customer_loc,
        "balance_amount": float(cust.balance_amount),
        "entries": result_entries
    }

# --- OpenAI / LiteLLM Schemas ---

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "create_customer",
            "description": "Onboard a new customer with required phone number and location details (city, state_code).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Customer or Business Name"},
                    "phone": {"type": "string", "description": "Customer Phone Number"},
                    "city": {"type": "string", "description": "Customer City (e.g. Kolkata, Jaipur, Delhi)"},
                    "state_code": {"type": "string", "description": "2-digit GST state code (e.g. 08 for RJ, 19 for WB)"},
                    "business_name": {"type": "string", "description": "Trading name"},
                    "email": {"type": "string", "description": "Email address"},
                    "gstin": {"type": "string", "description": "GSTIN number"},
                    "pan": {"type": "string", "description": "PAN number"},
                    "credit_limit": {"type": "number", "description": "Credit limit in INR"},
                    "transport": {"type": "string", "description": "Name of transport/logistics carrier preferred by the customer"},
                    "transport_id": {"type": "integer", "description": "Transport ID if known"}
                },
                "required": ["name", "phone"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_transport",
            "description": "Add a new transport / logistics carrier service (e.g. VRL Logistics, Blue Dart, TCI) so orders can travel through it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Transport or Logistics Company Name"},
                    "phone": {"type": "string", "description": "Phone / Mobile number"},
                    "contact_person": {"type": "string", "description": "Contact person, driver, or booking agent"},
                    "vehicle_number": {"type": "string", "description": "Vehicle / Truck / Lorry number"},
                    "destination_notes": {"type": "string", "description": "Route details or destination hub"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_transports",
            "description": "List all active transport services available for shipping orders and assigning to customers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Optional search term for transport name"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "assign_customer_transport",
            "description": "Assign a preferred transport carrier to a customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_identifier": {"type": "string", "description": "Customer Name, Phone, or ID"},
                    "transport_identifier": {"type": "string", "description": "Transport Name or Transport ID"}
                },
                "required": ["customer_identifier", "transport_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_customers",
            "description": "Search active customers with optional filters for name/phone, city/location, state_code, status, or balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search text for name, business name, or phone"},
                    "city": {"type": "string", "description": "Filter by city e.g. Kolkata, Jaipur"},
                    "state_code": {"type": "string", "description": "Filter by 2-digit GST state code e.g. 08, 19"},
                    "status": {"type": "string", "description": "Filter by status: approved, pending, blocked"},
                    "has_balance_due": {"type": "boolean", "description": "Set to true to show only customers with outstanding balance > 0"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "soft_delete_customer",
            "description": "Soft delete a customer record.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_identifier": {"type": "string", "description": "Customer Name, Phone, or ID"},
                    "customer_id": {"type": "integer", "description": "Customer ID"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_product",
            "description": "Add or update a product in the catalog. All fields including photo/image_url, category, prices, and carton quantity are required.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Unique SKU code e.g. STAT-A4-500"},
                    "name": {"type": "string", "description": "Product Name"},
                    "category": {"type": "string", "description": "Category name e.g. Stationery, Plastics, Packaging"},
                    "image_url": {"type": "string", "description": "Photo / Image URL of the product"},
                    "base_price": {"type": "number", "description": "Base/loose piece price in INR"},
                    "loose_price": {"type": "number", "description": "Loose item price in INR"},
                    "full_carton_price": {"type": "number", "description": "Full carton box price in INR"},
                    "half_carton_price": {"type": "number", "description": "Half carton price in INR"},
                    "full_carton_quantity": {"type": "integer", "description": "Units per carton box e.g. 50"},
                    "gst_rate": {"type": "number", "description": "GST percentage e.g. 18.0"},
                    "hsn_code": {"type": "string", "description": "HSN code e.g. 3926"}
                },
                "required": ["sku", "name", "category", "image_url", "full_carton_price", "full_carton_quantity"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search products in catalog by SKU, name, or category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for SKU, name, or category"},
                    "category": {"type": "string", "description": "Filter by category"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_order",
            "description": "Create a Sales Order or Advance Purchase Order for a customer with items, multi-tier pricing, and tax calculation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_identifier": {"type": "string", "description": "Customer Name, Phone, or ID"},
                    "order_type": {"type": "string", "description": "'sales' or 'advance_purchase'"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product": {"type": "string", "description": "Product SKU or Name"},
                                "quantity": {"type": "integer", "description": "Quantity to order"},
                                "unit_type": {"type": "string", "description": "'loose', 'full_carton', 'half_carton', or 'stuffed'"}
                            },
                            "required": ["product", "quantity"]
                        }
                    }
                },
                "required": ["customer_identifier", "items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_order",
            "description": "Edit an existing order: modify status, update line items/quantities, recalculate taxes and totals, and update customer balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_identifier": {"type": "string", "description": "Order Voucher No (e.g. INV-1234ABCD, ORD-2026-1234) or Order ID"},
                    "status": {"type": "string", "description": "New status: draft, placed, packed, dispatched, delivered, cancelled"},
                    "items": {
                        "type": "array",
                        "description": "New complete list of items for the order (if editing items)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product": {"type": "string", "description": "Product SKU or Name"},
                                "quantity": {"type": "integer", "description": "Quantity to order"},
                                "unit_type": {"type": "string", "description": "'loose', 'full_carton', 'half_carton'"}
                            },
                            "required": ["product", "quantity"]
                        }
                    }
                },
                "required": ["order_identifier"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_orders",
            "description": "List existing orders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_identifier": {"type": "string", "description": "Filter by customer name/phone"},
                    "status": {"type": "string", "description": "Filter by status e.g. placed, packed, dispatched"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "record_payment",
            "description": "Record a payment received from a customer with double-entry accounting entries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_identifier": {"type": "string", "description": "Customer Name, Phone, or ID"},
                    "amount": {"type": "number", "description": "Amount received in INR"},
                    "payment_mode": {"type": "string", "description": "'Cash', 'Bank', 'UPI', 'Cheque'"},
                    "voucher_number": {"type": "string", "description": "Optional payment voucher ref"},
                    "narration": {"type": "string", "description": "Payment note"}
                },
                "required": ["customer_identifier", "amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_ledger",
            "description": "View double-entry ledger statement and balance for a customer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_identifier": {"type": "string", "description": "Customer Name, Phone, or ID"}
                },
                "required": ["customer_identifier"]
            }
        }
    }
]

# --- Native Anthropic SDK Tool Schema ---

ANTHROPIC_TOOLS_SCHEMA = [
    {
        "name": t["function"]["name"],
        "description": t["function"]["description"],
        "input_schema": t["function"]["parameters"]
    }
    for t in TOOLS_SCHEMA
]

EXECUTE_TOOL_MAP = {
    "create_customer": tool_create_customer,
    "search_customers": tool_search_customers,
    "soft_delete_customer": tool_soft_delete_customer,
    "create_product": tool_create_product,
    "search_products": tool_search_products,
    "create_order": tool_create_order,
    "edit_order": tool_edit_order,
    "list_orders": tool_list_orders,
    "record_payment": tool_record_payment,
    "get_customer_ledger": tool_get_customer_ledger,
    "create_transport": tool_create_transport,
    "list_transports": tool_list_transports,
    "assign_customer_transport": tool_assign_customer_transport,
}

LANGCHAIN_TOOLS = [
    tool(func) for func in EXECUTE_TOOL_MAP.values()
]
