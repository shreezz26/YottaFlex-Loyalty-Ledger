
from app.database import transaction


# ============================================================
# 1. CALCULATE CUSTOMER TIER
# ============================================================

def calculate_tier(qualifying_spend, tiers):
    """
    Select the highest tier eligible for the qualifying spend.
    """

    qualifying_spend = float(qualifying_spend)

    if qualifying_spend < 0:
        raise ValueError("Qualifying spend cannot be negative.")

    eligible_tiers = [
        tier for tier in tiers
        if qualifying_spend >= float(tier["minimum_spend"])
    ]

    if not eligible_tiers:
        raise ValueError("No eligible loyalty tier found.")

    return max(
        eligible_tiers,
        key=lambda tier: float(tier["minimum_spend"])
    )


# ============================================================
# 2. GENERATE SEQUENTIAL HISTORY ID
# ============================================================

def generate_history_id(connection):
    """
    Generate a unique sequential tier history ID.
    """

    last_record = connection.execute(
        """
        SELECT history_id
        FROM tier_history
        WHERE history_id LIKE 'TH-%'
        ORDER BY history_id DESC
        LIMIT 1
        """
    ).fetchone()

    if last_record is None:
        number = 1
    else:
        number = int(
            last_record["history_id"].split("-")[-1]
        ) + 1

    return f"TH-{number:08d}"


# ============================================================
# 3. UPDATE CUSTOMER TIER
# ============================================================

def update_customer_tier(account_id, qualifying_spend):
    """
    Calculate and update a customer's loyalty tier.

    A history record is created only when the tier changes.
    """

    qualifying_spend = float(qualifying_spend)

    if qualifying_spend < 0:
        raise ValueError("Qualifying spend cannot be negative.")

    with transaction() as connection:

        # Retrieve configured tiers.
        tiers = connection.execute(
            """
            SELECT
                tier_id,
                tier_name,
                minimum_spend,
                earning_rate
            FROM tiers
            ORDER BY minimum_spend ASC
            """
        ).fetchall()

        tier_data = [dict(row) for row in tiers]

        if not tier_data:
            raise ValueError("Tier master data is missing.")

        # Validate account.
        account = connection.execute(
            """
            SELECT
                account_id,
                current_tier_id,
                qualifying_spend,
                account_status
            FROM loyalty_accounts
            WHERE account_id = ?
            """,
            (account_id,)
        ).fetchone()

        if account is None:
            raise ValueError("Loyalty account not found.")

        if account["account_status"] != "ACTIVE":
            raise ValueError("Account is not active.")

        # Calculate eligible tier.
        selected_tier = calculate_tier(
            qualifying_spend,
            tier_data
        )

        old_tier_id = account["current_tier_id"]
        new_tier_id = selected_tier["tier_id"]

        tier_changed = old_tier_id != new_tier_id

        # Record the tier transition.
        if tier_changed:

            history_id = generate_history_id(connection)

            connection.execute(
                """
                INSERT INTO tier_history (
                    history_id,
                    account_id,
                    old_tier_id,
                    new_tier_id,
                    qualifying_spend,
                    changed_at
                )
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    history_id,
                    account_id,
                    old_tier_id,
                    new_tier_id,
                    qualifying_spend
                )
            )

        # Update account even if the tier remains unchanged.
        connection.execute(
            """
            UPDATE loyalty_accounts
            SET current_tier_id = ?,
                qualifying_spend = ?
            WHERE account_id = ?
            """,
            (
                new_tier_id,
                qualifying_spend,
                account_id
            )
        )

        return {
            "account_id": account_id,
            "previous_tier_id": old_tier_id,
            "current_tier_id": new_tier_id,
            "tier_name": selected_tier["tier_name"],
            "qualifying_spend": qualifying_spend,
            "earning_rate": selected_tier["earning_rate"],
            "tier_changed": tier_changed,
            "status": "UPDATED"
        }


# ============================================================
# 4. RECALCULATE TIER FROM ACCOUNT SPEND
# ============================================================

def recalculate_customer_tier(account_id):
    """
    Recalculate the tier using qualifying spend stored
    in the loyalty account.
    """

    with transaction() as connection:

        account = connection.execute(
            """
            SELECT qualifying_spend
            FROM loyalty_accounts
            WHERE account_id = ?
            """,
            (account_id,)
        ).fetchone()

        if account is None:
            raise ValueError("Loyalty account not found.")

        qualifying_spend = account["qualifying_spend"]

    return update_customer_tier(
        account_id,
        qualifying_spend
    )
