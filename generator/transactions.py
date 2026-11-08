
import argparse
import random
from datetime import datetime, timedelta, timezone

from app.database import get_connection, initialize_database


SEED = 20261022
BASE_DATE = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)

# Cache generated IDs to avoid querying SQLite for every inserted record.
_ID_COUNTERS = {}


def iso(value):
    return value.isoformat()


def next_id(connection, table, column, prefix, digits=8):
    key = (id(connection), table, column, prefix, digits)

    if key not in _ID_COUNTERS:
        row = connection.execute(
            f"SELECT {column} FROM {table} "
            f"WHERE {column} LIKE ? ORDER BY {column} DESC LIMIT 1",
            (f"{prefix}%",)
        ).fetchone()

        number = 1 if row is None else int(row[0].split("-")[-1]) + 1
        _ID_COUNTERS[key] = number

    number = _ID_COUNTERS[key]
    _ID_COUNTERS[key] += 1

    return f"{prefix}{number:0{digits}d}"


def add_transaction(
    connection,
    account_id,
    transaction_type,
    points,
    event_date,
    order_id=None,
    reference_id=None,
    description=""
):
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
            transaction_id, account_id, order_id,
            transaction_type, points, transaction_date,
            reference_id, description
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_id,
            account_id,
            order_id,
            transaction_type,
            int(points),
            iso(event_date),
            reference_id,
            description
        )
    )

    return transaction_id


def choose_tier(tiers, spend):
    eligible = [
        tier for tier in tiers
        if spend >= float(tier["minimum_spend"])
    ]
    return max(eligible, key=lambda tier: tier["minimum_spend"])


