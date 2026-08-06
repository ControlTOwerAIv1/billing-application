import os
import sys
import json
import uuid
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from apps.core.models import (
    Customer, Product, Order, OrderItem, Warehouse, WarehouseProduct,
    PurchaseOrder, PoItem, Account, Ledger, CustomerStatus, OrderStatus, OrderType, PaymentStatus, AccountGroup, EntryType
)
from backend.db import execute_sql_query

MODULES_DIR = BASE_DIR / "modules"

# --- Tool Implementations ---

def tool_create_customer(name: str, phone: str, state_code: str = "08", business_name: str = "", email: str = "", gstin: str = "", pan: str = "", credit_limit: float = 0.0) -> dict:
    """Creates a new customer record and automatically creates a linked Account in Debtors."""
    if not name:
        return {"status": "error", "message": "Customer name is required."}
    if not phone:
        return {"status": "error", "message": "Phone number is required."}

    customer, created = Customer.objects.get_or_create(
        phone=phone,
        defaults={
            "name": name,
            "business_name": business_name,
            "email": email,
            "state_code": state_code,
            "gstin": gstin,
            "pan": pan,
            "credit_limit": Decimal(str(credit_limit)),
            "status": CustomerStatus.APPROVED
        }
    )
    if not created:
        customer.name = name
        if business_name: customer.business_name = business_name
        if email: customer.email = email
        if state_code: customer.state_code = state_code
        if gstin: customer.gstin = gstin
        if pan: customer.pan = pan
        if credit_limit > 0: customer.credit_limit = Decimal(str(credit_limit))
        customer.save()

    # Ensure linked Debtors Account exists
    Account.objects.get_or_create(
        name=f"Debtor - {customer.name}",
        customer=customer,
        defaults={"account_group": AccountGroup.DEBTORS}
    )

    return {
        "status": "success",
        "action": "created" if created else "updated",
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "state_code": customer.state_code,
            "credit_limit": float(customer.credit_limit),
            "balance_amount": float(customer.balance_amount)
        }
    }

def tool_search_customers(query: str = "") -> dict:
    """Searches active customers by name, phone, or business name."""
    qs = Customer.objects.all()
    if query:
        qs = qs.filter(name__icontains=query) | qs.filter(phone__icontains=query) | qs.filter(business_name__icontains=query)

    customers = [
        {
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "business_name": c.business_name,
            "state_code": c.state_code,
            "credit_limit": float(c.credit_limit),
            "balance_amount": float(c.balance_amount),
            "status": c.status
        }
        for c in qs[:20]
    ]
    return {"status": "success", "count": len(customers), "customers": customers}

def tool_soft_delete_customer(customer_id: int = None, name: str = "") -> dict:
    """Soft deletes a customer record."""
    if customer_id:
        qs = Customer.objects.filter(id=customer_id)
    elif name:
        qs = Customer.objects.filter(name__icontains=name)
    else:
        return {"status": "error", "message": "Specify customer_id or name to delete."}

    count = 0
    deleted_names = []
    for cust in qs:
        deleted_names.append(cust.name)
        cust.delete()
        count += 1

    return {"status": "success", "deleted_count": count, "deleted_customers": deleted_names}

def tool_create_product(sku: str, name: str, category: str = "General", base_price: float = 0.0, loose_price: float = 0.0, full_carton_price: float = 0.0, half_carton_price: float = 0.0, full_carton_quantity: int = 1, gst_rate: float = 18.0) -> dict:
    """Creates or updates a product with multi-tier pricing."""
    product, created = Product.objects.get_or_create(
        sku=sku,
        defaults={
            "name": name,
            "category": category,
            "base_price": Decimal(str(base_price or loose_price)),
            "loose_price": Decimal(str(loose_price or base_price)),
            "full_carton_price": Decimal(str(full_carton_price)),
            "half_carton_price": Decimal(str(half_carton_price)),
            "full_carton_quantity": full_carton_quantity,
            "gst_rate": Decimal(str(gst_rate))
        }
    )
    return {
        "status": "success",
        "action": "created" if created else "already_exists",
        "product": {
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
            "loose_price": float(product.loose_price),
            "full_carton_price": float(product.full_carton_price),
            "gst_rate": float(product.gst_rate)
        }
    }

