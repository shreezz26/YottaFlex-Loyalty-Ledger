
import json
import sqlite3
from pathlib import Path

from app.database import get_connection


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GROUND_TRUTH = ROOT / "data" / "generated" / "ground_truth.json"


def open_audit_connection(db_path=None):
    if db_path is None:
        return get_connection()

    connection = sqlite3.connect(
        str(db_path),
        timeout=30
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def table_exists(connection, table_name):
    result = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,)
    ).fetchone()

    return result is not None


def calculate_ledger_balance(connection, account_id):
    result = connection.execute(
        """
        SELECT COALESCE(
            SUM(
                CASE
                    WHEN transaction_type IN ('ACCRUAL', 'ADJUSTMENT')
                        THEN points
                    WHEN transaction_type IN (
                        'REDEMPTION', 'REVERSAL', 'EXPIRY'
                    )
                        THEN -points
                    ELSE 0
                END
            ),
            0
        ) AS ledger_balance
        FROM points_transactions
        WHERE account_id = ?
        """,
        (account_id,)
    ).fetchone()

    return result["ledger_balance"]


def audit_account_balances(db_path=None):
    connection = open_audit_connection(db_path)

    try:
        accounts = connection.execute(
            """
            SELECT account_id, stored_balance
            FROM loyalty_accounts
            """
        ).fetchall()

        issues = []

        for account in accounts:
            ledger_balance = calculate_ledger_balance(
                connection,
                account["account_id"]
            )

            if ledger_balance != account["stored_balance"]:
                issues.append({
                    "entity_id": account["account_id"],
                    "account_id": account["account_id"],
                    "stored_balance": account["stored_balance"],
                    "ledger_balance": ledger_balance,
                    "difference": (
                        account["stored_balance"] - ledger_balance
                    ),
                    "issue_type": "BALANCE_MISMATCH"
                })

        return issues

    finally:
        connection.close()


def validate_foreign_keys(db_path=None):
    connection = open_audit_connection(db_path)

    try:
        result = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        return [
            {
                "table": row[0],
                "rowid": row[1],
                "parent_table": row[2],
                "foreign_key_index": row[3],
                "issue_type": "FOREIGN_KEY_VIOLATION"
            }
            for row in result
        ]

    finally:
        connection.close()


def validate_primary_keys(db_path=None):
    connection = open_audit_connection(db_path)

    tables = [
        ("customers", "customer_id"),
        ("tiers", "tier_id"),
        ("rules", "rule_id"),
        ("loyalty_accounts", "account_id"),
        ("orders", "order_id"),
        ("order_lines", "order_line_id"),
        ("points_transactions", "transaction_id"),
        ("point_lots", "lot_id"),
        ("rewards", "reward_id"),
        ("redemptions", "redemption_id"),
        ("expiry_batches", "expiry_id"),
        ("returns", "return_id"),
        ("tier_history", "history_id"),
        ("audit_issues", "issue_id")
    ]

    issues = []

    try:
        for table, column in tables:
            if not table_exists(connection, table):
                continue

            result = connection.execute(
                f"""
                SELECT {column}, COUNT(*) AS record_count
                FROM {table}
                GROUP BY {column}
                HAVING COUNT(*) > 1
                """
            ).fetchall()

            for row in result:
                issues.append({
                    "table": table,
                    "id": row[column],
                    "count": row["record_count"],
                    "issue_type": "DUPLICATE_PRIMARY_KEY"
                })

        return issues

    finally:
        connection.close()


def validate_order_arithmetic(db_path=None):
    connection = open_audit_connection(db_path)

    try:
        if not table_exists(connection, "orders"):
            return []

        rows = connection.execute(
            """
            SELECT
                order_id,
                gross_amount,
                discount_amount,
                refund_amount,
                net_amount
            FROM orders
            """
        ).fetchall()

        issues = []

        for row in rows:
            expected = (
                row["gross_amount"]
                - row["discount_amount"]
                - row["refund_amount"]
            )

            if abs(expected - row["net_amount"]) > 0.01:
                issues.append({
                    "entity_id": row["order_id"],
                    "order_id": row["order_id"],
                    "expected_net": expected,
                    "actual_net": row["net_amount"],
                    "issue_type": "ORDER_ARITHMETIC_MISMATCH"
                })

        return issues

    finally:
        connection.close()


def detect_over_redemptions(db_path=None):
    connection = open_audit_connection(db_path)

    try:
        if not table_exists(connection, "redemptions"):
            return []

        rows = connection.execute(
            """
            SELECT
                r.redemption_id,
                r.account_id,
                r.points_used,
                r.redemption_status,
                a.stored_balance
            FROM redemptions r
            JOIN loyalty_accounts a
                ON a.account_id = r.account_id
            WHERE r.redemption_status = 'REJECTED'
              AND r.points_used > a.stored_balance
            """
        ).fetchall()

        return [
            {
                "entity_id": row["redemption_id"],
                "account_id": row["account_id"],
                "attempted_points": row["points_used"],
                "stored_balance": row["stored_balance"],
                "issue_type": "OVER_REDEMPTION"
            }
            for row in rows
        ]

    finally:
        connection.close()


def detect_returns_without_reversal(db_path=None):
    connection = open_audit_connection(db_path)

    try:
        if not table_exists(connection, "returns"):
            return []

        rows = connection.execute(
            """
            SELECT
                r.return_id,
                r.order_id,
                r.original_transaction_id,
                r.reversed_points,
                p.points AS earned_points
            FROM returns r
            JOIN points_transactions p
                ON p.transaction_id = r.original_transaction_id
            WHERE r.return_status = 'COMPLETED'
              AND p.transaction_type = 'ACCRUAL'
              AND r.reversed_points < p.points
            """
        ).fetchall()

        return [
            {
                "entity_id": row["order_id"],
                "return_id": row["return_id"],
                "original_transaction_id": row["original_transaction_id"],
                "earned_points": row["earned_points"],
                "reversed_points": row["reversed_points"],
                "issue_type": "RETURN_WITHOUT_REVERSAL"
            }
            for row in rows
        ]

    finally:
        connection.close()


