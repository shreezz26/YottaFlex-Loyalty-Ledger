# YottaFlex Loyalty Ledger — Business Rules

## 1. Purpose

The YottaFlex Loyalty Ledger manages customer loyalty accounts, point accruals, redemptions, returns, reversals, expirations, and membership tier progression.

All balance-changing operations must be represented by explicit ledger transactions. Historical transaction records must be preserved for auditing.

## 2. Customer and Account Rules

1. Every customer must have a unique customer ID.
2. Every customer can have one loyalty account.
3. Every loyalty account must reference an existing customer.
4. Account IDs follow the format `LOY-<customer-id>`.
5. Account statuses are `ACTIVE`, `SUSPENDED`, or `CLOSED`.
6. Only active accounts can perform successful redemptions.

## 3. Loyalty Tier Rules

1. Each tier has a minimum qualifying spend and an earning rate.
2. Qualifying spend is calculated using eligible net order amounts.
3. Net order amount is calculated as:

   `Net Amount = Gross Amount - Discount Amount`

4. Refunds reduce the qualifying net spend of an order.
5. The customer's eligible tier is the highest tier whose minimum spend does not exceed qualifying spend.
6. Tier changes must be recorded in `tier_history`.
7. Previous tier history must not be overwritten.

## 4. Points Accrual Rules

1. Points are awarded only for eligible completed orders.
2. Points are calculated using the applicable tier earning rate:

   `Earned Points = Floor(Eligible Net Amount × Earning Rate)`

3. Every accrual creates a `points_transactions` record.
4. Every accrual must create a corresponding point lot.
5. Each point lot must reference its source accrual transaction.
6. Each lot must have a creation date and expiry date.
7. Points must not be awarded twice for the same order.

## 5. Redemption Rules

1. A redemption must reference an existing loyalty account and reward.
2. The account must have sufficient available points.
3. Available points must be determined from eligible, unexpired point lots.
4. Successful redemption must:
   - Create a redemption record.
   - Create a `REDEMPTION` ledger transaction.
   - Deduct the redeemed points from the account balance.
   - Consume points from eligible lots.
5. Point lots must be consumed using First Expiry, First Out (FEFO).
6. A redemption must never produce a negative account balance.
7. Rejected redemption attempts must be recorded without deducting points or creating a successful redemption ledger transaction.

## 6. Returns and Reversals

1. A return must reference an existing order.
2. Return amounts must not exceed the eligible original order amount.
3. Partial returns and full returns must be supported.
4. Earned points must be reversed proportionally to the cumulative returned amount.
5. Every points reversal must create a `REVERSAL` ledger transaction.
6. Reversed points must be removed from the corresponding point lots where available.
7. Return records must preserve their original transaction references.
8. A fully returned order must not retain un-reversed earned points.
9. Return history must not be silently overwritten.

## 7. Points Expiration Rules

1. Every point lot has an expiry date.
2. Only active lots with remaining points can expire.
3. Expiration is permitted only when the lot expiry date has passed.
4. Expiration creates an `EXPIRY` ledger transaction.
5. Expiration must create one corresponding expiry batch record.
6. The lot's remaining points become zero after expiration.
7. An expired lot must not be expired again.
8. Expired points must be deducted from the account balance.

## 8. Ledger and Balance Rules

1. The transaction ledger is the authoritative history of point movements.
2. Account balances must reconcile with their ledger transactions.
3. Accruals and adjustments increase balances.
4. Redemptions, reversals, and expirations decrease balances.
5. Every balance-changing operation must have an explicit transaction record.
6. Historical ledger records must not be deleted or overwritten to hide previous activity.

Balance reconciliation:

`Stored Balance = Accruals + Adjustments - Redemptions - Reversals - Expirations`

## 9. Identifier Standards

| Entity | Identifier format |
|---|---|
| Loyalty account | `LOY-<customer-id>` |
| Order | `ORD-2026-000001` |
| Points transaction | `PTS-2026-00000001` |
| Redemption | `RDM-000001` |
| Expiry | `EXP-000001` |

Identifiers must be unique within their respective entities.

## 10. Audit and Anomaly Detection Rules

The audit engine must detect the following deliberately injected anomaly categories:

| Issue ID | Anomaly | Detection rule |
|---|---|---|
| ANM-001 | Balance mismatch | Stored account balance differs from calculated ledger balance |
| ANM-002 | Over-redemption | Requested redemption exceeds available points |
| ANM-003 | Return without reversal | A completed return has insufficient corresponding points reversal |
| ANM-004 | Duplicate expiry | The same point lot has multiple expiry records |
| ANM-005 | Incorrect tier calculation | Assigned tier does not match qualifying spend |

Anomaly labels must be derived from documented business rules and stored separately from the input dataset.

## 11. Data Integrity Rules

The system must validate:

- Primary key uniqueness.
- Foreign key integrity.
- Valid transaction and account status values.
- Valid order and return relationships.
- Date and lifecycle consistency.
- Order amount arithmetic.
- Account balance reconciliation.
- Point-lot balance constraints.
- Duplicate accrual and expiry prevention.
- Tier eligibility.

## 12. Synthetic Dataset and Reproducibility

The generated dataset uses random seed `20261022`.

Full-scale generation configuration:

- Customers: 20,000
- Loyalty accounts: 20,000
- Orders: 100,000
- Order lines: 199,923 in the current generated dataset
- Points transactions: 320,352 in the current generated dataset

Synthetic data is generated programmatically and does not represent real customer information.

The generator must produce deterministic results when run with the same seed and configuration.

## 13. Ground-Truth Separation

The anomaly ground-truth records are maintained separately in:

- `data/generated/ground_truth.json`
- `data/generated/ground_truth.csv`

Ground-truth labels must not be included as input features for anomaly detection.

The current labelled anomaly scenarios are test cases for evaluating audit detection performance.

## 14. Expected Audit Outcome

The five injected anomaly scenarios were successfully detected in the current test:

- Expected anomalies: 5
- Detected anomalies: 5
- Matched anomalies: 5
- Missed anomalies: 0
- Unexpected anomalies: 0
- Precision: 100%
- Recall: 100%

These results represent the current five-case anomaly test, not a guarantee of detection accuracy on every possible dataset.

## 10. Audit and Anomaly Rules

The audit engine evaluates:

- BALANCE_MISMATCH: stored balance differs from ledger balance.
- OVER_REDEMPTION: attempted redemption exceeds available points.
- RETURN_WITHOUT_REVERSAL: completed return lacks sufficient points reversal.
- DUPLICATE_EXPIRY: the same lot has multiple expiry records.
- INCORRECT_TIER_CALCULATION: assigned tier does not match qualifying spend.

Ground-truth labels are stored separately and must not be used as input features.

## 11. Data Integrity

Validate primary keys, foreign keys, allowed statuses, date ordering, order arithmetic, point-lot constraints, duplicate events, and balance reconciliation.

## 12. Reproducibility

- Random seed: 20261022.
- Customers: 20,000.
- Orders: 100,000.
- Generated ledger transactions: 320,352.
- Synthetic records do not represent real customer information.
- The same seed and configuration should reproduce the same generated data.

## 13. Ground Truth

Ground truth is maintained separately in:

- `data/generated/ground_truth.json`
- `data/generated/ground_truth.csv`

Five labelled anomaly scenarios are included.

Current test results: 5 expected, 5 detected, 5 matched, 0 missed, 0 unexpected; precision 100%, recall 100%.

These metrics describe the five injected test cases and do not guarantee general anomaly detection accuracy.