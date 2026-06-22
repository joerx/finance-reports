import os
from datetime import date

import duckdb
import pandas as pd
import streamlit as st

BUCKET   = os.environ["S3_BUCKET"]
ENDPOINT = os.environ["S3_ENDPOINT"]
REGION   = os.environ.get("S3_REGION", "eu-central-1")


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


def last_12_months() -> list[tuple[int, int]]:
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


@st.cache_data(show_spinner="Loading balances ...")
def load_balances(exclude_pattern: str = "") -> pd.DataFrame:
    """Sum gbp_value across all available history for assets and liabilities.

    exclude_pattern: if set, any transaction where at least one split's account
    matches this regex is dropped entirely (both legs) before summing.
    """
    glob = f"s3://{BUCKET}/gnucash/**/*.parquet"
    con = _make_connection()
    excl = (
        f" AND tx_guid NOT IN ("
        f"SELECT DISTINCT tx_guid FROM read_parquet('{glob}', hive_partitioning = true)"
        f" WHERE regexp_matches(account, '{exclude_pattern}'))"
        if exclude_pattern else ""
    )
    return con.sql(f"""
        SELECT account_type, SUM(gbp_value) AS gbp_value
        FROM read_parquet('{glob}', hive_partitioning = true)
        WHERE account_type IN ('assets', 'liabilities'){excl}
        GROUP BY account_type
    """).df()


@st.cache_data(show_spinner="Loading currency exposure ...")
def load_currency_exposure() -> pd.DataFrame:
    """Net exposure per currency across all asset and liability accounts."""
    glob = f"s3://{BUCKET}/gnucash/**/*.parquet"
    con = _make_connection()
    return con.sql(f"""
        SELECT
            currency,
            SUM(CASE WHEN account_type = 'assets'      THEN amount    ELSE 0 END) AS assets,
            SUM(CASE WHEN account_type = 'liabilities' THEN amount    ELSE 0 END) AS liabilities,
            SUM(amount)                                                            AS net_amount,
            SUM(CASE WHEN account_type = 'assets'      THEN gbp_value ELSE 0 END) AS gbp_assets,
            SUM(gbp_value)                                                         AS gbp_amount
        FROM read_parquet('{glob}', hive_partitioning = true)
        WHERE account_type IN ('assets', 'liabilities')
        GROUP BY currency
        ORDER BY gbp_amount DESC
    """).df()


@st.cache_data(show_spinner="Loading data ...")
def load_data() -> pd.DataFrame:
    months = last_12_months()
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
