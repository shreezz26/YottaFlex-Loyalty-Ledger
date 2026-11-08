
from datetime import datetime, timedelta, timezone

from app.database import transaction


# ============================================================
# COMMON UTILITIES
# ============================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def next_id(connection, table, column, prefix, digits):
    """Generate sequential IDs inside the current transaction."""

    last_record = connection.execute(
        f"""
        SELECT {column}
        FROM {table}
        WHERE {column} LIKE ?
        ORDER BY {column} DESC
        LIMIT 1
        """,
        (f"{prefix}%",)
    ).fetchone()

    if last_record is None:
        number = 1
    else:
        number = int(
            last_record[column].split("-")[-1]
        ) + 1

    return f"{prefix}{number:0{digits}d}"


def get_available_points(connection, account_id, as_of=None):
    """Calculate unexpired points available in active lots."""

    as_of = as_of or utc_now()

    result = connection.execute(
        """
        SELECT COALESCE(SUM(remaining_points), 0)
        FROM point_lots
        WHERE account_id = ?
          AND remaining_points > 0
          AND expires_at > ?
          AND lot_status = 'ACTIVE'
        """,
        (account_id, as_of)
    ).fetchone()

    return int(result[0])


def _update_tier_in_transaction(
    connection,
    account_id,
    qualifying_spend
):
    """
    Update tier using the existing database transaction.
    This helper must not open another transaction.
    """

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
        raise ValueError("Tier master data is missing.")

    eligible = [
        dict(tier)
        for tier in tiers
        if qualifying_spend >= float(tier["minimum_spend"])
    ]

    if not eligible:
        raise ValueError("No eligible tier found.")

    selected_tier = max(
        eligible,
        key=lambda tier: float(tier["minimum_spend"])
    )

    account = connection.execute(
        """
        SELECT current_tier_id
        FROM loyalty_accounts
        WHERE account_id = ?
        """,
        (account_id,)
    ).fetchone()

    if account is None:
        raise ValueError("Loyalty account not found.")

    old_tier_id = account["current_tier_id"]
    new_tier_id = selected_tier["tier_id"]

    tier_changed = old_tier_id != new_tier_id

    if tier_changed:

        history_id = next_id(
            connection,
            "tier_history",
            "history_id",
            "TH-",
            8
        )

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
                account_id,
                old_tier_id,
                new_tier_id,
                qualifying_spend,
                utc_now()
            )
        )

    connection.execute(
        """
        UPDATE loyalty_accounts
        SET current_tier_id = ?,
            qualifying_spend = ?
        WHERE account_id = ?
        """,
        (
            new_tier_id,
            qualifying_spend,
            account_id
        )
    )

    return selected_tier, tier_changed


# ============================================================
# 1. POINTS ACCRUAL + AUTOMATIC TIER PROGRESSION
# ============================================================

