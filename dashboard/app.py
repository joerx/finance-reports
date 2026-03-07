import os
import duckdb
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

plt.style.use("dark_background")

BUCKET   = "dev-finance-reports-cfvd"
ENDPOINT = "eu-central-1.linodeobjects.com"
REGION   = "eu-central-1"

st.set_page_config(page_title="Expense Dashboard", layout="wide")


def _make_connection():
    con = duckdb.connect()
    con.install_extension("httpfs")
    con.load_extension("httpfs")
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
    url = f"s3://{BUCKET}/expenses/expenses_{quarter}.parquet"
    con = _make_connection()
    return con.sql(f"SELECT * FROM '{url}'").df()


def main():
    with st.sidebar:
        st.title("Expense Dashboard")
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
