import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from data import load_currency_exposure

try:
    df = load_currency_exposure()
except Exception as e:
    st.error(f"Could not load data: {e}")
    st.stop()

total = df["gbp_amount"].sum()
df["pct"] = (df["gbp_amount"] / total * 100).round(2)

# ── Metrics ───────────────────────────────────────────────────────────────────

st.subheader("Currency Exposure")
st.caption("Net asset/liability balance per currency, expressed in GBP equivalent.")

with st.container(horizontal=True, gap="medium"):
    for _, row in df.iterrows():
        st.metric(
            label=row["currency"],
            value=f"£{row['gbp_amount']:,.0f}",
            help=f"{row['pct']:.1f}% of net worth",
            width=190,
        )

st.space(size="small")

# ── Donut charts ──────────────────────────────────────────────────────────────

COLORS = ["#60a5fa", "#34d399", "#fb923c", "#c084fc", "#f472b6"]
currencies = df["currency"].tolist()
color_scale = alt.Scale(domain=currencies, range=COLORS[: len(currencies)])

total_assets = df["gbp_assets"].sum()
df["pct_assets"] = (df["gbp_assets"] / total_assets * 100).round(2)
df["label_net"]    = df["gbp_amount"].apply(lambda x: f"£{x:,.0f}")
df["label_assets"] = df["gbp_assets"].apply(lambda x: f"£{x:,.0f}")


def donut(source: pd.DataFrame, theta_field: str, label_field: str, pct_field: str, pct_title: str) -> alt.Chart:
    base = alt.Chart(source).encode(
        theta=alt.Theta(f"{theta_field}:Q", stack=True),
        color=alt.Color(
            "currency:N",
            scale=color_scale,
            legend=alt.Legend(title=None, orient="right"),
        ),
    )
    arc = base.mark_arc(innerRadius=80, outerRadius=180).encode(
        tooltip=[
            alt.Tooltip("currency:N",          title="Currency"),
            alt.Tooltip(f"{theta_field}:Q",    title="GBP Amount", format=",.0f"),
            alt.Tooltip(f"{pct_field}:Q",      title=pct_title,    format=".2f"),
        ],
    )
    text = base.mark_text(radius=130, size=13, fontWeight="bold").encode(
        text=alt.Text(f"{label_field}:N"),
    )
    return (
        alt.layer(arc, text)
        .properties(height=400)
        .configure(background="#1e293b")
        .configure_view(stroke=None)
    )


col1, col2 = st.columns(2)

col1.subheader("Net Worth by Currency")
col1.altair_chart(
    donut(df, "gbp_amount", "label_net", "pct", "% of Net Worth"),
    use_container_width=True,
)

col2.subheader("Assets by Currency")
col2.altair_chart(
    donut(df, "gbp_assets", "label_assets", "pct_assets", "% of Assets"),
    use_container_width=True,
)

st.space(size="small")

# ── Summary table ─────────────────────────────────────────────────────────────

table = df[["currency", "assets", "liabilities", "net_amount", "gbp_amount", "pct"]].copy()
# liabilities are stored as negative in double-entry; negate for display
table["liabilities"] = -table["liabilities"]
table.columns = ["Currency", "Assets", "Liabilities", "Net (native)", "GBP Amount (£)", "% of Net Worth"]

st.dataframe(
    table,
    hide_index=True,
    column_config={
        "Assets":          st.column_config.NumberColumn(format="%,.2f"),
        "Liabilities":     st.column_config.NumberColumn(format="%,.2f"),
        "Net (native)":    st.column_config.NumberColumn(format="%,.2f"),
        "GBP Amount (£)":  st.column_config.NumberColumn(format="£%,.2f"),
        "% of Net Worth":  st.column_config.NumberColumn(format="%.2f%%"),
    },
    use_container_width=True,
)
