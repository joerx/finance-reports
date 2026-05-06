#!/usr/bin/env python3
"""Monthly expense report: top 12 categories for N-1 with AVG12 and N-2 comparison."""
import argparse
import sqlite3
import sys
from datetime import date


def prev_month(y: int, m: int, n: int = 1) -> tuple[int, int]:
    m -= n
    while m <= 0:
        m += 12
        y -= 1
    return y, m


def month_range(start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
    months, y, m = [], *start
    ey, em = end
    while (y, m) <= (ey, em):
        months.append((y, m))
        m = m % 12 + 1
        if m == 1:
            y += 1
    return months


def full_name(cur, guid: str, cache: dict) -> str:
    if guid in cache:
        return cache[guid]
    row = cur.execute(
        "SELECT name, parent_guid, account_type FROM accounts WHERE guid = ?", (guid,)
    ).fetchone()
    if not row:
        return ""
    name, parent_guid, actype = row
    if actype == "ROOT" or not parent_guid:
        cache[guid] = ""
        return ""
    parent = full_name(cur, parent_guid, cache)
    result = f"{parent}/{name}" if parent else name
    cache[guid] = result
    return result


def fetch_monthly(cur, start: tuple[int, int], end: tuple[int, int]) -> dict:
    sy, sm = start
    ey, em = end
    next_em = em % 12 + 1
    next_ey = ey + 1 if em == 12 else ey
    start_date = f"{sy}-{sm:02d}-01"
    end_date   = f"{next_ey}-{next_em:02d}-01"

    rows = cur.execute("""
        WITH RECURSIVE expense_tree AS (
            SELECT a.guid
            FROM accounts a
            JOIN accounts p ON a.parent_guid = p.guid
            WHERE p.account_type = 'ROOT' AND a.name = 'Expenses'
            UNION ALL
            SELECT a.guid
            FROM accounts a
            JOIN expense_tree et ON a.parent_guid = et.guid
        )
        SELECT
            s.account_guid,
            CAST(SUBSTR(tx.post_date, 1, 4) AS INTEGER) AS yr,
            CAST(SUBSTR(tx.post_date, 6, 2) AS INTEGER) AS mo,
            SUM(CAST(s.quantity_num AS REAL) / s.quantity_denom) AS amount
        FROM splits s
        JOIN transactions tx ON s.tx_guid = tx.guid
        JOIN expense_tree et ON s.account_guid = et.guid
        WHERE tx.post_date >= ? AND tx.post_date < ?
        GROUP BY s.account_guid, yr, mo
    """, (start_date, end_date)).fetchall()

    data: dict[str, dict[tuple, float]] = {}
    for guid, yr, mo, amount in rows:
        data.setdefault(guid, {})[(yr, mo)] = amount
    return data


def main():
    parser = argparse.ArgumentParser(description="Monthly expense report by category")
    parser.add_argument("--db", required=True, metavar="FILE", help="GnuCash SQLite database file")
    args = parser.parse_args()

    today    = date.today()
    n1       = prev_month(today.year, today.month, 1)
    n2       = prev_month(today.year, today.month, 2)
    avg_start = prev_month(*n1, 11)   # 12 months ending at N-1 inclusive

    all_months = month_range(avg_start, n1)   # exactly 12 months

    con = sqlite3.connect(args.db)
    cur = con.cursor()

    raw   = fetch_monthly(cur, avg_start, n1)
    cache = {}

    # Aggregate by display name (strip "Expenses/" prefix)
    by_name: dict[str, dict[tuple, float]] = {}
    for guid, months in raw.items():
        name = full_name(cur, guid, cache).removeprefix("Expenses/")
        for key, val in months.items():
            by_name.setdefault(name, {})
            by_name[name][key] = by_name[name].get(key, 0.0) + val

    con.close()

    # Compute metrics per category
    table = []
    for name, months in by_name.items():
        n1_val  = months.get(n1,  0.0)
        n2_val  = months.get(n2,  0.0)
        avg12   = sum(months.get(m, 0.0) for m in all_months) / 12
        table.append((name, avg12, n2_val, n1_val))

    # Top 12 by N-1, descending
    table.sort(key=lambda r: r[3], reverse=True)
    table = table[:12]

    n1_label = date(*n1, 1).strftime("%b %Y")
    n2_label = date(*n2, 1).strftime("%b %Y")

    cat_w = max(len(r[0]) for r in table)
    cat_w = max(cat_w, 8)

    header = (
        f"| {'Category':<{cat_w}} "
        f"| {n1_label:>10} "
        f"| {'AVG12':>10} "
        f"| {'Δ AVG12':>10} "
        f"| {n2_label:>10} "
        f"| {'Δ N-2':>10} |"
    )
    sep = (
        f"|{'-' * (cat_w + 2)}"
        + f"|{'-' * 11}:" * 5
        + "|"
    )

    print(f"## Expense Report — {n1_label}\n")
    print(header)
    print(sep)

    for name, avg12, n2_val, n1_val in table:
        d_avg  = n1_val - avg12
        d_prev = n1_val - n2_val
        print(
            f"| {name:<{cat_w}} "
            f"| {n1_val:>10.2f} "
            f"| {avg12:>10.2f} "
            f"| {d_avg:>+10.2f} "
            f"| {n2_val:>10.2f} "
            f"| {d_prev:>+10.2f} |"
        )


main()
