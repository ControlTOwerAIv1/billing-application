# Module: Orders & Sales

## Database Schema (`core_order` / `sales_order` table)
Primary table for customer orders.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Order ID |
| `voucher_no` | VARCHAR(50) | UNIQUE, NOT NULL | Sequential Order Invoice Number |
| `customer_id` | INTEGER | NOT NULL | Foreign key to `core_customer.id` |
| `subtotal` | DECIMAL(12,2) | NOT NULL | Taxable amount before GST |
| `cgst_amount` | DECIMAL(12,2) | DEFAULT 0.00 | CGST tax amount |
| `sgst_amount` | DECIMAL(12,2) | DEFAULT 0.00 | SGST tax amount |
| `igst_amount` | DECIMAL(12,2) | DEFAULT 0.00 | IGST tax amount |
| `total_amount` | DECIMAL(12,2) | NOT NULL | Grand total after GST |
| `status` | VARCHAR(20) | DEFAULT 'placed' | Status: draft, placed, packed, dispatched, delivered, cancelled |
| `soft_deleted` | INTEGER | DEFAULT 0 | 0 = Active, 1 = Soft Deleted |

---

## Order Workflow & Edit Rules
1. **Tax Calculation (GST)**:
   - Intra-State orders (`customer.state_code == seller.state_code`): CGST + SGST (half GST rate each).
   - Inter-State orders (`customer.state_code != seller.state_code`): IGST (full GST rate).
2. **Order Edit Flow**:
   - Order items, quantities, unit types, and statuses can be updated via `edit_order`.
   - When order items are updated, taxes (CGST, SGST, IGST), subtotal, and total amount must be recalculated server-side.
   - Customer's running balance must be adjusted by the difference: `customer.balance_amount += (new_total - old_total)`.
   - An updated Tax Invoice PDF is automatically available at `/api/orders/<id>/pdf`.
3. **Ambiguity Handling**:
   - If an order edit or creation command lacks specific item quantities, product SKUs, or customer identities, clarify before executing.
