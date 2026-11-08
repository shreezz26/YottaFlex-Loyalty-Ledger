import sqlite3
from pathlib import Path
from contextlib import contextmanager

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "loyalty.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DB_PATH,
        timeout=30,
        isolation_level=None
    )

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")

    return connection


@contextmanager
def transaction():
    connection = get_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def initialize_database():

    schema = [

        """
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS tiers (
            tier_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tier_name TEXT UNIQUE NOT NULL,
            minimum_spend REAL NOT NULL,
            earning_rate REAL NOT NULL
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS rules (
            rule_id TEXT PRIMARY KEY,
            rule_name TEXT NOT NULL,
            earning_rate REAL NOT NULL,
            effective_from TEXT NOT NULL,
            effective_to TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS loyalty_accounts (
            account_id TEXT PRIMARY KEY,
            customer_id TEXT UNIQUE NOT NULL,
            current_tier_id INTEGER NOT NULL,
            stored_balance INTEGER NOT NULL DEFAULT 0,
            qualifying_spend REAL NOT NULL DEFAULT 0,
            account_status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL,

            FOREIGN KEY(customer_id)
                REFERENCES customers(customer_id),

            FOREIGN KEY(current_tier_id)
                REFERENCES tiers(tier_id),

            CHECK(account_status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            order_date TEXT NOT NULL,
            gross_amount REAL NOT NULL,
            discount_amount REAL NOT NULL DEFAULT 0,
            refund_amount REAL NOT NULL DEFAULT 0,
            net_amount REAL NOT NULL,
            order_status TEXT NOT NULL,

            FOREIGN KEY(customer_id)
                REFERENCES customers(customer_id),

            CHECK(order_status IN (
                'COMPLETED',
                'PARTIALLY_RETURNED',
                'RETURNED',
                'CANCELLED'
            ))
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS order_lines (
            order_line_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            line_total REAL NOT NULL,

            FOREIGN KEY(order_id)
                REFERENCES orders(order_id),

            CHECK(quantity > 0),
            CHECK(unit_price >= 0)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS points_transactions (
            transaction_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            order_id TEXT,
            transaction_type TEXT NOT NULL,
            points INTEGER NOT NULL,
            transaction_date TEXT NOT NULL,
            reference_id TEXT,
            description TEXT,

            FOREIGN KEY(account_id)
                REFERENCES loyalty_accounts(account_id),

            FOREIGN KEY(order_id)
                REFERENCES orders(order_id),

            CHECK(transaction_type IN (
                'ACCRUAL',
                'REDEMPTION',
                'REVERSAL',
                'EXPIRY',
                'ADJUSTMENT'
            )),

            CHECK(points > 0)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS point_lots (
            lot_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            source_transaction_id TEXT NOT NULL,
            original_points INTEGER NOT NULL,
            remaining_points INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            lot_status TEXT NOT NULL DEFAULT 'ACTIVE',

            FOREIGN KEY(account_id)
                REFERENCES loyalty_accounts(account_id),

            FOREIGN KEY(source_transaction_id)
                REFERENCES points_transactions(transaction_id),

            CHECK(original_points > 0),
            CHECK(remaining_points >= 0),
            CHECK(remaining_points <= original_points)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS rewards (
            reward_id TEXT PRIMARY KEY,
            reward_name TEXT NOT NULL,
            points_required INTEGER NOT NULL,
            reward_status TEXT NOT NULL DEFAULT 'ACTIVE',

            CHECK(points_required > 0)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS redemptions (
            redemption_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            reward_id TEXT NOT NULL,
            points_used INTEGER NOT NULL,
            redemption_date TEXT NOT NULL,
            redemption_status TEXT NOT NULL,

            FOREIGN KEY(account_id)
                REFERENCES loyalty_accounts(account_id),

            FOREIGN KEY(reward_id)
                REFERENCES rewards(reward_id),

            CHECK(points_used > 0),
            CHECK(redemption_status IN (
                'COMPLETED',
                'REJECTED',
                'CANCELLED'
            ))
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS expiry_batches (
            expiry_id TEXT PRIMARY KEY,
            lot_id TEXT UNIQUE NOT NULL,
            account_id TEXT NOT NULL,
            expired_points INTEGER NOT NULL,
            expiry_date TEXT NOT NULL,

            FOREIGN KEY(lot_id)
                REFERENCES point_lots(lot_id),

            FOREIGN KEY(account_id)
                REFERENCES loyalty_accounts(account_id),

            CHECK(expired_points > 0)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS tier_history (
            history_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            old_tier_id INTEGER,
            new_tier_id INTEGER NOT NULL,
            qualifying_spend REAL NOT NULL,
            changed_at TEXT NOT NULL,

            FOREIGN KEY(account_id)
                REFERENCES loyalty_accounts(account_id),

            FOREIGN KEY(old_tier_id)
                REFERENCES tiers(tier_id),

            FOREIGN KEY(new_tier_id)
                REFERENCES tiers(tier_id)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS audit_issues (
            issue_id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            ground_truth INTEGER NOT NULL,
            description TEXT NOT NULL,
            detected_at TEXT NOT NULL,

            CHECK(ground_truth IN (0, 1))
        )
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_orders_customer
        ON orders(customer_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_transactions_account
        ON points_transactions(account_id)
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_lots_account_expiry
        ON point_lots(account_id, expires_at)
        """
    ]

    connection = get_connection()

    try:
        for statement in schema:
            connection.execute(statement)

        connection.commit()

    finally:
        connection.close()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized successfully.")
    print(f"Database location: {DB_PATH}")