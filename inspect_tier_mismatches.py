
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATABASES = {
    "ORIGINAL DATABASE": ROOT / "data" / "loyalty.db",
    "ANOMALY DATABASE": ROOT / "data" / "loyalty_anomaly.db",
}


def inspect_database(name, db_path):
    print("\n" + "=" * 65)
    print(name)
    print("=" * 65)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row

    try:
        mismatches = connection.execute(
            """
            SELECT
                a.account_id,
                a.qualifying_spend,
                actual.tier_name AS actual_tier,
                expected.tier_name AS expected_tier
            FROM loyalty_accounts a
            JOIN tiers actual
                ON actual.tier_id = a.current_tier_id
            JOIN tiers expected
                ON expected.tier_id = (
                    SELECT tier_id
                    FROM tiers
                    WHERE minimum_spend <= a.qualifying_spend
                    ORDER BY minimum_spend DESC
                    LIMIT 1
                )
            WHERE a.current_tier_id != expected.tier_id
            ORDER BY a.qualifying_spend DESC
            """
        ).fetchall()

        print("Total tier mismatches:", len(mismatches))

        print("\nMISMATCH DISTRIBUTION")
        print("-" * 65)

        distribution = connection.execute(
            """
            SELECT
                actual.tier_name AS actual_tier,
                expected.tier_name AS expected_tier,
                COUNT(*) AS total
            FROM loyalty_accounts a
            JOIN tiers actual
                ON actual.tier_id = a.current_tier_id
            JOIN tiers expected
                ON expected.tier_id = (
                    SELECT tier_id
                    FROM tiers
                    WHERE minimum_spend <= a.qualifying_spend
                    ORDER BY minimum_spend DESC
                    LIMIT 1
                )
            WHERE a.current_tier_id != expected.tier_id
            GROUP BY actual.tier_name, expected.tier_name
            ORDER BY total DESC
            """
        ).fetchall()

        for row in distribution:
            print(
                f"Actual: {row['actual_tier']:<10} "
                f"Expected: {row['expected_tier']:<10} "
                f"Count: {row['total']}"
            )

        print("\nFIRST 15 MISMATCHES")
        print("-" * 65)

        for row in mismatches[:15]:
            print(dict(row))

    finally:
        connection.close()


if __name__ == "__main__":
    for name, db_path in DATABASES.items():
        inspect_database(name, db_path)
