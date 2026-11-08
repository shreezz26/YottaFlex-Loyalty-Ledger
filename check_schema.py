from app.database import get_connection

connection = get_connection()

tables = [
    "expiry_batches",
    "point_lots",
    "redemptions",
    "points_transactions",
    "loyalty_accounts"
]

for table in tables:
    print(f"\n--- {table} ---")

    columns = connection.execute(
        f"PRAGMA table_info({table})"
    ).fetchall()

    for column in columns:
        print(column["name"], column["type"])

connection.close()