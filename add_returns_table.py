
from app.database import get_connection

connection = get_connection()

try:
    connection.execute("BEGIN IMMEDIATE")

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

            FOREIGN KEY (order_id)
                REFERENCES orders(order_id),

            FOREIGN KEY (original_transaction_id)
                REFERENCES points_transactions(transaction_id)
        )
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_returns_order
        ON returns(order_id)
        """
    )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_returns_transaction
        ON returns(original_transaction_id)
        """
    )

    connection.commit()

    print("Returns table created successfully!")

except Exception:
    connection.rollback()
    raise

finally:
    connection.close()
