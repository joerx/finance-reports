import logging
import os
import duckdb
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import dotenv

dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def get_auth_user():
    """Extract authenticated user info from proxy-injected request headers."""
    headers = st.context.headers
    log.info("Request headers: %s", dict(headers))
    return {
        "user":   headers.get("X-Auth-Request-User"),
        "email":  headers.get("X-Auth-Request-Email"),
        "groups": headers.get("X-Auth-Request-Groups"),
    }

BUCKET = os.environ["S3_BUCKET"]
ENDPOINT = os.environ["S3_ENDPOINT"]
REGION = os.environ.get("S3_REGION", "eu-central-1")
QUARTER_MONTHS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}


def _make_connection():
    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"""
        CREATE OR REPLACE SECRET linode_s3 (
            TYPE       s3,
            KEY_ID     '{os.environ["AWS_ACCESS_KEY_ID"]}',
            SECRET     '{os.environ["AWS_SECRET_ACCESS_KEY"]}',
            ENDPOINT   '{ENDPOINT}',
            REGION     '{REGION}',
            URL_STYLE  'path'
        )
    """)
    return con


@st.cache_data(show_spinner="Loading expenses from S3 ...")
def load_data(quarter: str) -> pd.DataFrame:
    year_str, q_str = quarter.split("-")
    year = int(year_str)
    q = int(q_str[1])
    month_start, month_end = QUARTER_MONTHS[q]

    glob = f"s3://{BUCKET}/expenses/year={year}/**/*.parquet"
    con = _make_connection()
    return con.sql(f"""
        SELECT * FROM read_parquet('{glob}', hive_partitioning = true)
        WHERE CAST(month AS INTEGER) BETWEEN {month_start} AND {month_end}
    """).df()


def main():
    plt.style.use("dark_background")
    st.set_page_config(page_title="Expense Dashboard", layout="wide")

    auth = get_auth_user()

    with st.sidebar:
        st.title("Expense Dashboard")
        if auth["user"] or auth["email"]:
            name = auth["user"] or auth["email"]
            st.caption(f"Signed in as **{name}**")
            if auth["email"] and auth["email"] != auth["user"]:
                st.caption(auth["email"])
        else:
            st.caption("Welcome, guest")
        st.divider()
        quarter = st.text_input("Quarter (YYYY-QN)", value="2026-Q1")

    try:
        df = load_data(quarter)
    except Exception as e:
        st.error(f"Could not load data for **{quarter}**: {e}")
        return

    # All categories sorted by spend, percentages relative to grand total
    by_cat = (
        df.groupby("account")["amount"]
        .sum()
        .rename(lambda a: a.removeprefix("Expenses/"))
        .sort_values(ascending=False)
    )

    grand_total = by_cat.sum()

    # Pie chart: top 10 slices + "Other" for the rest
    topN = by_cat.head(9)
    other = grand_total - topN.sum()
    pie_data = pd.concat([topN, pd.Series({"Other": other})]) if other > 0 else topN

    # Dataframe: all categories + totals row
    table = pd.DataFrame({
        "Category":  by_cat.index,
        "Total (£)": by_cat.values.round(2),
        "%":         (by_cat.values / grand_total * 100).round(1),
    }).reset_index(drop=True)
    table.loc[len(table)] = ["Total", round(grand_total, 2), 100.0]

    col_chart, col_table = st.columns([0.4, 0.6])

    with col_chart:
        st.subheader(f"Top 10 expenses — {quarter}")
        fig, ax = plt.subplots()
        ax.pie(
            pie_data.values,
            labels=pie_data.index,
            autopct="%1.1f%%",
            startangle=140,
        )
        ax.axis("equal")
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    with col_table:
        st.subheader("Breakdown")
        event = st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Total (£)": st.column_config.NumberColumn(format="£%.2f"),
                "%":         st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

    # ── Transaction drill-down ────────────────────────────────────────────────

    selected_rows = event.selection.rows
    # Ignore clicks on the Total row (last row)
    if selected_rows and selected_rows[0] < len(table) - 1:
        selected_cat = table.iloc[selected_rows[0]]["Category"]

        tx = (
            df[df["account"].str.removeprefix("Expenses/") == selected_cat]
            [["date", "description", "amount"]]
            .sort_values("amount", ascending=False)
            .reset_index(drop=True)
            .rename(columns={"date": "Date", "description": "Description", "amount": "Amount (£)"})
        )

        st.divider()
        st.subheader(f"Transactions — {selected_cat}")
        st.dataframe(
            tx,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Amount (£)": st.column_config.NumberColumn(format="£%.2f"),
            },
        )


main()