def tool_search_products(query: str = "") -> dict:
    """Searches active products by SKU, name, or category."""
    qs = Product.objects.filter(is_active=True)
    if query:
        qs = qs.filter(sku__icontains=query) | qs.filter(name__icontains=query) | qs.filter(category__icontains=query)

    products = [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "category": p.category,
            "base_price": float(p.base_price),
            "loose_price": float(p.loose_price),
            "full_carton_price": float(p.full_carton_price),
            "full_carton_quantity": p.full_carton_quantity,
            "gst_rate": float(p.gst_rate)
        }
        for p in qs[:20]
    ]
    return {"status": "success", "count": len(products), "products": products}

def tool_create_order(customer_identifier: str, items: list, order_type: str = "sales", tenant_state_code: str = "08") -> dict:
    """
    Creates an Order with line items, multi-tier pricing, tax calculation (CGST+SGST vs IGST),
    and credit limit verification.
    """
    # 1. Resolve Customer
    cust = Customer.objects.filter(name__icontains=customer_identifier).first()
    if not cust and customer_identifier.isdigit():
        cust = Customer.objects.filter(id=int(customer_identifier)).first()
    if not cust:
        cust = Customer.objects.filter(phone__icontains=customer_identifier).first()

    if not cust:
        return {"status": "error", "message": f"Customer matching '{customer_identifier}' not found."}

    # 2. Generate Voucher Number
    voucher_no = f"INV-{uuid.uuid4().hex[:8].upper()}"

    # 3. Create Order Shell
    o_type = OrderType.ADVANCE_PURCHASE if "advance" in order_type.lower() else OrderType.SALES
    order = Order.objects.create(
        customer=cust,
        voucher_no=voucher_no,
        order_type=o_type,
        status=OrderStatus.PLACED
    )

    # 4. Add Line Items
    created_items = []

    for item in items:
        prod_id_or_sku = item.get("product") or item.get("sku") or item.get("product_id")
        qty = int(item.get("quantity", 1))
        unit_type = item.get("unit_type", "loose").lower()

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

    # 5. Calculate Taxes & Grand Total
    order.calculate_taxes_and_totals(tenant_state_code=tenant_state_code)

    # 6. Update Customer Running Balance
    cust.balance_amount += order.total_amount
    cust.save()

    # 7. Verify Credit Limit
    credit_warning = None
    if cust.credit_limit > Decimal("0.00"):
        if cust.balance_amount > cust.credit_limit:
            credit_warning = f"WARNING: Customer balance (Rs.{float(cust.balance_amount):.2f}) exceeds credit limit (Rs.{float(cust.credit_limit):.2f})."

    return {
        "status": "success",
        "voucher_no": order.voucher_no,
        "customer": cust.name,
        "order_type": order.order_type,
        "subtotal": float(order.subtotal),
        "cgst_amount": float(order.cgst_amount),
        "sgst_amount": float(order.sgst_amount),
        "igst_amount": float(order.igst_amount),
        "total_amount": float(order.total_amount),
        "credit_warning": credit_warning,
        "items": created_items
    }

def tool_list_orders(customer_identifier: str = "", status: str = "") -> dict:
    """Lists active orders, optionally filtered by customer or status."""
    qs = Order.objects.all()
    if customer_identifier:
        qs = qs.filter(customer__name__icontains=customer_identifier) | qs.filter(customer__phone__icontains=customer_identifier)
    if status:
        qs = qs.filter(status__iexact=status)

    orders = [
        {
            "id": o.id,
            "voucher_no": o.voucher_no,
            "customer": o.customer.name,
            "status": o.status,
            "order_type": o.order_type,
            "total_amount": float(o.total_amount),
            "item_count": o.items.count()
        }
        for o in qs[:20]
    ]
    return {"status": "success", "count": len(orders), "orders": orders}

