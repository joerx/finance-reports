import logging
import sys
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from data import load_data, last_12_months

log = logging.getLogger(__name__)

try:
    df = load_data()
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

df = df[df["account_type"] == "income"]
# Income splits are stored as negative values (credit-normal); negate to show as positive
df["amount"] = -df["amount"]

months = last_12_months()
month_labels = [date(y, m, 1).strftime("%Y-%m") for y, m in months]

df["year"]    = df["year"].astype(int)
df["month"]   = df["month"].astype(int)
df["account"] = df["account"].str.removeprefix("Income/")

# Top 10 sources by total income across the period
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

month_index = pd.MultiIndex.from_tuples(months, names=["year", "month"])
pivot = pivot.reindex(month_index, fill_value=0)

ordered_cols = [c for c in top10 if c in pivot.columns]
if "Other" in pivot.columns:
    ordered_cols.append("Other")
pivot = pivot[ordered_cols]
pivot.index = month_labels

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

st.subheader("Monthly income — last 12 months")
chart_event = st.altair_chart(bars, on_select="rerun", use_container_width=True)

st.divider()

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
    st.subheader(f"Sources — {month_label}")
    by_cat = (
        sel_df.groupby("account")["amount"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"account": "Source", "amount": "Total (£)"})
    )
    total_row = pd.DataFrame([{"Source": "Total", "Total (£)": by_cat["Total (£)"].sum()}])
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
    if table_sel and table_sel[0] < len(by_cat) - 1:
        active_cat = by_cat.iloc[table_sel[0]]["Source"]
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
        st.caption("Select a source to view transactions.")
