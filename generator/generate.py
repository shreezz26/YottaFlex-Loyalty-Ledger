import argparse
import random
import yaml

from pathlib import Path
from datetime import datetime, timedelta, timezone

from app.database import get_connection, initialize_database


ROOT = Path(__file__).resolve().parent.parent


def load_config():
    config_path = ROOT / "config.yaml"

    with open(config_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def generate(customers=100, orders=500, seed=20261022):

    if customers <= 0 or orders < 0:
        raise ValueError("Customers must be positive and orders cannot be negative.")

    rng = random.Random(seed)

    config = load_config()
    initialize_database()

    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        # Clear dependent records before master records.
        tables = [
            "expiry_batches",
            "redemptions",
            "audit_issues",
            "tier_history",
            "point_lots",
            "points_transactions",
            "order_lines",
            "orders",
            "loyalty_accounts",
            "rules",
            "customers",
            "tiers",
            "rewards"
        ]

        for table in tables:
            connection.execute(f"DELETE FROM {table}")

        # Reset automatically generated tier IDs.
        connection.execute(
            "DELETE FROM sqlite_sequence WHERE name = 'tiers'"
        )

        # Fixed reference date makes output reproducible.
        base_date = datetime(
            2026, 10, 22, 12, 0, 0,
            tzinfo=timezone.utc
        )

        # --------------------------------
        # 1. CREATE TIER MASTER DATA
        # --------------------------------

        tier_ids = {}

        for tier_id, tier in enumerate(config["tiers"], start=1):

            connection.execute(
                """
                INSERT INTO tiers (
                    tier_id,
                    tier_name,
                    minimum_spend,
                    earning_rate
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    tier_id,
                    tier["name"],
                    tier["minimum_spend"],
                    tier["earning_rate"]
                )
            )

            tier_ids[tier["name"]] = tier_id

        # --------------------------------
        # 2. CREATE RULE MASTER DATA
        # --------------------------------

        for number, tier in enumerate(config["tiers"], start=1):

            connection.execute(
                """
                INSERT INTO rules (
                    rule_id,
                    rule_name,
                    earning_rate,
                    effective_from,
                    effective_to,
                    is_active
                )
                VALUES (?, ?, ?, ?, NULL, 1)
                """,
                (
                    f"RULE-{number:03d}",
                    f"{tier['name']} earning rule",
                    tier["earning_rate"],
                    base_date.isoformat()
                )
            )

        # --------------------------------
        # 3. CREATE REWARD MASTER DATA
        # --------------------------------

        rewards = [
            ("REW-001", "100 Point Reward", 100, "ACTIVE"),
            ("REW-002", "500 Point Reward", 500, "ACTIVE"),
            ("REW-003", "1000 Point Reward", 1000, "ACTIVE")
        ]

        connection.executemany(
            """
            INSERT INTO rewards (
                reward_id,
                reward_name,
                points_required,
                reward_status
            )
            VALUES (?, ?, ?, ?)
            """,
            rewards
        )

        # --------------------------------
        # 4. CREATE CUSTOMERS
        # --------------------------------

        customer_rows = []
        account_rows = []

        for number in range(1, customers + 1):

            customer_id = f"CUS-{number:06d}"
            account_id = f"LOY-{customer_id}"

            customer_rows.append((
                customer_id,
                f"Customer {number}",
                f"customer{number}@example.com",
                base_date.isoformat()
            ))

            account_rows.append((
                account_id,
                customer_id,
                tier_ids["Bronze"],
                0,
                0,
                "ACTIVE",
                base_date.isoformat()
            ))

        connection.executemany(
            """
            INSERT INTO customers (
                customer_id,
                full_name,
                email,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            customer_rows
        )

        connection.executemany(
            """
            INSERT INTO loyalty_accounts (
                account_id,
                customer_id,
                current_tier_id,
                stored_balance,
                qualifying_spend,
                account_status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            account_rows
        )

        # --------------------------------
        # 5. CREATE ORDERS AND ORDER LINES
        # --------------------------------

        order_rows = []
        line_rows = []

        for number in range(1, orders + 1):

            customer_number = rng.randint(1, customers)
            customer_id = f"CUS-{customer_number:06d}"

            order_id = f"ORD-2026-{number:06d}"

            order_date = (
                base_date - timedelta(days=rng.randint(0, 300))
            ).isoformat()

            gross = 0.0
            line_number = 1

            # Each order contains 1 to 3 product lines.
            number_of_lines = rng.randint(1, 3)

            current_lines = []

            for _ in range(number_of_lines):

                quantity = rng.randint(1, 5)

                # Generate price in paise to avoid random
                # floating-point price generation.
                unit_price = rng.randint(10000, 500000) / 100

                line_total = round(quantity * unit_price, 2)

                gross += line_total

                current_lines.append((
                    f"LINE-{number:06d}-{line_number:02d}",
                    order_id,
                    f"Product {rng.randint(1, 50)}",
                    quantity,
                    unit_price,
                    line_total
                ))

                line_number += 1

            gross = round(gross, 2)

            discount = round(
                gross * rng.randint(0, 15) / 100,
                2
            )

            refund = 0.0

            net = round(gross - discount - refund, 2)

            order_rows.append((
                order_id,
                customer_id,
                order_date,
                gross,
                discount,
                refund,
                net,
                "COMPLETED"
            ))

            line_rows.extend(current_lines)

        connection.executemany(
            """
            INSERT INTO orders (
                order_id,
                customer_id,
                order_date,
                gross_amount,
                discount_amount,
                refund_amount,
                net_amount,
                order_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            order_rows
        )

        connection.executemany(
            """
            INSERT INTO order_lines (
                order_line_id,
                order_id,
                product_name,
                quantity,
                unit_price,
                line_total
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            line_rows
        )

        connection.commit()

        print("\nSynthetic master data generated successfully!")
        print("--------------------------------------------")
        print(f"Customers       : {customers:,}")
        print(f"Loyalty accounts: {customers:,}")
        print(f"Orders          : {orders:,}")
        print(f"Order lines     : {len(line_rows):,}")
        print(f"Random seed     : {seed}")
        print(f"Base date       : {base_date.isoformat()}")
        print("--------------------------------------------")
        print("Database: data/loyalty.db")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Generate YottaFlex synthetic loyalty data"
    )

    parser.add_argument(
        "--customers",
        type=int,
        default=100
    )

    parser.add_argument(
        "--orders",
        type=int,
        default=500
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=20261022
    )

    args = parser.parse_args()

    generate(
        customers=args.customers,
        orders=args.orders,
        seed=args.seed
    )