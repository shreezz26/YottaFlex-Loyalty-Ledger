# YottaFlex Loyalty Ledger & Audit Intelligence System

A Python-based loyalty points management, synthetic data generation, and audit intelligence platform developed for the **YottaFlex AI Technologies 72-Hour Coding Challenge**.

## 1. Project Overview

The YottaFlex Loyalty Ledger manages the lifecycle of customer loyalty points through an auditable transaction ledger.

The system supports:

- Customer and loyalty account management
- Loyalty tier progression
- Points accrual on eligible orders
- Reward redemption
- Full and partial returns with points reversals
- Points expiration using point lots
- Transaction history and balance reconciliation
- Synthetic anomaly injection and detection
- Database integrity validation
- CSV, JSON, and SQL data exports
- Interactive Streamlit audit dashboard

## 2. Problem Statement

Loyalty platforms must accurately manage points earned, redeemed, reversed, and expired.

Incorrect balances, duplicate expiry events, invalid redemptions, incomplete return reversals, and incorrect tier calculations can create financial and operational risks.

This project implements a structured loyalty ledger that maintains transaction traceability and provides audit mechanisms to identify data inconsistencies.

## 3. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application logic and data generation |
| SQLite | Relational database |
| FastAPI | Backend REST API |
| Streamlit | Interactive dashboard |
| Pandas | Data processing and analysis |
| Plotly | Data visualization |
| Pytest | Automated testing |
| YAML | Configuration |
| Git and GitHub | Version control |

## 4. System Architecture

The project is organized into four primary layers:

1. **Database layer:** Stores customers, accounts, tiers, orders, point lots, transactions, returns, redemptions, expiry records, and audit issues.
2. **Business logic layer:** Handles points accrual, redemption, returns, reversals, tier progression, and ledger operations.
3. **Data generation layer:** Generates reproducible synthetic master data and dependent loyalty events.
4. **Audit and visualization layer:** Injects labelled anomaly scenarios, runs audit checks, compares detections against ground truth, and displays results.

## 5. Dataset and Generation Results

The final generated demonstration dataset uses:

- Random seed: `20261022`
- Customers: **20,000**
- Loyalty accounts: **20,000**
- Orders: **100,000**
- Order lines: **199,923**
- Points transactions: **320,352**
- Accrual transactions: **100,000**
- Returns: **7,913**
- Redemptions: **116,143**
- Expiry records: **96,296**
- Point lots: **100,000**
- Tier history records: **37,040**

All records are synthetic and do not represent real customer information.

### Data generation

Create and activate a virtual environment, install dependencies, and initialize the database:

```bash
python -m venv venv
```

Windows activation:

