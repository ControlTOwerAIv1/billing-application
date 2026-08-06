from ninja import NinjaAPI, Schema
from typing import List, Optional
from apps.core.models import Customer, Product, Order
from backend.agent.tools import (
    tool_create_customer, tool_search_customers, tool_soft_delete_customer,
    tool_create_product, tool_search_products, tool_create_order, tool_list_orders,
    tool_record_payment, tool_get_customer_ledger
)

api = NinjaAPI(title="OrderBot AI Supply Chain API", version="2.0.0")

class CustomerSchema(Schema):
    id: int
    name: str
    phone: str
    state_code: str
    credit_limit: float
    balance_amount: float
    status: str

class CreateCustomerSchema(Schema):
    name: str
    phone: str
    state_code: Optional[str] = "08"
    business_name: Optional[str] = ""
    email: Optional[str] = ""
    gstin: Optional[str] = ""
    pan: Optional[str] = ""
    credit_limit: Optional[float] = 0.0

class ProductSchema(Schema):
    id: int
    sku: str
    name: str
    category: str
    loose_price: float
    full_carton_price: float
    gst_rate: float

class CreateProductSchema(Schema):
    sku: str
    name: str
    category: Optional[str] = "General"
    loose_price: Optional[float] = 0.0
    full_carton_price: Optional[float] = 0.0
    full_carton_quantity: Optional[int] = 1
    gst_rate: Optional[float] = 18.0

class OrderItemInputSchema(Schema):
    product: str
    quantity: int
    unit_type: Optional[str] = "loose"

class CreateOrderSchema(Schema):
    customer_identifier: str
    items: List[OrderItemInputSchema]
    order_type: Optional[str] = "sales"

class RecordPaymentSchema(Schema):
    customer_identifier: str
    amount: float
    payment_mode: Optional[str] = "Cash"
    narration: Optional[str] = ""

@api.get("/customers")
def list_customers(request, query: Optional[str] = ""):
    return tool_search_customers(query=query)

@api.post("/customers")
def create_customer(request, payload: CreateCustomerSchema):
    return tool_create_customer(**payload.dict())

@api.delete("/customers/{customer_id}")
def delete_customer(request, customer_id: int):
    return tool_soft_delete_customer(customer_id=customer_id)

@api.get("/products")
def list_products(request, query: Optional[str] = ""):
    return tool_search_products(query=query)

@api.post("/products")
def create_product(request, payload: CreateProductSchema):
    return tool_create_product(**payload.dict())

@api.get("/orders")
def list_orders(request, customer: Optional[str] = "", status: Optional[str] = ""):
    return tool_list_orders(customer_identifier=customer, status=status)

@api.post("/orders")
def create_order(request, payload: CreateOrderSchema):
    items_list = [item.dict() for item in payload.items]
    return tool_create_order(
        customer_identifier=payload.customer_identifier,
        items=items_list,
        order_type=payload.order_type
    )

@api.post("/payments")
def record_payment(request, payload: RecordPaymentSchema):
    return tool_record_payment(**payload.dict())

@api.get("/customers/{customer_id}/ledger")
def get_customer_ledger(request, customer_id: str):
    return tool_get_customer_ledger(customer_identifier=customer_id)
