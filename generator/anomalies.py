
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

DB_PATH = ROOT / "data" / "loyalty_anomaly.db"
OUTPUT_DIR = ROOT / "data" / "generated"
GROUND_TRUTH_PATH = OUTPUT_DIR / "ground_truth.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def record_issue(connection, issue_id, entity_id, issue_type, description):
    connection.execute(
        """
        INSERT INTO audit_issues (
            issue_id,
            entity_id,
            issue_type,
            ground_truth,
            description,
            detected_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            issue_id,
            entity_id,
            issue_type,
            1,
            description,
            utc_now(),
        ),
    )


def inject_anomalies():
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Anomaly database not found: {DB_PATH}"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    labels = []

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")

        # ANOMALY 1: Stored balance differs from ledger sum.

        account = connection.execute(
            """
            SELECT account_id, stored_balance
            FROM loyalty_accounts
            WHERE stored_balance > 0
            ORDER BY account_id
            LIMIT 1
            """
        ).fetchone()

        if account is None:
            raise RuntimeError("No account available for balance anomaly.")

        account_id = account["account_id"]

        connection.execute(
            """
            UPDATE loyalty_accounts
            SET stored_balance = stored_balance + 17
            WHERE account_id = ?
            """,
            (account_id,),
        )

        record_issue(
            connection,
            "ANM-001",
            account_id,
            "BALANCE_MISMATCH",
            "Stored balance increased by 17 points without a ledger transaction.",
        )

        labels.append({
            "issue_id": "ANM-001",
            "entity_id": account_id,
            "issue_type": "BALANCE_MISMATCH",
            "ground_truth": 1,
            "expected_difference": 17,
        })

        # ANOMALY 2: Redemption attempt exceeds available balance.

        account = connection.execute(
            """
            SELECT account_id, stored_balance
            FROM loyalty_accounts
            WHERE stored_balance >= 0
            ORDER BY account_id
            LIMIT 1
            """
        ).fetchone()

        if account is None:
            raise RuntimeError("No account available for redemption anomaly.")

        redemption_id = "RDM-ANM-000001"
        attempted_points = account["stored_balance"] + 10000

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
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                redemption_id,
                account["account_id"],
                "REW-001",
                attempted_points,
                utc_now(),
                "REJECTED",
            ),
        )

        record_issue(
            connection,
            "ANM-002",
            redemption_id,
            "OVER_REDEMPTION",
            "Redemption attempt exceeded available balance and was rejected.",
        )

        labels.append({
            "issue_id": "ANM-002",
            "entity_id": redemption_id,
            "issue_type": "OVER_REDEMPTION",
            "ground_truth": 1,
            "attempted_points": attempted_points,
            "available_balance": account["stored_balance"],
            "expected_status": "REJECTED",
        })

        # ANOMALY 3: Returned order without points reversal.

        order = connection.execute(
            """
            SELECT
                o.order_id,
                o.gross_amount,
                o.discount_amount,
                p.transaction_id,
                p.points
            FROM orders o
            JOIN points_transactions p
                ON p.order_id = o.order_id
            WHERE o.order_status = 'COMPLETED'
              AND o.refund_amount = 0
              AND p.transaction_type = 'ACCRUAL'
            ORDER BY o.order_id
            LIMIT 1
            """
        ).fetchone()

        if order is None:
            raise RuntimeError("No order available for return anomaly.")

        return_id = "RET-ANM-000001"
        return_amount = order["gross_amount"] - order["discount_amount"]

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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                return_id,
                order["order_id"],
                utc_now(),
                return_amount,
                "COMPLETED",
                order["transaction_id"],
                0,
                utc_now(),
            ),
        )

        connection.execute(
            """
            UPDATE orders
            SET refund_amount = gross_amount - discount_amount,
                net_amount = 0,
                order_status = 'RETURNED'
            WHERE order_id = ?
            """,
            (order["order_id"],),
        )

        record_issue(
            connection,
            "ANM-003",
            order["order_id"],
            "RETURN_WITHOUT_REVERSAL",
            "Order was returned but its original accrual transaction was not reversed.",
        )

        labels.append({
            "issue_id": "ANM-003",
            "entity_id": order["order_id"],
            "issue_type": "RETURN_WITHOUT_REVERSAL",
            "ground_truth": 1,
            "return_id": return_id,
            "original_transaction_id": order["transaction_id"],
            "earned_points": order["points"],
            "reversed_points": 0,
        })

        # ANOMALY 4: Duplicate expiry evidence for one point lot.

        lot = connection.execute(
            """
            SELECT lot_id, account_id, remaining_points
            FROM point_lots
            WHERE remaining_points > 0
            ORDER BY lot_id
            LIMIT 1
            """
        ).fetchone()

        if lot is None:
            raise RuntimeError("No point lot available for expiry anomaly.")

        connection.execute(
            """
            INSERT INTO expiry_batches (
                expiry_id,
                lot_id,
                account_id,
                expired_points,
                expiry_date
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "EXP-ANM-000001",
                lot["lot_id"],
                lot["account_id"],
                lot["remaining_points"],
                utc_now(),
            ),
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS anomaly_expiry_evidence (
                evidence_id TEXT PRIMARY KEY,
                lot_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                expired_points INTEGER NOT NULL,
                expiry_date TEXT NOT NULL,
                FOREIGN KEY(lot_id) REFERENCES point_lots(lot_id),
                FOREIGN KEY(account_id) REFERENCES loyalty_accounts(account_id)
            )
            """
        )

        connection.execute(
            """
            INSERT INTO anomaly_expiry_evidence (
                evidence_id,
                lot_id,
                account_id,
                expired_points,
                expiry_date
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "EXP-ANM-000002",
                lot["lot_id"],
                lot["account_id"],
                lot["remaining_points"],
                utc_now(),
            ),
        )

        record_issue(
            connection,
            "ANM-004",
            lot["lot_id"],
            "DUPLICATE_EXPIRY",
            "The same point lot has two expiry records in the anomaly evidence.",
        )

        labels.append({
            "issue_id": "ANM-004",
            "entity_id": lot["lot_id"],
            "issue_type": "DUPLICATE_EXPIRY",
            "ground_truth": 1,
            "expiry_records": [
                "EXP-ANM-000001",
                "EXP-ANM-000002",
            ],
        })

        # ANOMALY 5: Tier incorrectly calculated using gross spend.

        synthetic_customer = "CUS-ANM-000001"
        synthetic_account = "LOY-CUS-ANM-000001"
        synthetic_order = "ORD-ANM-000001"

        existing = connection.execute(
            """
            SELECT customer_id
            FROM customers
            WHERE customer_id = ?
            """,
            (synthetic_customer,),
        ).fetchone()

        if existing is not None:
            raise RuntimeError(
                "Synthetic tier case already exists. "
                "Create a fresh anomaly database copy."
            )

        bronze = connection.execute(
            "SELECT tier_id FROM tiers WHERE tier_name = 'Bronze'"
        ).fetchone()

        silver = connection.execute(
            "SELECT tier_id FROM tiers WHERE tier_name = 'Silver'"
        ).fetchone()

        if bronze is None or silver is None:
            raise RuntimeError("Required tiers are missing.")

        connection.execute(
            """
            INSERT INTO customers (
                customer_id, full_name, email, created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                synthetic_customer,
                "Synthetic Tier Test",
                "tier-test@example.invalid",
                utc_now(),
            ),
        )

        # Incorrectly assigned Silver despite qualifying spend of 9500.

        connection.execute(
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
            (
                synthetic_account,
                synthetic_customer,
                silver["tier_id"],
                0,
                9500,
                "ACTIVE",
                utc_now(),
            ),
        )

        connection.execute(
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
            (
                synthetic_order,
                synthetic_customer,
                utc_now(),
                12000,
                3000,
                0,
                9000,
                "COMPLETED",
            ),
        )

        record_issue(
            connection,
            "ANM-005",
            synthetic_account,
            "INCORRECT_TIER_CALCULATION",
            "Account was assigned Silver using gross spend although qualifying spend is below the Silver threshold.",
        )

        labels.append({
            "issue_id": "ANM-005",
            "entity_id": synthetic_account,
            "issue_type": "INCORRECT_TIER_CALCULATION",
            "ground_truth": 1,
            "qualifying_spend": 9500,
            "gross_order_amount": 12000,
            "net_order_amount": 9000,
            "actual_tier": "Silver",
            "expected_tier": "Bronze",
            "synthetic_case": True,
        })

        # Commit all database changes together.

        connection.commit()

        # Export ground truth separately from operational records.

        with open(
            GROUND_TRUTH_PATH,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                {
                    "dataset": "YottaFlex Loyalty Ledger Anomaly Dataset",
                    "database": "loyalty_anomaly.db",
                    "created_at": utc_now(),
                    "seed": 20261022,
                    "anomalies": labels,
                },
                file,
                indent=4,
            )

        print("\nANOMALY INJECTION COMPLETED")
        print("=" * 50)

        for item in labels:
            print(
                item["issue_id"],
                "|",
                item["issue_type"],
                "|",
                item["entity_id"],
            )

        print(f"\nTotal anomalies: {len(labels)}")
        print(f"Ground truth: {GROUND_TRUTH_PATH}")

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


if __name__ == "__main__":
    inject_anomalies()