def detect_duplicate_expiries(db_path=None):
    connection = open_audit_connection(db_path)

    try:
        if not table_exists(connection, "expiry_batches"):
            return []

        if table_exists(connection, "anomaly_expiry_evidence"):
            query = """
                SELECT
                    lot_id,
                    COUNT(*) AS expiry_count,
                    GROUP_CONCAT(expiry_id) AS expiry_ids
                FROM (
                    SELECT lot_id, expiry_id
                    FROM expiry_batches

                    UNION ALL

                    SELECT lot_id, evidence_id AS expiry_id
                    FROM anomaly_expiry_evidence
                )
                GROUP BY lot_id
                HAVING COUNT(*) > 1
            """
        else:
            query = """
                SELECT
                    lot_id,
                    COUNT(*) AS expiry_count,
                    GROUP_CONCAT(expiry_id) AS expiry_ids
                FROM expiry_batches
                GROUP BY lot_id
                HAVING COUNT(*) > 1
            """

        rows = connection.execute(query).fetchall()

        return [
            {
                "entity_id": row["lot_id"],
                "expiry_count": row["expiry_count"],
                "expiry_ids": row["expiry_ids"],
                "issue_type": "DUPLICATE_EXPIRY"
            }
            for row in rows
        ]

    finally:
        connection.close()


def detect_incorrect_tiers(db_path=None):
    connection = open_audit_connection(db_path)

    try:
        rows = connection.execute(
            """
            SELECT
                a.account_id,
                a.qualifying_spend,
                t.tier_name AS actual_tier,
                expected.tier_name AS expected_tier,
                t.minimum_spend AS actual_minimum_spend
            FROM loyalty_accounts a
            JOIN tiers t
                ON t.tier_id = a.current_tier_id
            LEFT JOIN tiers expected
                ON expected.tier_id = (
                    SELECT tier_id
                    FROM tiers
                    WHERE minimum_spend <= a.qualifying_spend
                    ORDER BY minimum_spend DESC
                    LIMIT 1
                )
            WHERE expected.tier_id IS NULL
               OR a.current_tier_id != expected.tier_id
            """
        ).fetchall()

        return [
            {
                "entity_id": row["account_id"],
                "qualifying_spend": row["qualifying_spend"],
                "actual_tier": row["actual_tier"],
                "expected_tier": row["expected_tier"],
                "actual_minimum_spend": row["actual_minimum_spend"],
                "issue_type": "INCORRECT_TIER_CALCULATION"
            }
            for row in rows
        ]

    finally:
        connection.close()


def run_all_audits(db_path=None):
    balance_issues = audit_account_balances(db_path)
    foreign_key_issues = validate_foreign_keys(db_path)
    primary_key_issues = validate_primary_keys(db_path)
    arithmetic_issues = validate_order_arithmetic(db_path)
    over_redemptions = detect_over_redemptions(db_path)
    return_issues = detect_returns_without_reversal(db_path)
    duplicate_expiries = detect_duplicate_expiries(db_path)
    tier_issues = detect_incorrect_tiers(db_path)

    results = {
        "balance_mismatches": balance_issues,
        "foreign_key_issues": foreign_key_issues,
        "primary_key_issues": primary_key_issues,
        "arithmetic_issues": arithmetic_issues,
        "over_redemptions": over_redemptions,
        "returns_without_reversal": return_issues,
        "duplicate_expiries": duplicate_expiries,
        "incorrect_tiers": tier_issues
    }

    results["total_issues"] = sum(
        len(items) for items in results.values()
    )

    return results


def compare_ground_truth(
    detected_results,
    ground_truth_path=DEFAULT_GROUND_TRUTH
):
    with open(
        ground_truth_path,
        "r",
        encoding="utf-8"
    ) as file:
        ground_truth_data = json.load(file)

    result_mapping = {
        "balance_mismatches": "entity_id",
        "over_redemptions": "entity_id",
        "returns_without_reversal": "entity_id",
        "duplicate_expiries": "entity_id",
        "incorrect_tiers": "entity_id"
    }

    detected_items = []

    for category, entity_key in result_mapping.items():
        for item in detected_results.get(category, []):
            detected_items.append({
                "entity_id": item[entity_key],
                "issue_type": item["issue_type"]
            })

    expected_items = [
        {
            "entity_id": item["entity_id"],
            "issue_type": item["issue_type"]
        }
        for item in ground_truth_data["anomalies"]
    ]

    detected_set = {
        (item["entity_id"], item["issue_type"])
        for item in detected_items
    }

    expected_set = {
        (item["entity_id"], item["issue_type"])
        for item in expected_items
    }

    matched = detected_set & expected_set
    missed = expected_set - detected_set
    unexpected = detected_set - expected_set

    return {
        "expected_count": len(expected_set),
        "detected_count": len(detected_set),
        "matched_count": len(matched),
        "missed": [
            {
                "entity_id": entity,
                "issue_type": issue_type
            }
            for entity, issue_type in sorted(missed)
        ],
        "unexpected": [
            {
                "entity_id": entity,
                "issue_type": issue_type
            }
            for entity, issue_type in sorted(unexpected)
        ],
        "precision": (
            len(matched) / len(detected_set)
            if detected_set else 0
        ),
        "recall": (
            len(matched) / len(expected_set)
            if expected_set else 0
        )
    }
