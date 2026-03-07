import argparse
import os
from datetime import date, timedelta

from export import load_data, parse_quarter


def main():
    parser = argparse.ArgumentParser(description="Batch export GnuCash expenses to date-partitioned Parquet files")
    parser.add_argument("--db", required=True, metavar="FILE", help="GnuCash SQLite database file")
    parser.add_argument("--quarter", required=True, metavar="YYYY-QN", help="Quarter to export (e.g. 2026-Q1)")
    parser.add_argument("--outdir", required=True, metavar="DIR", help="Output base directory")

    args = parser.parse_args()
    start_str, end_str = parse_quarter(args.quarter)
    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)

    d = start
    while d < end:
        next_d = d + timedelta(days=1)
        df = load_data(args.db, d.isoformat(), next_d.isoformat())

        if not df.empty:
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
