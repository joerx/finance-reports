import sys
from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from data import load_data, load_balances, last_12_months

try:
    df       = load_data()
    balances = load_balances()
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

months = last_12_months()
month_labels = [date(y, m, 1).strftime("%Y-%m") for y, m in months]
month_index = pd.MultiIndex.from_tuples(months, names=["year", "month"])

df["year"]  = df["year"].astype(int)
df["month"] = df["month"].astype(int)

exp_df = df[df["account_type"] == "expenses"]
inc_df = df[df["account_type"] == "income"]

monthly_exp = (
    exp_df
    .groupby(["year", "month"])["gbp_value"]
    .sum()
    .reindex(month_index, fill_value=0)
)


def monthly_income(income_df: pd.DataFrame) -> pd.Series:
    return (
        -income_df
        .groupby(["year", "month"])["gbp_value"]
        .sum()
        .reindex(month_index, fill_value=0)
    )


def income_expense_chart(inc: pd.Series, exp: pd.Series) -> alt.LayerChart:
    summary = pd.DataFrame({
        "month":    month_labels,
        "income":   inc.values,
        "expenses": exp.values,
        "pnl":      inc.values - exp.values,
    })

    bars = (
        alt.Chart(summary)
        .mark_bar(opacity=0.6)
        .encode(
            x=alt.X("month:O", sort=None, title=None),
            y=alt.Y("pnl:Q", title="Amount (£)"),
            color=alt.condition(
                alt.datum.pnl >= 0,
                alt.value("#4ade80"),
                alt.value("#f87171"),
            ),
            tooltip=[
                alt.Tooltip("month:O", title="Month"),
                alt.Tooltip("pnl:Q",   title="PnL (£)", format=",.2f"),
            ],
        )
    )

    lines_df = summary.melt(
        id_vars="month",
        value_vars=["income", "expenses"],
        var_name="series",
        value_name="amount",
    )

    lines = (
        alt.Chart(lines_df)
        .mark_line(strokeWidth=2, point=True)
        .encode(
            x=alt.X("month:O", sort=None, title=None),
            y=alt.Y("amount:Q"),
            color=alt.Color(
                "series:N",
                scale=alt.Scale(
                    domain=["income", "expenses"],
                    range=["#60a5fa", "#fb923c"],
                ),
                legend=alt.Legend(title=None, orient="top-left"),
            ),
            tooltip=[
                alt.Tooltip("month:O",  title="Month"),
                alt.Tooltip("series:N", title="Series"),
                alt.Tooltip("amount:Q", title="Amount (£)", format=",.2f"),
            ],
        )
    )

    return (
        alt.layer(bars, lines)
        .configure(background="#1e293b")
        .configure_view(stroke=None)
    )


# ── Key metrics ───────────────────────────────────────────────────────────────

def _balance(account_type: str, negate: bool = False) -> float:
    row = balances[balances["account_type"] == account_type]["gbp_value"]
    val = float(row.iloc[0]) if not row.empty else 0.0
    return -val if negate else val

assets      = _balance("assets")
liabilities = _balance("liabilities", negate=True)
net_worth   = assets - liabilities
total_inc   = monthly_income(inc_df).sum()
total_exp   = monthly_exp.sum()
pnl         = total_inc - total_exp

today = date.today()

n1_month = today.month - 1 or 12
n1_year  = today.year if today.month > 1 else today.year - 1
n1_label = date(n1_year, n1_month, 1).strftime("%b %Y")
n1_df    = df[(df["year"] == n1_year) & (df["month"] == n1_month)]
n1_inc   = -n1_df[n1_df["account_type"] == "income"]["gbp_value"].sum()
n1_exp   =  n1_df[n1_df["account_type"] == "expenses"]["gbp_value"].sum()
n1_pnl   = n1_inc - n1_exp

n2_month = today.month - 2
n2_year  = today.year
if n2_month <= 0:
    n2_month += 12
    n2_year  -= 1
n2_df    = df[(df["year"] == n2_year) & (df["month"] == n2_month)]
n2_inc   = -n2_df[n2_df["account_type"] == "income"]["gbp_value"].sum()
n2_exp   =  n2_df[n2_df["account_type"] == "expenses"]["gbp_value"].sum()
n2_pnl   = n2_inc - n2_exp


with st.container(horizontal=True, gap="medium"):
    st.metric("Income (12m)", total_inc, format="£%,.2f", width=190)
    st.metric("Expenses (12m)", total_exp, format="£%,.2f", width=190)
    st.metric("PnL (12m)",      pnl,       format="£%,.2f", width=190)
    st.metric("Net worth",      net_worth, format="£%,.2f", width=190)
    st.metric("Assets",         assets,    format="£%,.2f", width=190)
    st.metric("Liabilities",    liabilities, format="£%,.2f", width=190)

with st.container(horizontal=True, gap="medium"):
    st.metric(f"Income ({n1_label})",   n1_inc, format="£%,.2f", width=190,
              delta=round(n1_inc - n2_inc, 2), delta_color="normal")
    st.metric(f"Expenses ({n1_label})", n1_exp, format="£%,.2f", width=190,
              delta=round(n1_exp - n2_exp, 2), delta_color="inverse")
    st.metric(f"PnL ({n1_label})",      n1_pnl, format="£%,.2f", width=190,
              delta=round(n1_pnl - n2_pnl, 2), delta_color="normal")

st.space(size="small")

# ── Charts ────────────────────────────────────────────────────────────────────

cols = st.columns(2)

cols[0].subheader("Cashflow (12 months)")
cols[0].caption("Bars show net PnL (green = surplus, red = deficit). Lines show total income and expenses.")

cols[0].altair_chart(
    income_expense_chart(monthly_income(inc_df), monthly_exp), 
    use_container_width=True,
    height=330
)

cols[1].subheader("Cashflow excl. ESOP")
cols[1].caption("Same view with ESOP excluded from income, showing underlying cash flow position.")

cols[1].altair_chart(
    income_expense_chart(monthly_income(inc_df[~inc_df["account"].str.contains("ESOP")]), monthly_exp),
    use_container_width=True,
    height=330
)

st.space(size="small")

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


pie_data_12m = cat_summary(exp_df, 12)

n3_month = n2_month - 1 or 12
n3_year  = n2_year if n2_month > 1 else n2_year - 1
exp_3m   = exp_df[
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

pie_data_12m_excl = cat_summary(exclude(exp_df), 12)
pie_data_3m_excl  = cat_summary(exclude(exp_3m),  3)

ins = st.columns(2)
ins[0].subheader("Top expenses (12m)")
ins[1].subheader("Top expenses (3m)")

ins = st.columns(4)
ins[0].altair_chart(make_pie(pie_data_12m), use_container_width=True)
ins[1].dataframe(pie_data_12m, hide_index=True, use_container_width=True, column_config=table_config)
ins[2].altair_chart(make_pie(pie_data_3m),  use_container_width=True)
ins[3].dataframe(pie_data_3m,  hide_index=True, use_container_width=True, column_config=table_config)

ins = st.columns(2)
ins[0].subheader("Discretionary expenses (12m)")
ins[1].subheader("Discretionary expenses (3m)")

ins = st.columns(4)
ins[0].altair_chart(make_pie(pie_data_12m_excl), use_container_width=True)
ins[1].dataframe(pie_data_12m_excl, hide_index=True, use_container_width=True, column_config=table_config)
ins[2].altair_chart(make_pie(pie_data_3m_excl),  use_container_width=True)
ins[3].dataframe(pie_data_3m_excl,  hide_index=True, use_container_width=True, column_config=table_config)
