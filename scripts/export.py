import argparse
import sqlite3
import sys
import os
import pandas as pd
from datetime import date, timedelta

QUARTER_MONTHS = {1: 1, 2: 4, 3: 7, 4: 10}

def parse_quarter(quarter):
    try:
      year_str, q_str = quarter.split("-")
      year = int(year_str)
      q = int(q_str[1])
    except (ValueError, IndexError):
      raise ValueError(f"Invalid quarter format: '{quarter}'. Expected YYYY-QN (e.g. 2026-Q1)")
    start_month = QUARTER_MONTHS[q]
    end_q = q % 4 + 1
    end_year = year + 1 if q == 4 else year
    end_month = QUARTER_MONTHS[end_q]
    return date(year, start_month, 1).isoformat(), date(end_year, end_month, 1).isoformat()


def parse_date(date):
  try:
    d = date.fromisoformat(date)
  except ValueError:
    raise ValueError(f"Invalid date format: '{date}'. Expected YYYY-MM-DD (e.g. 2026-03-07)")
  return d.isoformat(), (d + timedelta(days=1)).isoformat()


def parse_date_range(args):
  """Return (start_date, end_date) as ISO strings from --quarter or --date args."""
  if args.date:
    return parse_date(args.date)
  if args.quarter:
    return parse_quarter(args.quarter)
  raise ValueError("Either --quarter or --date must be provided.")


def load_data(filename, start_date, end_date):
  conn = sqlite3.connect(filename)
  conn.row_factory = sqlite3.Row
  cur = conn.cursor()

  rows = cur.execute("""
    WITH RECURSIVE account_tree AS (
        -- Immediate children of ROOT become the top-level category (expenses, assets, etc.)
        SELECT
            a.guid,
            a.name        AS top_level,
            a.name        AS path,
            a.commodity_guid
        FROM accounts a
        JOIN accounts root ON a.parent_guid = root.guid
        WHERE root.account_type = 'ROOT'

        UNION ALL

        SELECT
            a.guid,
            at.top_level,
            at.path || '/' || a.name,
            a.commodity_guid
        FROM accounts a
        JOIN account_tree at ON a.parent_guid = at.guid
    )
    SELECT
        tx.guid                                                    AS tx_guid,
        tx.post_date                                               AS date,
        tx.description,
        at.path                                                    AS account,
        LOWER(at.top_level)                                        AS account_type,
        c.mnemonic                                                 AS currency,
        CAST(s.quantity_num AS REAL) / s.quantity_denom            AS amount
    FROM splits s
    JOIN transactions tx  ON s.tx_guid      = tx.guid
    JOIN account_tree at  ON s.account_guid = at.guid
    JOIN commodities c    ON c.guid         = at.commodity_guid
    WHERE tx.post_date >= :start_date
      AND tx.post_date <  :end_date
    ORDER BY tx.post_date
  """, {"start_date": start_date, "end_date": end_date}).fetchall()

  return pd.DataFrame(
      [dict(row) for row in rows],
      columns=["tx_guid", "date", "account", "account_type", "currency", "description", "amount"],
  )


def main(args):
  if not os.path.isfile(args.db):
    print(f"Error: Database file '{args.db}' does not exist.")
    sys.exit(1)

  output_path = args.output
  filename = args.db
  start_date, end_date = parse_date_range(args)

  df = load_data(filename, start_date, end_date)

  if output_path.endswith(".csv"):
    df.to_csv(output_path, index=False)
  else:
    df.to_parquet(output_path, index=False)
  
  print(f"Wrote {len(df)} rows to {output_path}")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(description="Export all GnuCash splits with account metadata to Parquet or CSV")
  parser.add_argument("--db", required=True, metavar="FILE", help="GnuCash SQLite database file (e.g. 2026.gnucash)")
  parser.add_argument("--output", required=True, metavar="FILE", help="Output Parquet file path (e.g. out.parquet)")
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument("--quarter", metavar="YYYY-QN", help="Quarter to export (e.g. 2026-Q1)")
  group.add_argument("--date", metavar="YYYY-MM-DD", help="Single day to export (e.g. 2026-03-07)")
  args = parser.parse_args()

  main(args)