def accrue_points(
    account_id,
    order_id,
    net_amount,
    earning_rate=None,
    validity_days=365
):
    """
    Award points using the account's current tier earning rate.

    The earning_rate argument is retained for compatibility
    with the existing API, but the database tier rate is used.
    """

    net_amount = round(float(net_amount), 2)

    if net_amount <= 0:
        raise ValueError("Net amount must be greater than zero.")

    if validity_days <= 0:
        raise ValueError("Validity days must be positive.")

    points = 0

    with transaction() as connection:

        # Validate account and retrieve its current tier rate.
        account = connection.execute(
            """
            SELECT
                a.account_id,
                a.customer_id,
                a.account_status,
                a.stored_balance,
                a.qualifying_spend,
                a.current_tier_id,
                t.tier_name,
                t.earning_rate
            FROM loyalty_accounts a
            JOIN tiers t
                ON a.current_tier_id = t.tier_id
            WHERE a.account_id = ?
            """,
            (account_id,)
        ).fetchone()

        if account is None:
            raise ValueError(
                "Loyalty account or current tier not found."
            )

        if account["account_status"] != "ACTIVE":
            raise ValueError("Account is not active.")

        # Always use the configured current tier rate.
        current_rate = float(account["earning_rate"])

        if current_rate <= 0:
            raise ValueError("Invalid tier earning rate.")

        # Validate order.
        order = connection.execute(
            """
            SELECT
                customer_id,
                net_amount,
                order_status
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,)
        ).fetchone()

        if order is None:
            raise ValueError("Order not found.")

        if order["customer_id"] != account["customer_id"]:
            raise ValueError(
                "Order does not belong to this account."
            )

        if order["order_status"] != "COMPLETED":
            raise ValueError(
                "Only completed orders earn points."
            )

        if abs(
            float(order["net_amount"]) - net_amount
        ) > 0.000001:
            raise ValueError(
                "Provided amount does not match order net amount."
            )

        # Prevent duplicate accrual.
        existing = connection.execute(
            """
            SELECT transaction_id
            FROM points_transactions
            WHERE order_id = ?
              AND transaction_type = 'ACCRUAL'
            """,
            (order_id,)
        ).fetchone()

        if existing:
            raise ValueError(
                "Points already accrued for this order."
            )

        # Calculate points using the current tier rate.
        points = int(net_amount * current_rate)

        if points <= 0:
            raise ValueError(
                "Calculated points must be positive."
            )

        transaction_id = next_id(
            connection,
            "points_transactions",
            "transaction_id",
            "PTS-2026-",
            8
        )

        lot_id = next_id(
            connection,
            "point_lots",
            "lot_id",
            "LOT-",
            8
        )

        now = utc_now()

        expiry_date = (
            datetime.now(timezone.utc)
            + timedelta(days=validity_days)
        ).isoformat()

        # Record accrual in immutable transaction ledger.
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
            VALUES (?, ?, ?, 'ACCRUAL', ?, ?, ?, ?)
            """,
            (
                transaction_id,
                account_id,
                order_id,
                points,
                now,
                order_id,
                "Points earned from completed order"
            )
        )

        # Create individual expiry lot.
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
                account_id,
                transaction_id,
                points,
                points,
                now,
                expiry_date
            )
        )

        # Update account balance and qualifying spend.
        new_qualifying_spend = round(
            float(account["qualifying_spend"]) + net_amount,
            2
        )

        connection.execute(
            """
            UPDATE loyalty_accounts
            SET stored_balance = stored_balance + ?
            WHERE account_id = ?
            """,
            (points, account_id)
        )

        # Recalculate tier in the same transaction.
        selected_tier, tier_changed = (
            _update_tier_in_transaction(
                connection,
                account_id,
                new_qualifying_spend
            )
        )

        return {
            "transaction_id": transaction_id,
            "lot_id": lot_id,
            "account_id": account_id,
            "points_awarded": points,
            "earning_rate": current_rate,
            "previous_tier": account["tier_name"],
            "current_tier": selected_tier["tier_name"],
            "tier_changed": tier_changed,
            "qualifying_spend": new_qualifying_spend,
            "status": "COMPLETED"
        }


# ============================================================
# 2. POINTS REDEMPTION
# ============================================================

