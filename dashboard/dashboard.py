
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
import plotly.express as px

from app.database import get_connection
from app.audit import run_all_audits, compare_ground_truth


MAIN_DB = PROJECT_ROOT / "data" / "loyalty.db"
ANOMALY_DB = PROJECT_ROOT / "data" / "loyalty_anomaly.db"
GROUND_TRUTH = (
    PROJECT_ROOT / "data" / "generated" / "ground_truth.json"
)


st.set_page_config(
    page_title="YottaFlex Loyalty Intelligence",
    page_icon="💎",
    layout="wide"
)

st.title("💎 YottaFlex Loyalty Ledger")
st.caption("AI-powered Loyalty Management & Audit Intelligence System")


@st.cache_data(ttl=10)
def load_data():
    connection = get_connection()

    try:
        customers = pd.read_sql_query(
            "SELECT * FROM customers",
            connection
        )

        accounts = pd.read_sql_query(
            """
            SELECT
                a.account_id,
                a.customer_id,
                a.stored_balance,
                a.qualifying_spend,
                t.tier_name
            FROM loyalty_accounts a
            LEFT JOIN tiers t
                ON a.current_tier_id = t.tier_id
            """,
            connection
        )

        orders = pd.read_sql_query(
            "SELECT * FROM orders",
            connection
        )

        transactions = pd.read_sql_query(
            """
            SELECT *
            FROM points_transactions
            ORDER BY transaction_date DESC
            """,
            connection
        )

        return customers, accounts, orders, transactions

    finally:
        connection.close()


@st.cache_data(ttl=10)
def load_audit_results():
    if not ANOMALY_DB.exists():
        return None, None, None

    results = run_all_audits(str(ANOMALY_DB))

    comparison = None

    if GROUND_TRUTH.exists():
        comparison = compare_ground_truth(
            results,
            GROUND_TRUTH
        )

    return results, comparison, None


customers, accounts, orders, transactions = load_data()


st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Select Module",
    [
        "Overview",
        "Customers",
        "Transactions",
        "Audit Intelligence"
    ]
)


