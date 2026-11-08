
from datetime import datetime, timezone

from app.database import transaction
from app.ledger_engine import next_id


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def process_return(order_id, return_amount):
    """
    Process a full or partial order return.

    Records the return, updates order refund values,
    and reverses earned loyalty points proportionally.
    """

    return_amount = round(float(return_amount), 2)

    if return_amount <= 0:
        raise ValueError("Return amount must be greater than zero.")

    with transaction() as connection:

        # 1. Find the original order
        order = connection.execute(
            """
            SELECT
                order_id,
                customer_id,
                gross_amount,
                discount_amount,
                refund_amount,
                net_amount,
                order_status
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,)
        ).fetchone()

        if order is None:
            raise ValueError("Order not found.")

        if order["order_status"] != "COMPLETED":
            raise ValueError("Only completed orders can be returned.")

        original_net = round(
            float(order["gross_amount"])
            - float(order["discount_amount"]),
            2
        )

        previous_refunds = round(
            float(order["refund_amount"]),
            2
        )

        remaining_amount = round(
            original_net - previous_refunds,
            2
        )

        if return_amount > remaining_amount:
            raise ValueError(
                f"Return exceeds remaining refundable amount: "
                f"{remaining_amount}"
            )

        # 2. Find the original points accrual
        account = connection.execute(
            """
            SELECT account_id
            FROM loyalty_accounts
            WHERE customer_id = ?
            """,
            (order["customer_id"],)
        ).fetchone()

        if account is None:
            raise ValueError("Customer loyalty account not found.")

        original = connection.execute(
            """
            SELECT transaction_id, points
            FROM points_transactions
            WHERE order_id = ?
              AND transaction_type = 'ACCRUAL'
            """,
            (order_id,)
        ).fetchone()

        if original is None:
            raise ValueError("Original points accrual not found.")

        # 3. Calculate proportional point reversal
        original_points = int(original["points"])

        cumulative_refund = round(
            previous_refunds + return_amount,
            2
        )

        target_reversed_points = min(
            original_points,
            int(
                original_points
                * cumulative_refund
                / original_net
            )
        )

        previous_reversed_points = connection.execute(
            """
            SELECT COALESCE(SUM(reversed_points), 0)
            FROM returns
            WHERE order_id = ?
              AND return_status = 'COMPLETED'
            """,
            (order_id,)
        ).fetchone()[0]

        points_to_reverse = (
            target_reversed_points
            - int(previous_reversed_points)
        )

        # 4. Generate return identifier
        return_id = next_id(
            connection,
            "returns",
            "return_id",
            "RET-",
            6
        )

        now = utc_now()

        # 5. Record the return
        connection.execute(
            """
            INSERT INTO returns (
                return_id,
                order_id,
                return_date,
                return_amount,
                return_status,
                original_transaction_id,
                reversed_points,
                created_at
            )
            VALUES (?, ?, ?, ?, 'COMPLETED', ?, ?, ?)
            """,
            (
                return_id,
                order_id,
                now,
                return_amount,
                original["transaction_id"],
                points_to_reverse,
                now
            )
        )

        # 6. Update the order refund and net amount
        new_refund = round(
            previous_refunds + return_amount,
            2
        )

        new_net_amount = round(
            original_net - new_refund,
            2
        )

        new_status = (
            "RETURNED"
            if new_net_amount == 0
            else "COMPLETED"
        )

        connection.execute(
            """
            UPDATE orders
            SET refund_amount = ?,
                net_amount = ?,
                order_status = ?
            WHERE order_id = ?
            """,
            (
                new_refund,
                new_net_amount,
                new_status,
                order_id
            )
        )

        # 7. Create a reversal ledger entry
        if points_to_reverse > 0:

            transaction_id = next_id(
                connection,
                "points_transactions",
                "transaction_id",
                "PTS-2026-",
                8
            )

            connection.execute(
                """
                INSERT INTO points_transactions (
                    transaction_id,
                    account_id,
                    order_id,
                    transaction_type,
                    points,
                    transaction_date,
                    reference_id,
                    description
                )
                VALUES (?, ?, ?, 'REVERSAL', ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    account["account_id"],
                    order_id,
                    points_to_reverse,
                    now,
                    original["transaction_id"],
                    f"Points reversed for return {return_id}"
                )
            )

            # Remove available points from the original accrual lot.
            lots = connection.execute(
                """
                SELECT lot_id, remaining_points
                FROM point_lots
                WHERE source_transaction_id = ?
                  AND remaining_points > 0
                ORDER BY created_at ASC
                """,
                (original["transaction_id"],)
            ).fetchall()

            remaining_to_remove = points_to_reverse

            for lot in lots:

                if remaining_to_remove <= 0:
                    break

                removed = min(
                    lot["remaining_points"],
                    remaining_to_remove
                )

                new_remaining = (
                    lot["remaining_points"] - removed
                )

                connection.execute(
                    """
                    UPDATE point_lots
                    SET remaining_points = ?,
                        lot_status = ?
                    WHERE lot_id = ?
                    """,
                    (
                        new_remaining,
                        "REVERSED" if new_remaining == 0 else "ACTIVE",
                        lot["lot_id"]
                    )
                )

                remaining_to_remove -= removed

            # Reverse the full liability, including points already spent.
            connection.execute(
                """
                UPDATE loyalty_accounts
                SET stored_balance = stored_balance - ?
                WHERE account_id = ?
                """,
                (
                    points_to_reverse,
                    account["account_id"]
                )
            )

        return {
            "return_id": return_id,
            "order_id": order_id,
            "return_amount": return_amount,
            "points_reversed": points_to_reverse,
            "refund_total": new_refund,
            "remaining_order_value": new_net_amount,
            "status": "COMPLETED"
        }