def redeem_points(account_id, reward_id):

    with transaction() as connection:

        account = connection.execute(
            """
            SELECT stored_balance, account_status
            FROM loyalty_accounts
            WHERE account_id = ?
            """,
            (account_id,)
        ).fetchone()

        if account is None:
            raise ValueError("Loyalty account not found.")

        if account["account_status"] != "ACTIVE":
            raise ValueError("Account is not active.")

        reward = connection.execute(
            """
            SELECT points_required, reward_status
            FROM rewards
            WHERE reward_id = ?
            """,
            (reward_id,)
        ).fetchone()

        if reward is None:
            raise ValueError("Reward not found.")

        if reward["reward_status"] != "ACTIVE":
            raise ValueError("Reward is not active.")

        points = int(reward["points_required"])

        if points < 100:
            raise ValueError(
                "Minimum redemption is 100 points."
            )

        if account["stored_balance"] < points:
            raise ValueError("Insufficient points balance.")

        now = utc_now()

        lots = connection.execute(
            """
            SELECT lot_id, remaining_points
            FROM point_lots
            WHERE account_id = ?
              AND remaining_points > 0
              AND expires_at > ?
              AND lot_status = 'ACTIVE'
            ORDER BY expires_at ASC, created_at ASC, lot_id ASC
            """,
            (account_id, now)
        ).fetchall()

        available = sum(
            lot["remaining_points"] for lot in lots
        )

        if available < points:
            raise ValueError("Insufficient unexpired points.")

        redemption_id = next_id(
            connection,
            "redemptions",
            "redemption_id",
            "RDM-",
            6
        )

        transaction_id = next_id(
            connection,
            "points_transactions",
            "transaction_id",
            "PTS-2026-",
            8
        )

        remaining_to_consume = points

        # FEFO consumption.
        for lot in lots:

            if remaining_to_consume == 0:
                break

            consumed = min(
                lot["remaining_points"],
                remaining_to_consume
            )

            new_remaining = (
                lot["remaining_points"] - consumed
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
                    "CONSUMED" if new_remaining == 0 else "ACTIVE",
                    lot["lot_id"]
                )
            )

            remaining_to_consume -= consumed

        if remaining_to_consume != 0:
            raise ValueError("Unable to consume required points.")

        connection.execute(
            """
            INSERT INTO redemptions (
                redemption_id,
                account_id,
                reward_id,
                points_used,
                redemption_date,
                redemption_status
            )
            VALUES (?, ?, ?, ?, ?, 'COMPLETED')
            """,
            (
                redemption_id,
                account_id,
                reward_id,
                points,
                now
            )
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
            VALUES (?, ?, NULL, 'REDEMPTION', ?, ?, ?, ?)
            """,
            (
                transaction_id,
                account_id,
                points,
                now,
                redemption_id,
                "Points redeemed for reward"
            )
        )

        connection.execute(
            """
            UPDATE loyalty_accounts
            SET stored_balance = stored_balance - ?
            WHERE account_id = ?
            """,
            (points, account_id)
        )

        return {
            "redemption_id": redemption_id,
            "transaction_id": transaction_id,
            "points_redeemed": points,
            "status": "COMPLETED"
        }


# ============================================================
# 3. POINTS REVERSAL
# ============================================================

def reverse_accrual(original_transaction_id, return_amount=None):

    with transaction() as connection:

        original = connection.execute(
            """
            SELECT
                transaction_id,
                account_id,
                order_id,
                points
            FROM points_transactions
            WHERE transaction_id = ?
              AND transaction_type = 'ACCRUAL'
            """,
            (original_transaction_id,)
        ).fetchone()

        if original is None:
            raise ValueError(
                "Original accrual transaction not found."
            )

        order = connection.execute(
            """
            SELECT net_amount
            FROM orders
            WHERE order_id = ?
            """,
            (original["order_id"],)
        ).fetchone()

        if order is None:
            raise ValueError("Original order not found.")

        original_points = int(original["points"])
        original_amount = float(order["net_amount"])

        if original_amount <= 0:
            raise ValueError("Original order amount is invalid.")

        if return_amount is None:
            reversal_points = original_points
        else:
            return_amount = float(return_amount)

            if return_amount <= 0:
                raise ValueError("Return amount must be positive.")

            if return_amount > original_amount:
                raise ValueError(
                    "Return amount exceeds order amount."
                )

            reversal_points = int(
                original_points * return_amount / original_amount
            )

        if reversal_points <= 0:
            raise ValueError(
                "Calculated reversal points must be positive."
            )

        previous_reversals = connection.execute(
            """
            SELECT COALESCE(SUM(points), 0)
            FROM points_transactions
            WHERE reference_id = ?
              AND transaction_type = 'REVERSAL'
            """,
            (original_transaction_id,)
        ).fetchone()[0]

        remaining_original = (
            original_points - int(previous_reversals)
        )

        if reversal_points > remaining_original:
            raise ValueError(
                "Reversal exceeds remaining earned points."
            )

        transaction_id = next_id(
            connection,
            "points_transactions",
            "transaction_id",
            "PTS-2026-",
            8
        )

        now = utc_now()

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
                original["account_id"],
                original["order_id"],
                reversal_points,
                now,
                original_transaction_id,
                "Points reversed for returned order"
            )
        )

        lots = connection.execute(
            """
            SELECT lot_id, remaining_points
            FROM point_lots
            WHERE source_transaction_id = ?
              AND remaining_points > 0
            ORDER BY created_at ASC
            """,
            (original_transaction_id,)
        ).fetchall()

        remaining_to_remove = reversal_points

        for lot in lots:

            if remaining_to_remove == 0:
                break

            removed = min(
                lot["remaining_points"],
                remaining_to_remove
            )

            new_remaining = lot["remaining_points"] - removed

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

        connection.execute(
            """
            UPDATE loyalty_accounts
            SET stored_balance = stored_balance - ?
            WHERE account_id = ?
            """,
            (
                reversal_points,
                original["account_id"]
            )
        )

        return {
            "transaction_id": transaction_id,
            "original_transaction_id": original_transaction_id,
            "points_reversed": reversal_points,
            "status": "COMPLETED"
        }


# ============================================================
# 4. POINTS EXPIRY
# ============================================================

def expire_points(as_of=None):

    if as_of is None:
        as_of = utc_now()

    # Validate supplied timestamp.
    try:
        datetime.fromisoformat(as_of)
    except (TypeError, ValueError):
        raise ValueError("Invalid expiry timestamp.")

    with transaction() as connection:

        expired_lots = connection.execute(
            """
            SELECT
                lot_id,
                account_id,
                remaining_points
            FROM point_lots
            WHERE remaining_points > 0
              AND expires_at <= ?
              AND lot_status = 'ACTIVE'
            ORDER BY expires_at ASC, lot_id ASC
            """,
            (as_of,)
        ).fetchall()

        if not expired_lots:
            return {
                "batch_id": None,
                "expired_lots": 0,
                "expired_points": 0,
                "status": "NO_EXPIRY_REQUIRED"
            }

        batch_id = next_id(
            connection,
            "expiry_batches",
            "batch_id",
            "EXP-",
            6
        )

        total_expired = 0

        for lot in expired_lots:

            points = int(lot["remaining_points"])

            if points <= 0:
                continue

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
                VALUES (?, ?, NULL, 'EXPIRY', ?, ?, ?, ?)
                """,
                (
                    transaction_id,
                    lot["account_id"],
                    points,
                    as_of,
                    batch_id,
                    "Loyalty points expired"
                )
            )

            connection.execute(
                """
                UPDATE point_lots
                SET remaining_points = 0,
                    lot_status = 'EXPIRED'
                WHERE lot_id = ?
                """,
                (lot["lot_id"],)
            )

            connection.execute(
                """
                UPDATE loyalty_accounts
                SET stored_balance = stored_balance - ?
                WHERE account_id = ?
                """,
                (points, lot["account_id"])
            )

            total_expired += points

        connection.execute(
            """
            INSERT INTO expiry_batches (
                batch_id,
                expiry_date,
                total_points_expired,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                batch_id,
                as_of,
                total_expired,
                utc_now()
            )
        )

        return {
            "batch_id": batch_id,
            "expired_lots": len(expired_lots),
            "expired_points": total_expired,
            "status": "COMPLETED"
        }