if page == "Overview":

    st.subheader("Business Overview")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Customers",
        f"{len(customers):,}"
    )

    col2.metric(
        "Loyalty Accounts",
        f"{len(accounts):,}"
    )

    col3.metric(
        "Total Orders",
        f"{len(orders):,}"
    )

    total_points = (
        transactions.loc[
            transactions["transaction_type"] == "ACCRUAL",
            "points"
        ].sum()
        if not transactions.empty else 0
    )

    col4.metric(
        "Points Issued",
        f"{total_points:,.0f}"
    )

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("Customer Tier Distribution")

        if not accounts.empty:
            tier_data = (
                accounts["tier_name"]
                .fillna("Unknown")
                .value_counts()
                .reset_index()
            )

            tier_data.columns = ["Tier", "Customers"]

            fig = px.pie(
                tier_data,
                names="Tier",
                values="Customers",
                hole=0.45
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

    with right:
        st.subheader("Points Transaction Types")

        if not transactions.empty:
            transaction_data = (
                transactions["transaction_type"]
                .value_counts()
                .reset_index()
            )

            transaction_data.columns = [
                "Transaction Type",
                "Count"
            ]

            fig = px.bar(
                transaction_data,
                x="Transaction Type",
                y="Count",
                text="Count"
            )

            st.plotly_chart(
                fig,
                use_container_width=True
            )


elif page == "Customers":

    st.subheader("Customer Loyalty Accounts")

    if not accounts.empty:

        search = st.text_input(
            "Search by Customer ID or Account ID"
        )

        filtered = accounts.copy()

        if search:
            filtered = filtered[
                filtered["customer_id"].str.contains(
                    search,
                    case=False,
                    na=False
                )
                |
                filtered["account_id"].str.contains(
                    search,
                    case=False,
                    na=False
                )
            ]

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True
        )

        st.subheader("Customer Balance Distribution")

        fig = px.histogram(
            accounts,
            x="stored_balance",
            nbins=20,
            title="Points Balance Distribution"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    else:
        st.info("No customer accounts available.")


elif page == "Transactions":

    st.subheader("Points Transaction History")

    if not transactions.empty:

        transaction_types = sorted(
            transactions["transaction_type"].dropna().unique()
        )

        selected_type = st.selectbox(
            "Filter by Transaction Type",
            ["All"] + list(transaction_types)
        )

        filtered = transactions.copy()

        if selected_type != "All":
            filtered = filtered[
                filtered["transaction_type"] == selected_type
            ]

        st.dataframe(
            filtered,
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Download Transactions CSV",
            data=filtered.to_csv(index=False),
            file_name="loyalty_transactions.csv",
            mime="text/csv"
        )

    else:
        st.info("No transactions available.")


elif page == "Audit Intelligence":

    st.subheader("🔍 Audit Intelligence")
    st.caption(
        "Auditing the separate anomaly database against documented "
        "ground-truth labels."
    )

    if not ANOMALY_DB.exists():
        st.error(
            "Anomaly database not found: "
            f"{ANOMALY_DB}"
        )
        st.info(
            "Create the anomaly database and run the anomaly generator "
            "before using this module."
        )

    else:
        if st.button("Run Audit Checks", type="primary"):
            load_audit_results.clear()

        results, comparison, _ = load_audit_results()

        if results is not None:

            if comparison is not None:
                metric1, metric2, metric3, metric4 = st.columns(4)

                metric1.metric(
                    "Expected Anomalies",
                    comparison["expected_count"]
                )

                metric2.metric(
                    "Detected Anomalies",
                    comparison["detected_count"]
                )

                metric3.metric(
                    "Precision",
                    f'{comparison["precision"]:.0%}'
                )

                metric4.metric(
                    "Recall",
                    f'{comparison["recall"]:.0%}'
                )

                st.divider()

                if (
                    comparison["matched_count"]
                    == comparison["expected_count"]
                    and not comparison["missed"]
                    and not comparison["unexpected"]
                ):
                    st.success(
                        "All ground-truth anomalies were detected "
                        "with no unexpected detections."
                    )
                else:
                    st.warning(
                        "Audit results differ from the ground-truth "
                        "labels. Review the details below."
                    )

            st.subheader("Detected Anomaly Categories")

            categories = [
                ("Balance Mismatches", "balance_mismatches"),
                ("Over-Redemptions", "over_redemptions"),
                ("Returns Without Reversal", "returns_without_reversal"),
                ("Duplicate Expiries", "duplicate_expiries"),
                ("Incorrect Tier Calculations", "incorrect_tiers")
            ]

            category_columns = st.columns(5)

            for column, (label, key) in zip(
                category_columns,
                categories
            ):
                column.metric(
                    label,
                    len(results.get(key, []))
                )

            for label, key in categories:
                with st.expander(
                    f"{label} ({len(results.get(key, []))})",
                    expanded=True
                ):
                    records = results.get(key, [])

                    if records:
                        st.dataframe(
                            pd.DataFrame(records),
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.success("No issues detected.")

            st.divider()
            st.subheader("Database Integrity Checks")

            integrity_columns = st.columns(4)

            integrity_columns[0].metric(
                "Foreign Key Issues",
                len(results["foreign_key_issues"])
            )

            integrity_columns[1].metric(
                "Primary Key Issues",
                len(results["primary_key_issues"])
            )

            integrity_columns[2].metric(
                "Order Arithmetic Issues",
                len(results["arithmetic_issues"])
            )

            integrity_columns[3].metric(
                "Total Audit Issues",
                results["total_issues"]
            )

            if comparison is not None:
                st.subheader("Ground-Truth Comparison")

                st.json(comparison)

            st.download_button(
                "Download Audit Results JSON",
                data=__import__("json").dumps(
                    {
                        "audit_results": results,
                        "ground_truth_comparison": comparison
                    },
                    indent=2
                ),
                file_name="yottaflex_audit_results.json",
                mime="application/json"
            )

        else:
            st.error("Unable to load audit results.")


st.sidebar.divider()

st.sidebar.caption(
    "YottaFlex AI Technologies | Loyalty Ledger v1.0"
)
