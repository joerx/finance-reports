import logging
import sys
import os
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

df = df[df["account_type"] == "expenses"]

months = last_12_months()
month_labels = [date(y, m, 1).strftime("%Y-%m") for y, m in months]

df["year"]    = df["year"].astype(int)
df["month"]   = df["month"].astype(int)
df["account"] = df["account"].str.removeprefix("Expenses/")

# Top 10 categories by total spend across the period
top10 = (
    df.groupby("account")["gbp_value"]
    .sum()
    .sort_values(ascending=False)
    .head(10)
    .index.tolist()
)

df["category"] = df["account"].where(df["account"].isin(top10), "Other")

pivot = (
    df.groupby(["year", "month", "category"])["gbp_value"]
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


# ── Chart components ──────────────────────────────────────────────────────────

def render_monthly_bar_chart(data: pd.DataFrame, col_order: list[str]):
    bar_select = alt.selection_point(fields=["month", "category"], name="bar_select")
    bars = (
        alt.Chart(data)
        .mark_bar()
        .encode(
            x=alt.X("month:O", sort=None, title=None),
            y=alt.Y("sum(amount):Q", title="Amount (£)"),
            color=alt.Color("category:N", sort=col_order, legend=alt.Legend(title=None)),
            order=alt.Order("order:Q"),
        )
        .add_params(bar_select)
        .configure(background="#1e293b")
        .configure_view(stroke=None)
    )
    st.subheader("Monthly expenses — last 12 months")
    return st.altair_chart(bars, on_select="rerun", use_container_width=True)


def render_category_table(sel_df: pd.DataFrame, month_label: str):
    st.subheader(f"Categories — {month_label}")
    by_cat = (
        sel_df.groupby("account")["gbp_value"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
        .rename(columns={"account": "Category", "gbp_value": "Total (£)"})
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
    return table_event, by_cat


def render_transactions(sel_df: pd.DataFrame, active_cat: str | None):
    if active_cat:
        st.subheader(f"Transactions — {active_cat}")
        tx = (
            sel_df[sel_df["account"] == active_cat]
            [["date", "description", "gbp_value"]]
            .sort_values("gbp_value", ascending=False)
            .reset_index(drop=True)
            .rename(columns={"date": "Date", "description": "Description", "gbp_value": "Amount (£)"})
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


def render_insight_row(
    title_12m: str,
    title_3m: str,
    data_12m: pd.DataFrame,
    data_3m: pd.DataFrame,
    table_config: dict,
):
    cols = st.columns(2)
    cols[0].subheader(title_12m)
    cols[1].subheader(title_3m)

    cols = st.columns(4)
    cols[0].altair_chart(make_pie(data_12m), use_container_width=True)
    cols[1].dataframe(data_12m, hide_index=True, use_container_width=True, column_config=table_config)
    cols[2].altair_chart(make_pie(data_3m),  use_container_width=True)
    cols[3].dataframe(data_3m,  hide_index=True, use_container_width=True, column_config=table_config)


# ── Main layout ───────────────────────────────────────────────────────────────

chart_event = render_monthly_bar_chart(pivot_long, ordered_cols)

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
    table_event, by_cat = render_category_table(sel_df, month_label)

with col_tx:
    table_sel = table_event.selection.rows
    if table_sel and table_sel[0] < len(by_cat) - 1:
        active_cat = by_cat.iloc[table_sel[0]]["Category"]
    elif chart_cat:
        active_cat = chart_cat
    else:
        active_cat = None

    render_transactions(sel_df, active_cat)


# ── Expense insights ──────────────────────────────────────────────────────────

"""
## Expense Insights
"""

def cat_summary(expense_df: pd.DataFrame, n_months: int) -> pd.DataFrame:
    by_cat = (
        expense_df.assign(account=expense_df["account"].str.removeprefix("Expenses/"))
        .groupby("account")["gbp_value"]
        .sum()
        .sort_values(ascending=False)
    )
    grand_total = by_cat.sum()
    top = by_cat.head(7).reset_index()
    top.columns = ["Category", "_total"]
    top["%"]           = (top["_total"] / grand_total * 100).round(1)
    top["Avg/month (£)"] = (top["_total"] / n_months).round(2)
    other_total = grand_total - top["_total"].sum()
    top = top[["Category", "Avg/month (£)", "%"]]
    if other_total > 0:
        top = pd.concat([
            top,
            pd.DataFrame([{
                "Category":      "Other",
                "Avg/month (£)": round(other_total / n_months, 2),
                "%":             round(other_total / grand_total * 100, 1),
            }]),
        ], ignore_index=True)
    return top


def make_pie(data: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(data)
        .mark_arc(innerRadius=40)
        .encode(
            theta=alt.Theta("Avg/month (£):Q"),
            color=alt.Color("Category:N", legend=None),
            tooltip=[
                alt.Tooltip("Category:N",       title="Category"),
                alt.Tooltip("Avg/month (£):Q",  title="Avg/month (£)", format=",.2f"),
                alt.Tooltip("%:Q",               title="%",             format=".1f"),
            ],
        )
        .properties(height=300, padding={"left": 5, "top": 25, "right": 5, "bottom": 5})
        .configure(background="#1e293b")
        .configure_view(stroke=None)
    )


pie_data_12m = cat_summary(df, 12)

n1_month = today.month - 1 or 12
n1_year  = today.year if today.month > 1 else today.year - 1

n2_month = today.month - 2
n2_year  = today.year

n3_month = n2_month - 1 or 12
n3_year  = n2_year if n2_month > 1 else n2_year - 1

exp_3m = df[
    ((df["year"] == n1_year)  & (df["month"] == n1_month)) |
    ((df["year"] == n2_year)  & (df["month"] == n2_month)) |
    ((df["year"] == n3_year)  & (df["month"] == n3_month))
]
pie_data_3m = cat_summary(exp_3m, 3)

table_config = {
    "Avg/month (£)": st.column_config.NumberColumn(format="£%,.2f"),
    "%":             st.column_config.NumberColumn(format="%.1f%%"),
}

EXCLUDED_CATS = {"Rent", "Team Jolene"}

def exclude(expense_df: pd.DataFrame) -> pd.DataFrame:
    return expense_df[
        ~expense_df["account"].str.removeprefix("Expenses/").str.split("/").str[0].isin(EXCLUDED_CATS)
    ]

pie_data_12m_excl = cat_summary(exclude(df), 12)
pie_data_3m_excl  = cat_summary(exclude(exp_3m), 3)

render_insight_row("Top expenses (12m)",           "Top expenses (3m)",           pie_data_12m,      pie_data_3m,      table_config)
render_insight_row("Discretionary expenses (12m)", "Discretionary expenses (3m)", pie_data_12m_excl, pie_data_3m_excl, table_config)