def generate_accruals(connection, tiers, validity_days):
    orders = connection.execute(
        """
        SELECT o.order_id, o.customer_id, o.order_date, o.net_amount,
               a.account_id, a.current_tier_id, a.qualifying_spend
        FROM orders o
        JOIN loyalty_accounts a ON a.customer_id = o.customer_id
        WHERE o.order_status = 'COMPLETED'
        ORDER BY o.order_date, o.order_id
        """
    ).fetchall()

    # Maintain account state in memory instead of querying it for every order.
    account_state = {}
    for row in orders:
        account_state.setdefault(
            row["account_id"],
            {
                "current_tier_id": row["current_tier_id"],
                "qualifying_spend": float(row["qualifying_spend"])
            }
        )

    count = 0

    for order in orders:
        account_id = order["account_id"]
        account = account_state[account_id]

        tier = next(
            t for t in tiers
            if t["tier_id"] == account["current_tier_id"]
        )

        net = round(float(order["net_amount"]), 2)
        points = int(net * float(tier["earning_rate"]))

        if points <= 0:
            continue

        event_date = datetime.fromisoformat(order["order_date"])
        expiry_date = event_date + timedelta(days=validity_days)

        transaction_id = add_transaction(
            connection,
            account_id,
            "ACCRUAL",
            points,
            event_date,
            order["order_id"],
            order["order_id"],
            "Points earned from completed order"
        )

        lot_id = next_id(
            connection, "point_lots", "lot_id", "LOT-", 8
        )

        connection.execute(
            """
            INSERT INTO point_lots (
                lot_id, account_id, source_transaction_id,
                original_points, remaining_points,
                created_at, expires_at, lot_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
            """,
            (
                lot_id,
                account_id,
                transaction_id,
                points,
                points,
                iso(event_date),
                iso(expiry_date)
            )
        )

        new_spend = round(account["qualifying_spend"] + net, 2)
        new_tier = choose_tier(tiers, new_spend)

        if new_tier["tier_id"] != account["current_tier_id"]:
            history_id = next_id(
                connection, "tier_history", "history_id", "TH-", 8
            )

            connection.execute(
                """
                INSERT INTO tier_history (
                    history_id, account_id, old_tier_id,
                    new_tier_id, qualifying_spend, changed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    history_id,
                    account_id,
                    account["current_tier_id"],
                    new_tier["tier_id"],
                    new_spend,
                    iso(event_date)
                )
            )

        account["qualifying_spend"] = new_spend
        account["current_tier_id"] = new_tier["tier_id"]

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
                account_id
            )
        )

        count += 1

    return count


def generate_returns(connection, rng, return_rate=0.08):
    orders = connection.execute(
        """
        SELECT o.order_id, o.gross_amount, o.discount_amount,
               a.account_id, p.transaction_id, p.points
        FROM orders o
        JOIN loyalty_accounts a ON a.customer_id = o.customer_id
        JOIN points_transactions p
          ON p.order_id = o.order_id
         AND p.transaction_type = 'ACCRUAL'
        WHERE o.order_status = 'COMPLETED'
        ORDER BY o.order_id
        """
    ).fetchall()

    count = 0

    for order in orders:
        if rng.random() > return_rate:
            continue

        original_net = round(
            float(order["gross_amount"]) -
            float(order["discount_amount"]), 2
        )

        if original_net <= 0:
            continue

        return_amount = round(
            original_net * rng.choice([0.25, 0.50, 0.75, 1.0]), 2
        )

        previous = connection.execute(
            """
            SELECT COALESCE(SUM(return_amount), 0),
                   COALESCE(SUM(reversed_points), 0)
            FROM returns
            WHERE order_id = ? AND return_status = 'COMPLETED'
            """,
            (order["order_id"],)
        ).fetchone()

        previous_amount = float(previous[0])

        if previous_amount + return_amount > original_net:
            continue

        target = min(
            int(order["points"]),
            int(
                int(order["points"])
                * (previous_amount + return_amount)
                / original_net
            )
        )

        points_to_reverse = target - int(previous[1])

        return_id = next_id(
            connection, "returns", "return_id", "RET-", 6
        )

        event_date = BASE_DATE + timedelta(
            days=rng.randint(61, 120),
            seconds=rng.randint(0, 86399)
        )

        connection.execute(
            """
            INSERT INTO returns (
                return_id, order_id, return_date, return_amount,
                return_status, original_transaction_id,
                reversed_points, created_at
            )
            VALUES (?, ?, ?, ?, 'COMPLETED', ?, ?, ?)
            """,
            (
                return_id,
                order["order_id"],
                iso(event_date),
                return_amount,
                order["transaction_id"],
                points_to_reverse,
                iso(event_date)
            )
        )

        if points_to_reverse > 0:
            add_transaction(
                connection,
                order["account_id"],
                "REVERSAL",
                points_to_reverse,
                event_date,
                order["order_id"],
                order["transaction_id"],
                f"Points reversed for return {return_id}"
            )

            lots = connection.execute(
                """
                SELECT lot_id, remaining_points
                FROM point_lots
                WHERE source_transaction_id = ?
                  AND remaining_points > 0
                ORDER BY created_at, lot_id
                """,
                (order["transaction_id"],)
            ).fetchall()

            remaining = points_to_reverse

            for lot in lots:
                if remaining <= 0:
                    break

                removed = min(int(lot["remaining_points"]), remaining)
                new_remaining = int(lot["remaining_points"]) - removed

                connection.execute(
                    """
                    UPDATE point_lots
                    SET remaining_points = ?, lot_status = ?
                    WHERE lot_id = ?
                    """,
                    (
                        new_remaining,
                        "REVERSED" if new_remaining == 0 else "ACTIVE",
                        lot["lot_id"]
                    )
                )

                remaining -= removed

            if remaining:
                raise ValueError(
                    f"Could not reverse all points for {order['order_id']}"
                )

            connection.execute(
                """
                UPDATE loyalty_accounts
                SET stored_balance = stored_balance - ?
                WHERE account_id = ?
                """,
                (points_to_reverse, order["account_id"])
            )

        new_refund = round(previous_amount + return_amount, 2)
        new_net = round(original_net - new_refund, 2)

        connection.execute(
            """
            UPDATE orders
            SET refund_amount = ?, net_amount = ?, order_status = ?
            WHERE order_id = ?
            """,
            (
                new_refund,
                new_net,
                "RETURNED" if new_net == 0 else "PARTIALLY_RETURNED",
                order["order_id"]
            )
        )

        count += 1

    return count


def generate_redemptions(
    connection,
    rng,
    redemption_rate=1.0,
    redemptions_per_account=6
):
    accounts = connection.execute(
        """
        SELECT account_id
        FROM loyalty_accounts
        WHERE account_status = 'ACTIVE'
        ORDER BY account_id
        """
    ).fetchall()

    rewards = connection.execute(
        """
        SELECT reward_id, points_required
        FROM rewards
        WHERE reward_status = 'ACTIVE'
          AND points_required >= 100
        ORDER BY points_required
        """
    ).fetchall()

    count = 0

    for account in accounts:
        account_id = account["account_id"]

        for round_number in range(redemptions_per_account):
            if rng.random() > redemption_rate:
                continue

            # Six separate chronological windows between day 121 and day 180.
            start_day = 121 + (round_number * 10)

            event_date = BASE_DATE + timedelta(
                days=rng.randint(start_day, start_day + 9),
                seconds=rng.randint(0, 86399)
            )

            lots = connection.execute(
                """
                SELECT lot_id, remaining_points
                FROM point_lots
                WHERE account_id = ?
                  AND remaining_points > 0
                  AND lot_status = 'ACTIVE'
                  AND expires_at > ?
                  AND created_at <= ?
                ORDER BY expires_at, created_at, lot_id
                """,
                (account_id, iso(event_date), iso(event_date))
            ).fetchall()

            available_points = sum(
                int(lot["remaining_points"]) for lot in lots
            )

            candidates = [
                reward for reward in rewards
                if int(reward["points_required"]) <= available_points
            ]

            if not candidates:
                continue

            reward = rng.choice(candidates)
            points = int(reward["points_required"])

            redemption_id = next_id(
                connection, "redemptions", "redemption_id", "RDM-", 6
            )

            remaining = points

            # Consume eligible point lots using FEFO.
            for lot in lots:
                if remaining <= 0:
                    break

                consumed = min(
                    int(lot["remaining_points"]),
                    remaining
                )

                new_remaining = int(lot["remaining_points"]) - consumed

                connection.execute(
                    """
                    UPDATE point_lots
                    SET remaining_points = ?, lot_status = ?
                    WHERE lot_id = ?
                    """,
                    (
                        new_remaining,
                        "CONSUMED" if new_remaining == 0 else "ACTIVE",
                        lot["lot_id"]
                    )
                )

                remaining -= consumed

            if remaining:
                raise ValueError(
                    f"Insufficient points for redemption {redemption_id}"
                )

            connection.execute(
                """
                INSERT INTO redemptions (
                    redemption_id, account_id, reward_id,
                    points_used, redemption_date, redemption_status
                )
                VALUES (?, ?, ?, ?, ?, 'COMPLETED')
                """,
                (
                    redemption_id,
                    account_id,
                    reward["reward_id"],
                    points,
                    iso(event_date)
                )
            )

            add_transaction(
                connection,
                account_id,
                "REDEMPTION",
                points,
                event_date,
                reference_id=redemption_id,
                description="Points redeemed for reward"
            )

            connection.execute(
                """
                UPDATE loyalty_accounts
                SET stored_balance = stored_balance - ?
                WHERE account_id = ?
                """,
                (points, account_id)
            )

            count += 1

    return count


def generate_expiries(connection, as_of=None):
    as_of = as_of or iso(BASE_DATE)

    lots = connection.execute(
        """
        SELECT lot_id, account_id, remaining_points, expires_at
        FROM point_lots
        WHERE remaining_points > 0
          AND lot_status = 'ACTIVE'
          AND expires_at <= ?
        ORDER BY expires_at, lot_id
        """,
        (as_of,)
    ).fetchall()

    count = 0

    for lot in lots:
        points = int(lot["remaining_points"])
        expiry_date = datetime.fromisoformat(lot["expires_at"])

        expiry_id = next_id(
            connection, "expiry_batches", "expiry_id", "EXP-", 6
        )

        add_transaction(
            connection,
            lot["account_id"],
            "EXPIRY",
            points,
            expiry_date,
            reference_id=expiry_id,
            description=f"Points expired from lot {lot['lot_id']}"
        )

        connection.execute(
            """
            INSERT INTO expiry_batches (
                expiry_id, lot_id, account_id,
                expired_points, expiry_date
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                expiry_id,
                lot["lot_id"],
                lot["account_id"],
                points,
                iso(expiry_date)
            )
        )

        connection.execute(
            """
            UPDATE point_lots
            SET remaining_points = 0, lot_status = 'EXPIRED'
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

        count += 1

    return count


def generate_transactions(
    seed=SEED,
    validity_days=365,
    redemptions_per_account=6
):
    rng = random.Random(seed)
    initialize_database()

    connection = get_connection()
    _ID_COUNTERS.clear()

    try:
        connection.execute("BEGIN IMMEDIATE")

        existing = connection.execute(
            "SELECT COUNT(*) FROM points_transactions"
        ).fetchone()[0]

        if existing:
            raise RuntimeError(
                "Transactions already exist. Rebuild master data first."
            )

        tiers = [
            dict(row)
            for row in connection.execute(
                """
                SELECT tier_id, tier_name, minimum_spend, earning_rate
                FROM tiers
                ORDER BY minimum_spend
                """
            ).fetchall()
        ]

        if not tiers:
            raise RuntimeError("Tier master data is missing.")

        accruals = generate_accruals(
            connection, tiers, validity_days
        )

        returns = generate_returns(connection, rng)

        redemptions = generate_redemptions(
            connection,
            rng,
            redemption_rate=1.0,
            redemptions_per_account=redemptions_per_account
        )

        # Expiries are generated separately using the simulation clock.
        expiries = generate_expiries(connection, iso(BASE_DATE))

        negative = connection.execute(
            """
            SELECT COUNT(*) FROM loyalty_accounts
            WHERE stored_balance < 0
            """
        ).fetchone()[0]

        if negative:
            raise ValueError(
                f"Generation produced {negative} negative account balances."
            )

        connection.commit()

        total = connection.execute(
            "SELECT COUNT(*) FROM points_transactions"
        ).fetchone()[0]

        print("\nEVENT GENERATION COMPLETED")
        print("--------------------------------")
        print(f"Accruals          : {accruals:,}")
        print(f"Returns           : {returns:,}")
        print(f"Redemptions       : {redemptions:,}")
        print(f"Expired lots      : {expiries:,}")
        print(f"Total ledger events: {total:,}")
        print(f"Negative balances : {negative}")
        print(f"Redemption rounds : {redemptions_per_account}")
        print(f"Seed              : {seed}")
        print("--------------------------------")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate deterministic loyalty ledger events"
    )

    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--validity-days", type=int, default=365)
    parser.add_argument("--redemptions-per-account", type=int, default=6)

    args = parser.parse_args()

    generate_transactions(
        seed=args.seed,
        validity_days=args.validity_days,
        redemptions_per_account=args.redemptions_per_account
    )
