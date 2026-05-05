import logging
import os
from datetime import date

import altair as alt
import duckdb
import pandas as pd
import streamlit as st
import dotenv

dotenv.load_dotenv()

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BUCKET = os.environ["S3_BUCKET"]
ENDPOINT = os.environ["S3_ENDPOINT"]
REGION = os.environ.get("S3_REGION", "eu-central-1")


def get_auth_user():
    """Extract authenticated user info from proxy-injected request headers."""
    headers = st.context.headers
    log.info("Request headers: %s", dict(headers))
    return {
        "user":   headers.get("X-Auth-Request-User"),
        "email":  headers.get("X-Auth-Request-Email"),
        "groups": headers.get("X-Auth-Request-Groups"),
    }


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


def _last_12_months() -> list[tuple[int, int]]:
    today = date.today()
    months = []
    for i in range(11, -1, -1):
        m = today.month - i
        y = today.year
        if m <= 0:
            m += 12
            y -= 1
        months.append((y, m))
    return months


@st.cache_data(show_spinner="Loading expenses ...")
def load_data() -> pd.DataFrame:
    months = _last_12_months()
    conditions = " OR ".join(
        f"(CAST(year AS INTEGER) = {y} AND CAST(month AS INTEGER) = {m})"
        for y, m in months
    )
    glob = f"s3://{BUCKET}/gnucash/**/*.parquet"
    con = _make_connection()
    return con.sql(f"""
        SELECT * FROM read_parquet('{glob}', hive_partitioning = true)
        WHERE {conditions}
    """).df()


def main():
    st.set_page_config(page_title="Expense Dashboard", layout="wide", page_icon=":bar_chart:")

    auth = get_auth_user()

    try:
        df = load_data()
    except Exception as e:
        st.error(f"Could not load data: {e}")
        return

    df = df[df["account_type"] == "expenses"]

    months = _last_12_months()
    month_labels = [date(y, m, 1).strftime("%Y-%m") for y, m in months]

    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    df["account"] = df["account"].str.removeprefix("Expenses/")

    # Top 10 categories by total spend across the period
    top10 = (
        df.groupby("account")["amount"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .index.tolist()
    )

    df["category"] = df["account"].where(df["account"].isin(top10), "Other")

    pivot = (
        df.groupby(["year", "month", "category"])["amount"]
        .sum()
        .unstack(fill_value=0)
    )

    # Ensure all 12 months are present, fill missing with 0
    month_index = pd.MultiIndex.from_tuples(months, names=["year", "month"])
    pivot = pivot.reindex(month_index, fill_value=0)

    # Top 10 columns in descending total order, Other last
    ordered_cols = [c for c in top10 if c in pivot.columns]
    if "Other" in pivot.columns:
        ordered_cols.append("Other")
    pivot = pivot[ordered_cols]
    pivot.index = month_labels

    # Long format for bars
    pivot_long = (
        pivot
        .reset_index(names="month")
        .melt(id_vars="month", var_name="category", value_name="amount")
    )
    pivot_long["order"] = pivot_long["category"].map(
        {cat: i for i, cat in enumerate(ordered_cols)}
    )

    bar_select = alt.selection_point(fields=["month", "category"], name="bar_select")

    bars = (
        alt.Chart(pivot_long)
        .mark_bar()
        .encode(
            x=alt.X("month:O", sort=None, title=None),
            y=alt.Y("sum(amount):Q", title="Amount (£)"),
            color=alt.Color("category:N", sort=ordered_cols, legend=alt.Legend(title=None)),
            order=alt.Order("order:Q"),
        )
        .add_params(bar_select)
        .configure(background="#1e293b")
        .configure_view(stroke=None)
    )

    st.subheader("Monthly expenses — last 12 months")
    chart_event = st.altair_chart(bars, on_select="rerun", use_container_width=True)

    today = date.today()
    chart_sel = chart_event.selection.get("bar_select", [])
    if chart_sel:
        sel_month_str = chart_sel[0].get("month")
        chart_cat = chart_sel[0].get("category")
        sel_year, sel_month_num = map(int, sel_month_str.split("-"))
    else:
        sel_year, sel_month_num = today.year, today.month
        chart_cat = None

    sel_df = df[(df["year"] == sel_year) & (df["month"] == sel_month_num)]
    month_label = date(sel_year, sel_month_num, 1).strftime("%B %Y")

    col_cats, col_tx = st.columns([0.4, 0.6])

    with col_cats:
        st.subheader(f"Categories — {month_label}")
        by_cat = (
            sel_df.groupby("account")["amount"]
            .sum()
            .sort_values(ascending=False)
            .reset_index()
            .rename(columns={"account": "Category", "amount": "Total (£)"})
        )
        total_row = pd.DataFrame([{"Category": "Total", "Total (£)": by_cat["Total (£)"].sum()}])
        by_cat = pd.concat([by_cat, total_row], ignore_index=True)

        table_event = st.dataframe(
            by_cat,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Total (£)": st.column_config.NumberColumn(format="£%.2f"),
            },
        )

    with col_tx:
        table_sel = table_event.selection.rows
        # Table row click takes priority over chart category; ignore the Total row
        if table_sel and table_sel[0] < len(by_cat) - 1:
            active_cat = by_cat.iloc[table_sel[0]]["Category"]
        elif chart_cat:
            active_cat = chart_cat
        else:
            active_cat = None

        if active_cat:
            st.subheader(f"Transactions — {active_cat}")
            tx = (
                sel_df[sel_df["account"] == active_cat]
                [["date", "description", "amount"]]
                .sort_values("amount", ascending=False)
                .reset_index(drop=True)
                .rename(columns={"date": "Date", "description": "Description", "amount": "Amount (£)"})
            )
            st.dataframe(
                tx,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Amount (£)": st.column_config.NumberColumn(format="£%.2f"),
                },
            )
        else:
            st.subheader("Transactions")
            st.caption("Select a category to view transactions.")


main()
