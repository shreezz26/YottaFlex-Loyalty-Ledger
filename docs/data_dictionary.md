
# YottaFlex Loyalty Ledger
## Database Schema and Data Dictionary

### 1. Project Overview

The YottaFlex Loyalty Ledger is a loyalty points management and audit intelligence system.

It manages:
- Customer registration
- Loyalty account management
- Points accrual
- Points redemption
- Points reversal
- Points expiry
- Loyalty tier progression
- Financial and transaction auditing

---

### 2. Database Entities

| Entity | Description |
|---|---|
| Customer | Stores customer information |
| LoyaltyAccount | Stores loyalty account and balance |
| Tier | Defines loyalty membership levels |
| Rule | Defines loyalty earning rules |
| Order | Stores customer purchases |
| OrderLine | Stores individual products in an order |
| PointsTransaction | Maintains the immutable points ledger |
| PointLot | Tracks points by accrual and expiry date |
| Reward | Stores available redemption rewards |
| Redemption | Stores customer reward redemptions |
| ExpiryBatch | Records points expiry operations |
| TierHistory | Tracks customer tier changes |
| AuditIssue | Records identified data-quality issues |

---

### 3. Primary Keys and Foreign Keys

| Entity | Primary Key | Foreign Key |
|---|---|---|
| Customer | customer_id | None |
| LoyaltyAccount | account_id | customer_id, current_tier_id |
| Tier | tier_id | None |
| Rule | rule_id | None |
| Order | order_id | customer_id |
| OrderLine | line_id | order_id |
| PointsTransaction | transaction_id | account_id, order_id |
| PointLot | lot_id | account_id, source_transaction_id |
| Reward | reward_id | None |
| Redemption | redemption_id | account_id, reward_id |
| ExpiryBatch | batch_id | None |
| TierHistory | history_id | account_id, tier_id |
| AuditIssue | issue_id | None |

---

### 4. Important Business Rules

#### Points Accrual
Points are calculated using:

Points = Eligible Net Spend × Earning Rate

#### Points Redemption
A customer cannot redeem more points than their available balance.

#### Points Reversal
Returned orders must have their previously earned points reversed.

#### Points Expiry
Points are tracked by individual lots and expire according to their validity period.

#### Tier Progression
A customer's tier is determined by qualifying spend.

---

### 5. Identifier Standards

| Record | Format |
|---|---|
| Customer | CUS-000001 |
| Loyalty Account | LOY-CUS-000001 |
| Order | ORD-2026-000001 |
| Points Transaction | PTS-2026-00000001 |
| Redemption | RDM-2026-000001 |
| Expiry Batch | EXP-2026-000001 |

---

### 6. Data Integrity

The system uses:
- Primary key constraints
- Foreign key constraints
- Unique identifiers
- Transactional database operations
- Business-rule validation
- Ledger reconciliation
- Audit issue tracking

---

### 7. Synthetic Data Generation

The synthetic dataset is generated using a configurable random seed.

Default seed: `20261022`

Generation parameters are maintained in `config.yaml`.

The generated dataset is intended for testing and demonstration purposes.
