
from app.database import get_connection
from app.ledger_engine import accrue_points


def test_accrual_creates_transaction():
    connection = get_connection()

    try:
        order = connection.execute(
            """
            SELECT
                o.order_id,
                o.net_amount,
                a.account_id,
                t.earning_rate
            FROM orders o
            JOIN loyalty_accounts a
                ON a.customer_id = o.customer_id
            JOIN tiers t
                ON t.tier_id = a.current_tier_id
            WHERE o.order_status = 'COMPLETED'
            LIMIT 1
            """
        ).fetchone()

        assert order is not None

        existing = connection.execute(
            """
            SELECT COUNT(*)
            FROM points_transactions
            WHERE order_id = ?
              AND transaction_type = 'ACCRUAL'
            """,
            (order["order_id"],)
        ).fetchone()[0]

        if existing:
            return

        result = accrue_points(
            account_id=order["account_id"],
            order_id=order["order_id"],
            net_amount=order["net_amount"],
            earning_rate=order["earning_rate"]
        )

        assert result is not None

        transaction = connection.execute(
            """
            SELECT *
            FROM points_transactions
            WHERE order_id = ?
              AND transaction_type = 'ACCRUAL'
            """,
            (order["order_id"],)
        ).fetchone()

        assert transaction is not None
        assert transaction["points"] > 0

    finally:
        connection.close()


def test_no_duplicate_accrual_per_order():
    connection = get_connection()

    try:
        duplicate_orders = connection.execute(
            """
            SELECT order_id, COUNT(*)
            FROM points_transactions
            WHERE transaction_type = 'ACCRUAL'
            GROUP BY order_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        assert len(duplicate_orders) == 0

    finally:
        connection.close()


def test_account_balance_is_non_negative():
    connection = get_connection()

    try:
        accounts = connection.execute(
            """
            SELECT stored_balance
            FROM loyalty_accounts
            """
        ).fetchall()

        for account in accounts:
            assert account["stored_balance"] >= 0

    finally:
        connection.close()
