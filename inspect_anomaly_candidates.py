import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "loyalty_anomaly.db"

connection = sqlite3.connect(DB_PATH)
connection.row_factory = sqlite3.Row

queries = {
    "CUSTOMERS": "SELECT COUNT(*) AS total FROM customers",
    "ACCOUNTS": "SELECT COUNT(*) AS total FROM loyalty_accounts",
    "ORDERS": "SELECT COUNT(*) AS total FROM orders",
    "TRANSACTIONS": "SELECT COUNT(*) AS total FROM points_transactions",
    "POINT LOTS": "SELECT COUNT(*) AS total FROM point_lots",
    "REDEMPTIONS": "SELECT COUNT(*) AS total FROM redemptions",
    "EXPIRY BATCHES": "SELECT COUNT(*) AS total FROM expiry_batches",
    "RETURNS": "SELECT COUNT(*) AS total FROM returns",
}

try:
    print("ANOMALY DATABASE RECORD COUNTS")
    print("=" * 45)

    for name, query in queries.items():
        total = connection.execute(query).fetchone()["total"]
        print(f"{name}: {total}")

    print("\nCANDIDATE RECORDS")
    print("=" * 45)

    candidates = connection.execute("""
        SELECT
            a.account_id,
            a.stored_balance,
            a.qualifying_spend,
            o.order_id,
            o.gross_amount,
            o.discount_amount,
            o.net_amount
        FROM loyalty_accounts a
        LEFT JOIN customers c
            ON c.customer_id = a.customer_id
        LEFT JOIN orders o
            ON o.customer_id = a.customer_id
        WHERE a.account_status = 'ACTIVE'
        LIMIT 10
    """).fetchall()

    for row in candidates:
        print(dict(row))

finally:
    connection.close()