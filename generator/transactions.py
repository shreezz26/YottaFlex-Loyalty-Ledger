
from datetime import datetime, timedelta

from app.database import get_connection


def generate_transactions(seed=20261022):
    """
    Generate deterministic accrual transactions.

    Business rules:
    - Process completed orders chronologically.
    - Earn points using the tier active before the order.
    - Increase qualifying spend by eligible net spend.
    - Update the tier after the order.
    - Record tier changes in tier_history.
    - Never accrue the same order twice.
    """

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM points_transactions
            """
        ).fetchone()["total"]

        if existing > 0:
            raise RuntimeError(
                "Transactions already exist. "
                "Do not run this generator twice. "
                "Regenerate the master dataset first."
            )

        orders = connection.execute(
            """
            SELECT
                o.order_id,
                o.customer_id,
                o.order_date,
                o.net_amount,
                a.account_id
            FROM orders o
            JOIN loyalty_accounts a
                ON a.customer_id = o.customer_id
            WHERE o.order_status = 'COMPLETED'
              AND o.net_amount > 0
            ORDER BY o.order_date, o.order_id
            """
        ).fetchall()

        tiers = connection.execute(
            """
            SELECT
                tier_id,
                tier_name,
                minimum_spend,
                earning_rate
            FROM tiers
            ORDER BY minimum_spend ASC
            """
        ).fetchall()

        if not tiers:
            raise RuntimeError("No tiers found in database.")

        tier_by_id = {
            tier["tier_id"]: tier
            for tier in tiers
        }

        transaction_number = 1
        history_number = 1

        generated = 0
        tier_changes = 0

        for order in orders:

            account = connection.execute(
                """
                SELECT
                    current_tier_id,
                    qualifying_spend
                FROM loyalty_accounts
                WHERE account_id = ?
                """,
                (order["account_id"],)
            ).fetchone()

            current_tier = tier_by_id[
                account["current_tier_id"]
            ]

            # Apply the rate of the tier active
            # immediately before this order.
            points = int(
                round(
                    order["net_amount"]
                    * current_tier["earning_rate"],
                    8
                )
            )

            if points <= 0:
                continue

            transaction_id = (
                f"PTS-2026-{transaction_number:08d}"
            )

            lot_id = (
                f"LOT-{transaction_number:08d}"
            )

            transaction_number += 1

            order_date = order["order_date"]

            expiry_date = (
                datetime.fromisoformat(order_date)
                + timedelta(days=365)
            ).isoformat()

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
                VALUES (?, ?, ?, 'ACCRUAL', ?, ?, NULL, ?)
                """,
                (
                    transaction_id,
                    order["account_id"],
                    order["order_id"],
                    points,
                    order_date,
                    "Synthetic order points accrual"
                )
            )

            connection.execute(
                """
                INSERT INTO point_lots (
                    lot_id,
                    account_id,
                    source_transaction_id,
                    original_points,
                    remaining_points,
                    created_at,
                    expires_at,
                    lot_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                """,
                (
                    lot_id,
                    order["account_id"],
                    transaction_id,
                    points,
                    points,
                    order_date,
                    expiry_date
                )
            )

            new_spend = round(
                account["qualifying_spend"]
                + order["net_amount"],
                2
            )

            # Determine the tier earned after this order.
            new_tier = tiers[0]

            for tier in tiers:
                if new_spend >= tier["minimum_spend"]:
                    new_tier = tier
                else:
                    break

            connection.execute(
                """
                UPDATE loyalty_accounts
                SET stored_balance = stored_balance + ?,
                    qualifying_spend = ?,
                    current_tier_id = ?
                WHERE account_id = ?
                """,
                (
                    points,
                    new_spend,
                    new_tier["tier_id"],
                    order["account_id"]
                )
            )

            if new_tier["tier_id"] != current_tier["tier_id"]:

                history_id = (
                    f"TH-{history_number:08d}"
                )

                history_number += 1

                connection.execute(
                    """
                    INSERT INTO tier_history (
                        history_id,
                        account_id,
                        old_tier_id,
                        new_tier_id,
                        qualifying_spend,
                        changed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        history_id,
                        order["account_id"],
                        current_tier["tier_id"],
                        new_tier["tier_id"],
                        new_spend,
                        order_date
                    )
                )

                tier_changes += 1

            generated += 1

        connection.commit()

        print("\nTRANSACTION GENERATION COMPLETED")
        print("=" * 50)
        print(f"Seed: {seed}")
        print(f"Accrual transactions: {generated:,}")
        print(f"Point lots: {generated:,}")
        print(f"Tier changes: {tier_changes:,}")
        print("=" * 50)

        return generated

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    generate_transactions()