def tool_record_payment(customer_identifier: str, amount: float, payment_mode: str = "Cash", voucher_number: str = "", narration: str = "") -> dict:
    """Records a payment received from a customer, creates double-entry ledger entries, and reduces customer balance."""
    cust = Customer.objects.filter(name__icontains=customer_identifier).first()
    if not cust and customer_identifier.isdigit():
        cust = Customer.objects.filter(id=int(customer_identifier)).first()
    if not cust:
        return {"status": "error", "message": f"Customer '{customer_identifier}' not found."}

    pay_amount = Decimal(str(amount))
    if pay_amount <= 0:
        return {"status": "error", "message": "Payment amount must be greater than 0."}

    # Cash / Bank Account
    cash_bank_acct, _ = Account.objects.get_or_create(
        name=f"{payment_mode.capitalize()} Account",
        defaults={"account_group": AccountGroup.CASH if "cash" in payment_mode.lower() else AccountGroup.BANK}
    )

    # Customer Debtor Account
    debtor_acct, _ = Account.objects.get_or_create(
        name=f"Debtor - {cust.name}",
        customer=cust,
        defaults={"account_group": AccountGroup.DEBTORS}
    )

    # Debit Cash/Bank, Credit Customer Debtor
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

    # Reduce Customer balance
    cust.balance_amount = max(Decimal("0.00"), cust.balance_amount - pay_amount)
    cust.save()

    return {
        "status": "success",
        "voucher_number": v_no,
        "customer": cust.name,
        "amount_paid": float(pay_amount),
        "remaining_balance": float(cust.balance_amount)
    }

def tool_get_customer_ledger(customer_identifier: str) -> dict:
    """Retrieves double-entry ledger history for a customer."""
    cust = Customer.objects.filter(name__icontains=customer_identifier).first()
    if not cust:
        return {"status": "error", "message": f"Customer '{customer_identifier}' not found."}

    debtor_acct = Account.objects.filter(customer=cust).first()
    if not debtor_acct:
        return {"status": "success", "customer": cust.name, "balance_amount": float(cust.balance_amount), "entries": []}

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
        "balance_amount": float(cust.balance_amount),
        "entries": result_entries
    }

# --- OpenAI / LiteLLM JSON Tool Definitions ---

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "create_customer",
            "description": "Onboard a new customer or update existing customer details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Customer or Business Name"},
                    "phone": {"type": "string", "description": "Customer Phone Number"},
                    "state_code": {"type": "string", "description": "2-digit GST state code (e.g. 08 for RJ, 19 for WB)"},
                    "business_name": {"type": "string", "description": "Trading name"},
                    "email": {"type": "string", "description": "Email address"},
                    "gstin": {"type": "string", "description": "GSTIN number"},
                    "pan": {"type": "string", "description": "PAN number"},
                    "credit_limit": {"type": "number", "description": "Credit limit in INR"}
                },
                "required": ["name", "phone"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_customers",
            "description": "Search active customers by name, phone, or business name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
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
                    "customer_id": {"type": "integer", "description": "Customer ID"},
                    "name": {"type": "string", "description": "Customer Name"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_product",
            "description": "Add or update a product in the catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Unique SKU"},
                    "name": {"type": "string", "description": "Product Name"},
                    "category": {"type": "string", "description": "Category name"},
                    "base_price": {"type": "number", "description": "Base price"},
                    "loose_price": {"type": "number", "description": "Loose item price"},
                    "full_carton_price": {"type": "number", "description": "Full carton box price"},
                    "half_carton_price": {"type": "number", "description": "Half carton price"},
                    "full_carton_quantity": {"type": "integer", "description": "Units per carton"},
                    "gst_rate": {"type": "number", "description": "GST percentage e.g. 18.0"}
                },
                "required": ["sku", "name"]
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
                    "query": {"type": "string", "description": "Search query"}
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
            "name": "list_orders",
            "description": "List existing orders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_identifier": {"type": "string", "description": "Filter by customer"},
                    "status": {"type": "string", "description": "Filter by status e.g. placed, packed"}
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
                    "customer_identifier": {"type": "string", "description": "Customer Name or Phone"},
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
                    "customer_identifier": {"type": "string", "description": "Customer Name or Phone"}
                },
                "required": ["customer_identifier"]
            }
        }
    }
]

EXECUTE_TOOL_MAP = {
    "create_customer": tool_create_customer,
    "search_customers": tool_search_customers,
    "soft_delete_customer": tool_soft_delete_customer,
    "create_product": tool_create_product,
    "search_products": tool_search_products,
    "create_order": tool_create_order,
    "list_orders": tool_list_orders,
    "record_payment": tool_record_payment,
    "get_customer_ledger": tool_get_customer_ledger,
}
