
from app.database import get_connection
from app.audit import (
    calculate_ledger_balance,
    validate_foreign_keys,
    validate_order_arithmetic,
)


def test_customers_generated():
    connection = get_connection()
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM customers"
        ).fetchone()[0]

        assert count >= 20_000
    finally:
        connection.close()


def test_accounts_generated():
    connection = get_connection()
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM loyalty_accounts"
        ).fetchone()[0]

        assert count >= 20_000
    finally:
        connection.close()


def test_orders_generated():
    connection = get_connection()
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM orders"
        ).fetchone()[0]

        assert count >= 100_000
    finally:
        connection.close()


def test_accrual_transactions_generated():
    connection = get_connection()
    try:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM points_transactions
            WHERE transaction_type = 'ACCRUAL'
            """
        ).fetchone()[0]

        assert count >= 100_000
    finally:
        connection.close()


def test_transaction_ids_are_unique():
    connection = get_connection()
    try:
        result = connection.execute(
            """
            SELECT transaction_id, COUNT(*)
            FROM points_transactions
            GROUP BY transaction_id
            HAVING COUNT(*) > 1
            """
        ).fetchall()

        assert len(result) == 0
    finally:
        connection.close()


def test_foreign_key_integrity():
    result = validate_foreign_keys()
    assert result == []


def test_order_arithmetic():
    issues = validate_order_arithmetic()
    assert issues == []


def test_ledger_balance_calculation():
    connection = get_connection()
    try:
        account = connection.execute(
            """
            SELECT account_id
            FROM loyalty_accounts
            LIMIT 1
            """
        ).fetchone()

        assert account is not None

        balance = calculate_ledger_balance(
            connection,
            account["account_id"]
        )

        assert balance >= 0

    finally:
        connection.close()


def test_total_transaction_target():
    connection = get_connection()
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM points_transactions"
        ).fetchone()[0]

        assert count >= 300_000
    finally:
        connection.close()


def test_no_negative_account_balances():
    connection = get_connection()
    try:
        count = connection.execute(
            """
            SELECT COUNT(*)
            FROM loyalty_accounts
            WHERE stored_balance < 0
            """
        ).fetchone()[0]

        assert count == 0
    finally:
        connection.close()


def test_account_balances_reconcile_with_ledger():
    connection = get_connection()
    try:
        mismatches = connection.execute(
            """
            SELECT COUNT(*)
            FROM loyalty_accounts a
            WHERE a.stored_balance != COALESCE(
                (
                    SELECT SUM(
                        CASE
                            WHEN transaction_type IN (
                                'ACCRUAL', 'ADJUSTMENT'
                            ) THEN points
                            WHEN transaction_type IN (
                                'REDEMPTION', 'REVERSAL', 'EXPIRY'
                            ) THEN -points
                            ELSE 0
                        END
                    )
                    FROM points_transactions p
                    WHERE p.account_id = a.account_id
                ), 0
            )
            """
        ).fetchone()[0]

        assert mismatches == 0
    finally:
        connection.close()
