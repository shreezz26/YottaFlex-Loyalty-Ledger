
# YottaFlex Loyalty Ledger & Audit Intelligence System

A Python-based loyalty points management and audit intelligence platform developed for the YottaFlex AI Technologies 72-Hour Coding Challenge.

## Project Overview

The YottaFlex Loyalty Ledger manages the complete lifecycle of customer loyalty points.

The platform supports:
- Customer and loyalty account management
- Loyalty points accrual
- Reward redemption
- Points reversal for returned orders
- Points expiry
- Customer tier progression
- Transaction history
- Database integrity checks
- Audit reporting

## Problem Statement

Loyalty platforms must accurately manage points earned, redeemed, reversed, and expired.

Incorrect balances, duplicate transactions, invalid redemptions, and inaccurate tier calculations can cause financial and operational problems.

This project aims to provide a structured, auditable loyalty ledger with traceable transaction records.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application development |
| SQLite | Database |
| FastAPI | Backend REST API |
| Streamlit | Interactive dashboard |
| Pandas | Data analysis |
| Plotly | Data visualization |
| Pytest | Automated testing |
| YAML | Configuration management |
| Git | Version control |

## Project Structure

```text
YottaFlex-Loyalty-Ledger/
│
├── app/
│   ├── database.py
│   ├── tier_engine.py
│   ├── ledger_engine.py
│   ├── audit.py
│   └── main.py
│
├── generator/
│   ├── generate.py
│   └── transactions.py
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
│   └── DATA_DICTIONARY.md
│
├── data/
├── exports/
├── config.yaml
├── requirements.txt
├── .gitignore
└── README.md
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/YottaFlex-Loyalty-Ledger.git
cd YottaFlex-Loyalty-Ledger
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

### 3. Activate the environment

Windows:

```cmd
venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

## Database Initialization

```bash
python -m app.database
```

## Generate Synthetic Data

Generate 100 customers and 500 orders:

```bash
python -m generator.generate --customers 100 --orders 500 --seed 20261022
```

Generate points accrual transactions:

```bash
python -m generator.transactions
```

The random seed makes the master-data generation reproducible for the same configuration and parameters.

## Run the Backend API

```bash
uvicorn app.main:app --reload
```

API URL:

http://127.0.0.1:8000

Interactive API documentation:

http://127.0.0.1:8000/docs

## Run the Dashboard

```bash
python -m streamlit run dashboard/dashboard.py
```

Dashboard URL:

http://localhost:8501

## Run Automated Tests

```bash
python -m pytest -v
```

## Database and Audit Documentation

Refer to:

`docs/DATA_DICTIONARY.md`

This document describes the database entities, identifiers, relationships, and business rules.

## Synthetic Dataset

The current development dataset is generated locally using configurable parameters.

Default random seed:

`20261022`

Current demonstration scale:

- 100 customers
- 100 loyalty accounts
- 500 orders
- 1,012 order lines
- 500 accrual transactions

## Development Status

The current implementation includes:
- Database schema
- Synthetic master-data generation
- Points accrual generation
- FastAPI endpoints
- Streamlit dashboard
- Initial automated audit tests
- Initial data dictionary

Further development is required for:
- Complete redemption and reversal event generation
- Expiry event generation
- Comprehensive tier progression
- Five required labelled anomaly scenarios
- Ground-truth dataset export
- Full validation and reproducibility checks
- SQL, CSV, and JSON exports

## Disclaimer

This project uses synthetic data for demonstration and testing. No real customer or financial information is included.

## Author

Developed as part of the YottaFlex AI Technologies coding challenge.
