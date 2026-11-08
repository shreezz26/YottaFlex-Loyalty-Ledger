import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "loyalty_anomaly.db"

connection = sqlite3.connect(DB_PATH)
connection.row_factory = sqlite3.Row

try:
    print("\n1. AVAILABLE TIERS")
    print("=" * 60)

    tiers = connection.execute("""
        SELECT tier_id, tier_name, minimum_spend, earning_rate
        FROM tiers
        ORDER BY minimum_spend
    """).fetchall()

    for tier in tiers:
        print(dict(tier))

    print("\n2. RETURN SCENARIO CANDIDATES")
    print("=" * 60)

    returns = connection.execute("""
        SELECT
            o.order_id,
            o.customer_id,
            o.gross_amount,
            o.discount_amount,
            o.net_amount,
            o.order_status,
            p.transaction_id,
            p.points
        FROM orders o
        JOIN loyalty_accounts a
            ON a.customer_id = o.customer_id
        JOIN points_transactions p
            ON p.order_id = o.order_id
           AND p.account_id = a.account_id
           AND p.transaction_type = 'ACCRUAL'
        WHERE o.order_status = 'COMPLETED'
          AND o.refund_amount = 0
        LIMIT 5
    """).fetchall()

    for row in returns:
        print(dict(row))

    print("\n3. TIER ANOMALY CANDIDATES")
    print("=" * 60)

    candidates = connection.execute("""
        SELECT
            a.account_id,
            a.qualifying_spend,
            o.order_id,
            o.gross_amount,
            o.discount_amount,
            o.net_amount,
            t.tier_name AS current_tier
        FROM loyalty_accounts a
        JOIN customers c
            ON c.customer_id = a.customer_id
        JOIN orders o
            ON o.customer_id = c.customer_id
        JOIN tiers t
            ON t.tier_id = a.current_tier_id
        WHERE a.account_status = 'ACTIVE'
          AND o.gross_amount > o.net_amount
        ORDER BY a.qualifying_spend
        LIMIT 10
    """).fetchall()

    for row in candidates:
        print(dict(row))

    print("\n4. POINT LOT CANDIDATES")
    print("=" * 60)

    lots = connection.execute("""
        SELECT
            lot_id,
            account_id,
            original_points,
            remaining_points,
            expires_at,
            lot_status
        FROM point_lots
        WHERE remaining_points > 0
        LIMIT 5
    """).fetchall()

    for row in lots:
        print(dict(row))

finally:
    connection.close()