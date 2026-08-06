import os
import sqlite3
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "orderbot.db"
SQL_DUMP_PATH = BASE_DIR / "wholesalerdistributordb_20260729.sql"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Initializes local SQLite database with core tables and ensures soft_deleted enforcement.
    """
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `account` (
        `id` INTEGER PRIMARY KEY AUTOINCREMENT,
        `account` TEXT NOT NULL,
        `phone` TEXT,
        `state_code` TEXT DEFAULT '08',
        `balance_amount` DECIMAL(15,2) DEFAULT 0.00,
        `status` INTEGER DEFAULT 1,
        `soft_deleted` INTEGER DEFAULT 0,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS `sales_order` (
        `id` INTEGER PRIMARY KEY AUTOINCREMENT,
        `voucher_no` TEXT NOT NULL,
        `account_id` INTEGER NOT NULL,
        `total_amount` DECIMAL(15,2) NOT NULL DEFAULT 0.00,
        `status` TEXT DEFAULT 'placed',
        `soft_deleted` INTEGER DEFAULT 0,
        `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()

    # Ensure soft_deleted column exists on all created tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    all_tables = [row["name"] for row in cursor.fetchall()]

    for table in all_tables:
        cursor.execute(f"PRAGMA table_info(`{table}`);")
        columns = [col["name"] for col in cursor.fetchall()]
        if "soft_deleted" not in columns:
            try:
                cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN soft_deleted INTEGER DEFAULT 0;")
            except Exception:
                pass
    
    conn.commit()
    conn.close()

def execute_sql_query(query: str, params: tuple = ()) -> dict:
    """
    Executes a SQL query with guardrails:
    1. Converts hard DELETE queries to UPDATE ... SET soft_deleted = 1
    2. Automatically appends soft_deleted = 0 to SELECT queries if not in WHERE clause
    """
    conn = get_connection()
    cursor = conn.cursor()

    cleaned_query = query.strip()
    query_upper = cleaned_query.upper()

    # Guardrail 1: Convert DELETE to Soft Delete
    if query_upper.startswith("DELETE FROM"):
        match = re.match(r"DELETE\s+FROM\s+[`'\"]?(\w+)[`'\"]?\s+(WHERE\s+.*)", cleaned_query, re.IGNORECASE)
        if match:
            table_name = match.group(1)
            where_clause = match.group(2)
            cleaned_query = f"UPDATE `{table_name}` SET soft_deleted = 1 {where_clause}"
        else:
            return {"status": "error", "error": "DELETE statements without a WHERE clause are prohibited."}

    # Guardrail 2: Enforce soft_deleted = 0 on SELECT queries if not present in WHERE clause
    if query_upper.startswith("SELECT"):
        where_match = re.search(r"(?i)\bWHERE\b", cleaned_query)
        if where_match:
            where_pos = where_match.start()
            where_clause_part = cleaned_query[where_pos:]
            if "soft_deleted" not in where_clause_part.lower():
                cleaned_query = re.sub(r"(?i)\bWHERE\b", "WHERE soft_deleted = 0 AND ", cleaned_query, count=1)
        else:
            if "ORDER BY" in query_upper:
                cleaned_query = re.sub(r"(?i)\bORDER BY\b", "WHERE soft_deleted = 0 ORDER BY ", cleaned_query, count=1)
            elif "LIMIT" in query_upper:
                cleaned_query = re.sub(r"(?i)\bLIMIT\b", "WHERE soft_deleted = 0 LIMIT ", cleaned_query, count=1)
            else:
                cleaned_query += " WHERE soft_deleted = 0"

    try:
        cursor.execute(cleaned_query, params)
        if query_upper.startswith("SELECT"):
            rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return {"status": "success", "type": "select", "query": cleaned_query, "data": rows, "count": len(rows)}
        else:
            conn.commit()
            affected = cursor.rowcount
            conn.close()
            return {"status": "success", "type": "mutation", "query": cleaned_query, "affected_rows": affected}
    except Exception as e:
        conn.close()
        return {"status": "error", "query": cleaned_query, "error": str(e)}

if __name__ == "__main__":
    init_db()
