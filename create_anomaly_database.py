import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

SOURCE_DB = ROOT_DIR / "data" / "loyalty.db"
ANOMALY_DB = ROOT_DIR / "data" / "loyalty_anomaly.db"


def create_database_copy():
    if not SOURCE_DB.exists():
        print("ERROR: Original database not found.")
        return

    if ANOMALY_DB.exists():
        print("ERROR: Anomaly database already exists.")
        print("No existing database was overwritten.")
        return

    source = None
    destination = None

    try:
        source = sqlite3.connect(SOURCE_DB)
        destination = sqlite3.connect(ANOMALY_DB)

        # Use SQLite's backup API for a consistent copy,
        # including any committed changes in the WAL.
        source.backup(destination)

        # Verify the copied database.
        source_tables = source.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' ORDER BY name"
        ).fetchall()

        copied_tables = destination.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' ORDER BY name"
        ).fetchall()

        if source_tables != copied_tables:
            raise RuntimeError("Database table verification failed.")

        source_count = source.execute(
            "SELECT COUNT(*) FROM customers"
        ).fetchone()[0]

        copied_count = destination.execute(
            "SELECT COUNT(*) FROM customers"
        ).fetchone()[0]

        if source_count != copied_count:
            raise RuntimeError("Customer count verification failed.")

        integrity = destination.execute(
            "PRAGMA integrity_check"
        ).fetchone()[0]

        if integrity != "ok":
            raise RuntimeError(
                f"Database integrity check failed: {integrity}"
            )

        print("Anomaly database created successfully.")
        print(f"Original database: {SOURCE_DB}")
        print(f"Anomaly database:  {ANOMALY_DB}")
        print(f"Tables copied: {len(copied_tables)}")
        print(f"Customers copied: {copied_count}")
        print(f"Integrity check: {integrity}")

    except Exception as error:
        print(f"ERROR: {error}")

        if ANOMALY_DB.exists():
            ANOMALY_DB.unlink()

    finally:
        if source is not None:
            source.close()

        if destination is not None:
            destination.close()


if __name__ == "__main__":
    create_database_copy()
    