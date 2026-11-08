
import json
from pathlib import Path

from app.audit import run_all_audits, compare_ground_truth

ROOT = Path(__file__).resolve().parent

DATABASE = ROOT / "data" / "loyalty_anomaly.db"
GROUND_TRUTH = ROOT / "data" / "generated" / "ground_truth.json"


def main():
    print("\nYOTTAFLEX ANOMALY DETECTION TEST")
    print("=" * 55)

    results = run_all_audits(DATABASE)

    categories = [
        "balance_mismatches",
        "over_redemptions",
        "returns_without_reversal",
        "duplicate_expiries",
        "incorrect_tiers",
    ]

    print("\nDETECTION RESULTS")
    print("-" * 55)

    for category in categories:
        records = results.get(category, [])

        print(f"\n{category}: {len(records)}")

        for record in records:
            print(json.dumps(record, indent=2))

    print("\nGROUND TRUTH COMPARISON")
    print("-" * 55)

    comparison = compare_ground_truth(
        results,
        GROUND_TRUTH
    )

    print(json.dumps(comparison, indent=2))

    print("\nSUMMARY")
    print("-" * 55)
    print("Expected anomalies:", comparison["expected_count"])
    print("Detected anomalies:", comparison["detected_count"])
    print("Matched anomalies:", comparison["matched_count"])
    print("Missed anomalies:", len(comparison["missed"]))
    print("Unexpected anomalies:", len(comparison["unexpected"]))
    print("Precision:", round(comparison["precision"], 2))
    print("Recall:", round(comparison["recall"], 2))


if __name__ == "__main__":
    main()
