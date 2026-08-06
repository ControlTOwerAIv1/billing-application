import os
import sys
import django
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "orderbot.settings")
django.setup()

from apps.core.models import Customer, Product, Order, OrderItem, OrderType, OrderStatus
from backend.agent.tools import (
    tool_create_customer, tool_search_customers, tool_soft_delete_customer,
    tool_create_product, tool_search_products, tool_create_order, tool_list_orders
)

def run_tests():
    print("=" * 65)
    print("      RUNNING PHASE 1 CORE FUNCTIONALITY TEST SUITE       ")
    print("=" * 65)

    # 1. Test Customer Creation
    print("\n[1] Testing Customer Creation...")
    cust_res = tool_create_customer(
        name="Raju Wholesalers",
        phone="+919876543210",
        state_code="08", # RJ (Intra-state with tenant)
        credit_limit=50000.0,
        business_name="Raju Toys Pvt Ltd"
    )
    print("Result:", cust_res)
    assert cust_res["status"] == "success"

    cust2_res = tool_create_customer(
        name="Kolkata Traders",
        phone="+919123456789",
        state_code="19", # WB (Inter-state with tenant)
        credit_limit=10000.0
    )
    print("Result:", cust2_res)
    assert cust2_res["status"] == "success"

    # 2. Test Product Creation with Multi-tier Pricing
    print("\n[2] Testing Multi-tier Product Creation...")
    prod_res = tool_create_product(
        sku="TOY-ROBOT-01",
        name="Remote Control Robot",
        category="Electronics",
        loose_price=200.0,
        full_carton_price=4000.0,
        half_carton_price=2100.0,
        full_carton_quantity=24,
        gst_rate=18.0
    )
    print("Result:", prod_res)
    assert prod_res["status"] == "success"

    # 3. Test Intra-State Order Placement (CGST 9% + SGST 9%)
    print("\n[3] Testing Intra-State Sales Order Placement (RJ -> RJ)...")
    order_res_intra = tool_create_order(
        customer_identifier="Raju Wholesalers",
        order_type="sales",
        tenant_state_code="08",
        items=[
            {"product": "TOY-ROBOT-01", "quantity": 1, "unit_type": "full_carton"},
            {"product": "TOY-ROBOT-01", "quantity": 2, "unit_type": "loose"}
        ]
    )
    print("Intra-State Order Output:")
    print(f"  Voucher No: {order_res_intra['voucher_no']}")
    print(f"  Subtotal: Rs.{order_res_intra['subtotal']}")
    print(f"  CGST (9%): Rs.{order_res_intra['cgst_amount']}")
    print(f"  SGST (9%): Rs.{order_res_intra['sgst_amount']}")
    print(f"  IGST (0%): Rs.{order_res_intra['igst_amount']}")
    print(f"  Total Amount: Rs.{order_res_intra['total_amount']}")

    assert order_res_intra["status"] == "success"
    assert order_res_intra["cgst_amount"] > 0
    assert order_res_intra["sgst_amount"] > 0
    assert order_res_intra["igst_amount"] == 0

    # 4. Test Inter-State Order Placement (RJ -> WB)
    print("\n[4] Testing Inter-State Sales Order Placement (RJ -> WB)...")
    order_res_inter = tool_create_order(
        customer_identifier="Kolkata Traders",
        order_type="sales",
        tenant_state_code="08",
        items=[
            {"product": "TOY-ROBOT-01", "quantity": 2, "unit_type": "full_carton"}
        ]
    )
    print("Inter-State Order Output:")
    print(f"  Voucher No: {order_res_inter['voucher_no']}")
    print(f"  Subtotal: Rs.{order_res_inter['subtotal']}")
    print(f"  CGST (0%): Rs.{order_res_inter['cgst_amount']}")
    print(f"  SGST (0%): Rs.{order_res_inter['sgst_amount']}")
    print(f"  IGST (18%): Rs.{order_res_inter['igst_amount']}")
    print(f"  Total Amount: Rs.{order_res_inter['total_amount']}")

    assert order_res_inter["status"] == "success"
    assert order_res_inter["igst_amount"] > 0
    assert order_res_inter["cgst_amount"] == 0

    # 5. Test Soft Delete
    print("\n[5] Testing Soft Delete Interceptor...")
    del_res = tool_soft_delete_customer(name="Kolkata Traders")
    print("Soft Delete Output:", del_res)
    assert del_res["status"] == "success"

    active_custs = tool_search_customers("Kolkata Traders")
    print("Search active customers after soft delete:", active_custs)
    assert active_custs["count"] == 0

    print("\n" + "=" * 65)
    print("     ALL PHASE 1 CORE FUNCTIONALITY TESTS PASSED SUCCESSFULLY!    ")
    print("=" * 65)

if __name__ == "__main__":
    run_tests()
