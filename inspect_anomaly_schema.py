from app.database import get_connection

TABLES = [
    "customers",
    "loyalty_accounts",
    "tiers",
    "orders",
    "points_transactions",
    "point_lots",
    "redemptions",
    "expiry_batches",
    "returns",
    "audit_issues",
]

connection = get_connection()

try:
    for table in TABLES:
        print(f"\n{'=' * 55}")
        print(f"TABLE: {table}")
        print("=" * 55)

        result = connection.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()

        if not result:
            print("Table not found.")
            continue

        for column in result:
            print(
                f"Column: {column['name']} | "
                f"Type: {column['type']} | "
                f"Not Null: {column['notnull']} | "
                f"Primary Key: {column['pk']}"
            )

finally:
    connection.close()