# Module: Customers & Accounts

## Database Schema (`core_customer` / `account` table)
Primary table for buyers, shops, retailers, and account masters.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique Customer ID |
| `name` | VARCHAR(150) | NOT NULL | Customer / Shop / Business Name |
| `phone` | VARCHAR(20) | NOT NULL | Customer Phone Number (Required for onboarding) |
| `city` | VARCHAR(100) | NULLABLE | Customer City / Town (e.g. Kolkata, Jaipur, Delhi) |
| `state_code` | VARCHAR(2) | NOT NULL DEFAULT '08' | 2-digit GST state code (e.g. 08 for RJ, 27 for MH, 19 for WB) |
| `balance_amount` | DECIMAL(15,2) | DEFAULT 0.00 | Running ledger balance |
| `credit_limit` | DECIMAL(15,2) | DEFAULT 0.00 | Maximum credit limit allowed |
| `status` | VARCHAR(20) | DEFAULT 'approved' | approved, pending, blocked |
| `soft_deleted` | INTEGER | DEFAULT 0 | 0 = Active, 1 = Soft Deleted |

---
   
## Customer Query & Filter Rules
1. When asked to list customers without specific criteria:
   - Ask the user which filter they want to apply:
     - **Location / City** (e.g., Kolkata, Jaipur)
     - **State** (e.g., 08 for Rajasthan, 19 for West Bengal)
     - **Outstanding Balance** (buyers with pending dues)
     - **Account Status** (Approved, Pending, Blocked)
     - Or confirm if they want the complete active list.

2. Location-aware Identification & Disambiguation:
   - In all conversation outputs, include customer location: e.g., *"Raj Wholesalers from Kolkata (WB)"*.
   - If multiple customers exist with the same name:
     - **NEVER** guess or pick the first record.
     - **Ask for clarification**: *"Did you mean Raj Wholesalers from Kolkata (WB, Phone: +91-9876543210) or Raj Wholesalers from Jaipur (RJ, Phone: +91-9123456789)?"*

3. Onboarding & Deletion Rules:
   - Required fields for customer onboarding: `name`, `phone`, and `state_code` / `city`.
   - Perform soft deletes (`soft_deleted = 1`) when deleting customers.
   - Always warn if an order or transaction exceeds the customer's credit limit.
