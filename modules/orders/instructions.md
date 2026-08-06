# Module: Orders & Sales

## Database Schema (`sales_order` table)
Primary table for customer orders.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Order ID |
| `voucher_no` | VARCHAR(100) | NOT NULL | Sequential Order Invoice Number |
| `account_id` | INTEGER | NOT NULL | Foreign key to `account.id` |
| `total_amount` | DECIMAL(15,2) | NOT NULL | Grand total after GST |
| `status` | VARCHAR(20) | DEFAULT 'placed' | Status: placed, packed, dispatched, delivered |
| `soft_deleted` | INTEGER | DEFAULT 0 | 0 = Active, 1 = Soft Deleted |

---

## Order Workflow Rules
1. Every order must calculate GST:
   - CGST (9%) + SGST (9%) for Intra-State orders (`customer.state_code == seller.state_code`).
   - IGST (18%) for Inter-State orders (`customer.state_code != seller.state_code`).
2. Order deletion must use `UPDATE sales_order SET soft_deleted = 1 WHERE voucher_no = '...'`.
3. All order list queries must include `WHERE soft_deleted = 0`.
