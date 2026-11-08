

import sys
from pathlib import Path

# Add the project root directory to Python's import path
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
import plotly.express as px

from app.database import get_connection
from app.audit import run_all_audits



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
            "SELECT * FROM customers", connection
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
            "SELECT * FROM orders", connection
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


customers, accounts, orders, transactions = load_data()


# Sidebar
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


# Overview
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

            st.plotly_chart(fig, use_container_width=True)

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

            st.plotly_chart(fig, use_container_width=True)


# Customers
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

        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No customer accounts available.")


# Transactions
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


# Audit Intelligence
elif page == "Audit Intelligence":

    st.subheader("Audit Intelligence")

    if st.button("Run Audit Checks"):

        with st.spinner("Checking database integrity..."):

            results = run_all_audits()

        st.write("### Audit Results")

        st.json(results)

        st.success(
            "Audit execution completed. Review the results above."
        )

    st.info(
        "Run the audit to inspect ledger balances, "
        "foreign keys and order arithmetic."
    )


st.sidebar.divider()

st.sidebar.caption(
    "YottaFlex AI Technologies | Loyalty Ledger v1.0"
)

