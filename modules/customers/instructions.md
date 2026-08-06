# Module: Customers & Accounts

## Database Schema (`account` table)
Primary table for buyers, shops, retailers, and account masters.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique Customer ID |
| `account` | VARCHAR(100) | NOT NULL | Customer / Shop / Business Name |
| `phone` | VARCHAR(20) | NOT NULL | Customer Phone Number (Required for onboarding) |
| `state_code` | VARCHAR(2) | NOT NULL DEFAULT '08' | 2-digit GST state code (e.g. 08 for RJ, 27 for MH, 19 for WB) |
| `balance_amount` | DECIMAL(15,2) | DEFAULT 0.00 | Running ledger balance |
| `status` | INTEGER | NOT NULL DEFAULT 1 | 1 = Approved, 0 = Pending Approval |
| `soft_deleted` | INTEGER | DEFAULT 0 | 0 = Active, 1 = Soft Deleted |

---
   
## Onboarding & Disambiguation Rules
1. When asked to create a customer (e.g. *"Create customer Raju Bhai from Kolkata"*):
   - Check if required `NOT NULL` fields are present (`account`, `phone`, `state_code`).
   - If `phone` is missing, **ask the user** for the phone number before running the SQL INSERT statement.
   - Default `state_code` can be inferred from city (e.g., Kolkata → West Bengal → State Code `19`).

2. When asked to delete a customer:
   - Perform a **Soft Delete**: `UPDATE account SET soft_deleted = 1 WHERE account = 'Raju Bhai'`.
   - Never execute `DELETE FROM account`.

3. Querying active customers:
   - Always filter with `WHERE soft_deleted = 0`.


Rule: Always confirm credit limit before approving order.


Rule: Always confirm credit limit before approving order.


Rule: Always confirm credit limit before approving order.


Rule: Always confirm credit limit before approving order.


Rule: Always confirm credit limit before approving order.