```cmd
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Initialize the database:

```bash
python -m app.database
```

Generate master data using the configured scale and seed:

```bash
python -m generator.generate --customers 20000 --orders 100000 --seed 20261022
```

Generate loyalty events:

```bash
python -m generator.transactions --seed 20261022
```

Check the available command-line options with `--help` if you want to change generation parameters.

**Important:** The generation commands create or regenerate data. Run them against a fresh database or a backup when you want to reproduce the dataset; do not run them against your final database unless you intend to replace its contents.

## 6. Loyalty Business Rules

### Points accrual
- Points are awarded for eligible completed orders.
- Points are calculated using the applicable earning rate.
- Each accrual is recorded in the transaction ledger.
- Each accrual is associated with a point lot and expiry date.

### Redemption
- A redemption requires an existing account and reward.
- Available points must be sufficient.
- Eligible point lots are consumed using First Expiry, First Out (FEFO).
- Successful redemptions create ledger transactions.
- Account balances must not become negative.

### Returns and reversals
- Full and partial returns are supported.
- Reversals are recorded as separate ledger transactions.
- Original transaction references are retained for auditability.

### Expiration
- Only eligible lots with remaining points can expire.
- Expiration is recorded in the ledger and expiry batch history.
- An expired lot must not be expired twice.

### Tier progression
- Customer tiers are based on qualifying spend.
- Tier changes are maintained in tier history.

Refer to `docs/business_rules.md` for the detailed business rules.

## 7. Audit Intelligence

The system includes five labelled anomaly scenarios:

| Anomaly | Description |
|---|---|
| BALANCE_MISMATCH | Stored account balance differs from ledger balance |
| OVER_REDEMPTION | Redemption attempt exceeds available points |
| RETURN_WITHOUT_REVERSAL | Returned order retains points that should have been reversed |
| DUPLICATE_EXPIRY | A point lot has duplicate expiry evidence |
| INCORRECT_TIER_CALCULATION | Assigned tier does not match qualifying spend |

Ground-truth labels are maintained separately from the main loyalty dataset and must not be used as model input features.

### Audit validation results

| Metric | Result |
|---|---:|
| Expected anomalies | 5 |
| Detected anomalies | 5 |
| Matched anomalies | 5 |
| Missed anomalies | 0 |
| Unexpected anomalies | 0 |
| Precision | 100% |
| Recall | 100% |

These results represent the five injected test scenarios, not a guarantee of detection accuracy on arbitrary real-world data.

## 8. Data Integrity and Validation

The project validates:

- Primary key uniqueness
- Foreign key integrity
- Order arithmetic
- Account balance reconciliation
- Negative account balances
- Transaction ID uniqueness
- Ledger consistency
- SQLite database integrity

The final generated main database validation reported:

- Balance mismatches: 0
- Negative balances: 0
- Foreign key violations: 0
- SQLite integrity: `ok`

## 9. Exports and Documentation

The export utility generates table-level CSV and JSON files and a validation summary.

Run:

```bash
python export_data.py
```

The project also includes an SQL seed dump generated from the database.

Documentation:

- `docs/DATA_DICTIONARY.md` — database entities, fields, and relationships.
- `docs/business_rules.md` — loyalty business rules.
- `data/generated/ground_truth.json` — labelled anomaly records.
- `data/generated/ground_truth.csv` — CSV version of ground truth.

Generated databases and exports are kept locally and are excluded from Git where configured in `.gitignore`. Run the generation and export commands to create them locally.

## 10. Run the Application

### FastAPI backend

```bash
uvicorn app.main:app --reload
```

API:

`http://127.0.0.1:8000`

Interactive API documentation:

`http://127.0.0.1:8000/docs`

### Streamlit dashboard

```bash
python -m streamlit run dashboard/dashboard.py
```

Dashboard:

`http://localhost:8501`

The dashboard presents the loyalty data overview and audit intelligence results.

## 11. Run Automated Tests

Run the project test suite:

```bash
python -m pytest -v
```

Run the anomaly detection validation:

```bash
python test_anomaly_detection.py
```

The completed test run passed, and all five injected anomaly scenarios matched their ground-truth labels.

## 12. Project Structure

```text
YottaFlex-Loyalty-Ledger/
│
├── app/
│   ├── database.py
│   ├── tier_engine.py
│   ├── ledger_engine.py
│   ├── audit.py
│   ├── return_engine.py
│   └── main.py
│
├── generator/
│   ├── generate.py
│   ├── transactions.py
│   └── anomalies.py
│
├── dashboard/
│   └── dashboard.py
│
├── tests/
│   ├── conftest.py
│   ├── test_audit.py
│   └── test_ledger.py
│
├── docs/
│   ├── DATA_DICTIONARY.md
│   └── business_rules.md
│
├── data/
│   └── generated/
│
├── exports/
│
├── config.yaml
├── export_data.py
├── test_anomaly_detection.py
├── requirements.txt
├── .gitignore
└── README.md
```

## 13. Reproducibility and Data Provenance

The synthetic dataset uses a fixed random seed of `20261022` and configurable generation parameters.

No external customer dataset is required. All demonstration records are synthetically generated for development, validation, and testing.

For reproducibility, use the same seed and configuration. Compare generated row counts and validation results when recreating the dataset.

## 14. Disclaimer

This project is developed for demonstration and coding challenge purposes. It uses synthetic data and is not connected to a real loyalty platform or financial system.

## 15. Author

Developed as part of the **YottaFlex AI Technologies 72-Hour Coding Challenge**.

GitHub Repository:  
https://github.com/shreezz26/YottaFlex-Loyalty-Ledger