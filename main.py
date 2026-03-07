import sqlite3
import sys
import os
import pandas as pd
from datetime import date

QUARTER_MONTHS = {1: 1, 2: 4, 3: 7, 4: 10}

def parse_quarter(quarter_str):
  """Parse 'YYYY-QN' and return (start_date, end_date) as ISO strings."""
  try:
    year_str, q_str = quarter_str.split("-")
    year = int(year_str)
    q = int(q_str[1])
  except (ValueError, IndexError):
    raise ValueError(f"Invalid quarter format: '{quarter_str}'. Expected YYYY-QN (e.g. 2026-Q1)")

  start_month = QUARTER_MONTHS[q]
  end_q = q % 4 + 1
  end_year = year + 1 if q == 4 else year
  end_month = QUARTER_MONTHS[end_q]

  return (
    date(year, start_month, 1).isoformat(),
    date(end_year, end_month, 1).isoformat(),
  )

def main(filename, output_path, quarter):
  # To get all expenses, we are looking for all splits that are in any of the expense accounts.
  # We then need to join them with the transaction to get date and description.

  root_account_name = "Expenses"
  root_account_id = None

  start_date, end_date = parse_quarter(quarter)

  conn = sqlite3.connect(filename)
  conn.row_factory = sqlite3.Row

  cur = conn.cursor()

  res = cur.execute("SELECT guid FROM accounts WHERE name = :name", {"name": root_account_name})
  for row in res:
    root_account_id = row['guid']
    break

  if root_account_id is None:
    raise Exception(f"Error: Account '{root_account_name}' not found.")

  query = """
    WITH RECURSIVE account_tree AS (
        SELECT guid, name, parent_guid, 1 AS depth, name AS path
        FROM accounts
        WHERE guid = :root_account_id

        UNION ALL

        SELECT a.guid, a.name, a.parent_guid, at.depth + 1, at.path || "/" || a.name
        FROM accounts a
        INNER JOIN account_tree at ON a.parent_guid = at.guid
    )

    SELECT tx.guid, s.quantity_num, s.quantity_denom, tx.post_date, tx.description, at.path
    FROM splits s
    JOIN transactions tx on s.tx_guid = tx.guid
    JOIN account_tree at on s.account_guid = at.guid
    WHERE at.guid != :root_account_id
    AND tx.post_date >= :start_date
    AND tx.post_date < :end_date
    """

  data = {
    "root_account_id": root_account_id,
    "start_date": start_date,
    "end_date": end_date
  }

  rows = []
  res = cur.execute(query, data)
  for row in res:
    rows.append({
      "tx_guid": row["guid"],
      "date": row["post_date"],
      "description": row["description"],
      "account": row["path"],
      "amount": row["quantity_num"] / row["quantity_denom"]
    })

  df = pd.DataFrame(rows, columns=["tx_guid", "date", "account", "description", "amount"])
  df.to_parquet(output_path, index=False)
  print(f"Wrote {len(df)} rows to {output_path}")


if __name__ == "__main__":
  if len(sys.argv) != 4:
    print("Usage: main.py <dbname> <output.parquet> <quarter>")
    print("  e.g. main.py 2026.gnucash out.parquet 2026-Q1")
    sys.exit(1)

  filename = sys.argv[1]
  output_path = sys.argv[2]
  quarter = sys.argv[3]

  if not os.path.isfile(filename):
    print(f"Error: Database file '{filename}' does not exist.")
    sys.exit(1)

  main(filename, output_path, quarter)
