
import csv
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "loyalty.db"
EXPORT_DIR = ROOT / "exports"
EXPORT_DIR.mkdir(exist_ok=True)


def export_database():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    try:
        tables = [
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        ]

        summary = {
            "database": "loyalty.db",
            "seed": 20261022,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tables": {},
            "foreign_key_violations": [],
            "integrity_check": ""
        }

        for table in tables:
            rows = [
                dict(row)
                for row in connection.execute(
                    f'SELECT * FROM "{table}"'
                ).fetchall()
            ]

            columns = [
                row["name"]
                for row in connection.execute(
                    f'PRAGMA table_info("{table}")'
                ).fetchall()
            ]

            csv_path = EXPORT_DIR / f"{table}.csv"
            json_path = EXPORT_DIR / f"{table}.json"

            with open(csv_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)

            with open(json_path, "w", encoding="utf-8") as file:
                json.dump(rows, file, indent=2, ensure_ascii=False)

            summary["tables"][table] = len(rows)
            print(f"{table}: {len(rows):,} rows exported")

        violations = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        summary["foreign_key_violations"] = [
            list(row) for row in violations
        ]

        summary["integrity_check"] = connection.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        with open(
            EXPORT_DIR / "validation_summary.json",
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(summary, file, indent=2)

        print("\nEXPORT COMPLETED")
        print("Integrity:", summary["integrity_check"])
        print("Foreign key violations:", len(violations))
        print("Files saved in:", EXPORT_DIR)

    finally:
        connection.close()


if __name__ == "__main__":
    export_database()

