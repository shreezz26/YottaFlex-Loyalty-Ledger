
import argparse
import random
import sqlite3
import yaml

from pathlib import Path
from datetime import datetime, timedelta, timezone

from app.database import get_connection, initialize_database


ROOT = Path(__file__).resolve().parent.parent
BASE_DATE = datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc)


def load_config():
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def create_returns_table(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS returns (
            return_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            return_date TEXT NOT NULL,
            return_amount REAL NOT NULL CHECK(return_amount > 0),
            return_status TEXT NOT NULL
                CHECK(return_status IN ('COMPLETED', 'CANCELLED')),
            original_transaction_id TEXT,
            reversed_points INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(order_id),
            FOREIGN KEY(original_transaction_id)
                REFERENCES points_transactions(transaction_id)
        )
        """
    )

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_returns_order ON returns(order_id)"
    )


def clear_existing_data(connection):
    # Delete child records before parent records.
    tables = [
        "returns",
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
        "rewards",
        "tiers",
    ]

    existing_tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }

    for table in tables:
        if table in existing_tables:
            connection.execute(f"DELETE FROM {table}")

    connection.execute(
        "DELETE FROM sqlite_sequence WHERE name = 'tiers'"
    )


def create_master_data(connection, customers, orders, seed, config):
    rng = random.Random(seed)
    base_date = BASE_DATE.isoformat()

    # 1. Tiers
    tier_ids = {}

    for tier_id, tier in enumerate(config["tiers"], start=1):
        connection.execute(
            """
            INSERT INTO tiers (
                tier_id, tier_name, minimum_spend, earning_rate
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                tier_id,
                tier["name"],
                float(tier["minimum_spend"]),
                float(tier["earning_rate"]),
            ),
        )
        tier_ids[tier["name"]] = tier_id

    if "Bronze" not in tier_ids:
        raise ValueError("config.yaml must define a Bronze tier.")

    # 2. Earning rules
    for number, tier in enumerate(config["tiers"], start=1):
        connection.execute(
            """
            INSERT INTO rules (
                rule_id, rule_name, earning_rate,
                effective_from, effective_to, is_active
            )
            VALUES (?, ?, ?, ?, NULL, 1)
            """,
            (
                f"RULE-{number:03d}",
                f"{tier['name']} earning rule",
                float(tier["earning_rate"]),
                base_date,
            ),
        )

    # 3. Rewards
    rewards = [
        ("REW-001", "100 Point Reward", 100, "ACTIVE"),
        ("REW-002", "500 Point Reward", 500, "ACTIVE"),
        ("REW-003", "1000 Point Reward", 1000, "ACTIVE"),
    ]

    connection.executemany(
        """
        INSERT INTO rewards (
            reward_id, reward_name, points_required, reward_status
        )
        VALUES (?, ?, ?, ?)
        """,
        rewards,
    )

    # 4. Customers and loyalty accounts
    customer_rows = []
    account_rows = []

    for number in range(1, customers + 1):
        customer_id = f"CUS-{number:06d}"
        account_id = f"LOY-{customer_id}"

        customer_rows.append(
            (
                customer_id,
                f"Customer {number}",
                f"customer{number}@example.com",
                base_date,
            )
        )

        account_rows.append(
            (
                account_id,
                customer_id,
                tier_ids["Bronze"],
                0,
                0.0,
                "ACTIVE",
                base_date,
            )
        )

    connection.executemany(
        """
        INSERT INTO customers (
            customer_id, full_name, email, created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        customer_rows,
    )

    connection.executemany(
        """
        INSERT INTO loyalty_accounts (
            account_id, customer_id, current_tier_id,
            stored_balance, qualifying_spend, account_status, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        account_rows,
    )

    # 5. Orders and order lines
    order_rows = []
    line_rows = []

    product_names = [
        "Laptop", "Headphones", "Keyboard", "Mouse", "Monitor",
        "Smartphone", "Tablet", "Smartwatch", "Speaker", "Camera",
        "Printer", "Router", "SSD", "Webcam", "Charger",
    ]

    for number in range(1, orders + 1):
        customer_number = rng.randint(1, customers)
        customer_id = f"CUS-{customer_number:06d}"
        order_id = f"ORD-2026-{number:06d}"

        order_date = (
            BASE_DATE - timedelta(days=rng.randint(0, 300))
        ).isoformat()

        line_count = rng.randint(1, 3)
        gross = 0.0

        for line_number in range(1, line_count + 1):
            quantity = rng.randint(1, 5)
            unit_price = rng.randint(10000, 500000) / 100
            line_total = round(quantity * unit_price, 2)
            gross += line_total

            line_rows.append(
                (
                    f"LINE-{number:06d}-{line_number:02d}",
                    order_id,
                    rng.choice(product_names),
                    quantity,
                    unit_price,
                    line_total,
                )
            )

        gross = round(gross, 2)
        discount = round(gross * rng.randint(0, 15) / 100, 2)
        net = round(gross - discount, 2)

        order_rows.append(
            (
                order_id,
                customer_id,
                order_date,
                gross,
                discount,
                0.0,
                net,
                "COMPLETED",
            )
        )

    connection.executemany(
        """
        INSERT INTO orders (
            order_id, customer_id, order_date,
            gross_amount, discount_amount, refund_amount,
            net_amount, order_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        order_rows,
    )

    connection.executemany(
        """
        INSERT INTO order_lines (
            order_line_id, order_id, product_name,
            quantity, unit_price, line_total
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        line_rows,
    )

    return len(customer_rows), len(account_rows), len(order_rows), len(line_rows)


def generate(customers=None, orders=None, seed=None):
    config = load_config()

    generation = config.get("generation", {})

    customers = customers if customers is not None else int(
        generation.get("customers", 20000)
    )
    orders = orders if orders is not None else int(
        generation.get("orders", 100000)
    )
    seed = seed if seed is not None else int(
        config.get("project", {}).get("random_seed", 20261022)
    )

    if customers <= 0:
        raise ValueError("Customer count must be greater than zero.")

    if orders < 0:
        raise ValueError("Order count cannot be negative.")

    initialize_database()
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        create_returns_table(connection)
        clear_existing_data(connection)

        counts = create_master_data(
            connection, customers, orders, seed, config
        )

        connection.commit()

        print("\nMASTER DATA GENERATION COMPLETED")
        print("----------------------------------------")
        print(f"Customers       : {counts[0]:,}")
        print(f"Loyalty accounts: {counts[1]:,}")
        print(f"Orders          : {counts[2]:,}")
        print(f"Order lines     : {counts[3]:,}")
        print(f"Random seed     : {seed:,}")
        print(f"Base date       : {BASE_DATE.isoformat()}")
        print("----------------------------------------")
        print("Database: data/loyalty.db")
        print("Existing event records were cleared.")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate YottaFlex loyalty master data"
    )

    parser.add_argument("--customers", type=int, default=None)
    parser.add_argument("--orders", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)

    args = parser.parse_args()

    generate(
        customers=args.customers,
        orders=args.orders,
        seed=args.seed,
    )
