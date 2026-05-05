import argparse
import json
import os
import sys
from datetime import date, timedelta

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from export import load_data, parse_quarter
from fetch_rates import fetch_rates, forward_fill

BASE_CURRENCY = "GBP"


def load_rates(rates_file: str) -> dict:
    if not os.path.isfile(rates_file):
        print(f"Error: rates file not found: {rates_file}", file=sys.stderr)
        sys.exit(1)
    with open(rates_file) as f:
        return json.load(f)["rates"]


def apply_gbp_value(df: pd.DataFrame, rates: dict) -> pd.DataFrame:
    # rates are GBP-based: 1 GBP = X foreign; to convert foreign -> GBP divide by rate
    date_strs = df["date"].astype(str).str[:10]
    rate_values = [
        1.0 if ccy == BASE_CURRENCY else rates.get(d, {}).get(ccy)
        for d, ccy in zip(date_strs, df["currency"])
    ]
    rate_series = pd.Series(rate_values, index=df.index, dtype=float)
    unknown = rate_series.isna()
    if unknown.any():
        missing = df.loc[unknown, "currency"].unique().tolist()
        print(f"Warn: no rate found for {missing}, gbp_value will be NaN", file=sys.stderr)
    df["gbp_value"] = (df["amount"] / rate_series).round(4)
    return df


def main():
    parser = argparse.ArgumentParser(description="Batch export GnuCash splits to date-partitioned Parquet files")
    parser.add_argument("--db",      required=True, metavar="FILE",    help="GnuCash SQLite database file")
    parser.add_argument("--quarter", required=True, metavar="YYYY-QN", help="Quarter to export (e.g. 2026-Q1)")
    parser.add_argument("--outdir",  required=True, metavar="DIR",     help="Output base directory")
    parser.add_argument("--rates",   required=True, metavar="FILE",    help="Path to rates JSON file")

    args = parser.parse_args()
    rates = load_rates(args.rates)

    start_str, end_str = parse_quarter(args.quarter)
    start = date.fromisoformat(start_str)
    end   = date.fromisoformat(end_str)

    d = start
    while d < end:
        next_d = d + timedelta(days=1)
        df = load_data(args.db, d.isoformat(), next_d.isoformat())

        if not df.empty:
            df = apply_gbp_value(df, rates)
            out_path = os.path.join(
                args.outdir,
                f"year={d.year}",
                f"month={d.month:02d}",
                f"day={d.day:02d}",
                "transactions.parquet",
            )
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            df.to_parquet(out_path, index=False)
            print(f"{d}: wrote {len(df)} rows -> {out_path}")
        else:
            print(f"{d}: no transactions, skipping")

        d = next_d


if __name__ == "__main__":
    main()
