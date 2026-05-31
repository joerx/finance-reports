import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from data import load_data

try:
    df = load_data()
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

df["year"]  = df["year"].astype(int)
df["month"] = df["month"].astype(int)
df["_date"] = pd.to_datetime(df["date"]).dt.date

today = date.today()

# Default start: first day of the month 3 months ago
_m = today.month - 3
default_start = date(today.year if _m > 0 else today.year - 1, _m if _m > 0 else _m + 12, 1)

data_min = df["_date"].min()
data_max = df["_date"].max()

# ── Toolbar ───────────────────────────────────────────────────────────────────

col_from, col_to, col_type, col_account = st.columns([1, 1, 1.5, 3])

with col_from:
    date_from = st.date_input("From", value=max(default_start, data_min), min_value=data_min, max_value=data_max)

with col_to:
    date_to = st.date_input("To", value=min(today, data_max), min_value=data_min, max_value=data_max)

with col_type:
    type_options = ["All"] + sorted(df["account_type"].unique().tolist())
    sel_type = st.selectbox("Account type", type_options)

with col_account:
    account_pool = df if sel_type == "All" else df[df["account_type"] == sel_type]
    account_options = ["All"] + sorted(account_pool["account"].unique().tolist())
    sel_account = st.selectbox("Account", account_options)

# ── Filter ────────────────────────────────────────────────────────────────────

mask = (df["_date"] >= date_from) & (df["_date"] <= date_to)
if sel_type != "All":
    mask &= df["account_type"] == sel_type
if sel_account != "All":
    mask &= df["account"] == sel_account

filtered = (
    df[mask]
    [["date", "account_type", "account", "description", "currency", "amount", "gbp_value"]]
    .sort_values("date", ascending=False)
    .reset_index(drop=True)
    .rename(columns={
        "date":         "Date",
        "account_type": "Type",
        "account":      "Account",
        "description":  "Description",
        "currency":     "CCY",
        "amount":       "Amount",
        "gbp_value":    "GBP",
    })
)

# ── Table ─────────────────────────────────────────────────────────────────────

st.caption(f"{len(filtered):,} transactions")

st.dataframe(
    filtered,
    use_container_width=True,
    hide_index=True,
    height=600,
    column_config={
        "Date":   st.column_config.DatetimeColumn("Date", format="YYYY-MM-DD"),
        "Amount": st.column_config.NumberColumn(format="%.4f"),
        "GBP":    st.column_config.NumberColumn(format="£%.2f"),
    },
)
