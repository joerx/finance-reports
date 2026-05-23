#!/usr/bin/env python3
"""Net worth report: summary, asset breakdown, and savings/investments detail."""
import argparse
import sqlite3
import sys


def fetch_by_root(cur, root_name: str) -> list[tuple[str, str, float]]:
    """
    Returns (top_level, full_path, balance) for every account with splits
    under root_name. top_level is the immediate child of root_name.
    """
    rows = cur.execute("""
        WITH RECURSIVE tree AS (
            SELECT a.guid, a.name AS top_level, a.name AS path
            FROM accounts a
            JOIN accounts root ON a.parent_guid = root.guid
            JOIN accounts rr   ON root.parent_guid = rr.guid
            WHERE rr.account_type = 'ROOT' AND root.name = ?

            UNION ALL

            SELECT a.guid, t.top_level, t.path || '/' || a.name
            FROM accounts a
            JOIN tree t ON a.parent_guid = t.guid
        )
        SELECT t.top_level, t.path,
               SUM(CAST(s.quantity_num AS REAL) / s.quantity_denom) AS balance
        FROM tree t
        JOIN splits s ON s.account_guid = t.guid
        GROUP BY t.guid, t.top_level, t.path
        HAVING balance != 0
    """, (root_name,)).fetchall()
    return rows


def md_table(headers: list[str], rows: list[tuple], right: set[int] | None = None) -> None:
    right = right or set()
    widths = [len(h) for h in headers]
    str_rows = []
    for row in rows:
        cells = [f"{v:,.2f}" if isinstance(v, float) else str(v) for v in row]
        str_rows.append(cells)
        for i, c in enumerate(cells):
            widths[i] = max(widths[i], len(c))

    def fmt(i: int, s: str) -> str:
        return f"{s:>{widths[i]}}" if i in right else f"{s:<{widths[i]}}"

    print("| " + " | ".join(fmt(i, h) for i, h in enumerate(headers)) + " |")
    sep = ["-" * (widths[i] - 1) + ":" if i in right else "-" * widths[i] for i in range(len(headers))]
    print("| " + " | ".join(sep) + " |")
    for cells in str_rows:
        print("| " + " | ".join(fmt(i, c) for i, c in enumerate(cells)) + " |")


def main():
    parser = argparse.ArgumentParser(description="Net worth report with asset and savings breakdown")
    parser.add_argument("--db", required=True, metavar="FILE", help="GnuCash SQLite database file")
    parser.add_argument("--savings", default="Savings & Investments",
                        metavar="ACCOUNTS",
                        help="Comma-separated top-level asset account names for the savings detail table "
                             "(default: Savings,Investments)")
    args = parser.parse_args()

    savings_filter = {s.strip() for s in args.savings.split(",") if s.strip()}

    con = sqlite3.connect(args.db)
    cur = con.cursor()
    asset_rows = fetch_by_root(cur, "Assets")
    liab_rows  = fetch_by_root(cur, "Liabilities")
    con.close()

    total_assets = sum(b for _, _, b in asset_rows)
    total_liab   = -sum(b for _, _, b in liab_rows)   # credit-normal → negate
    net_worth    = total_assets - total_liab

    # ── Table 1: Summary ─────────────────────────────────────────────────────────
    print("**Net Worth**\n")
    md_table(
        ["Metric", "Amount (£)"],
        [("Total assets", total_assets), ("Total liabilities", total_liab), ("Net worth", net_worth)],
        right={1},
    )

    # ── Table 2: Asset breakdown by top-level account ─────────────────────────────
    by_top: dict[str, float] = {}
    for tl, _, bal in asset_rows:
        by_top[tl] = by_top.get(tl, 0.0) + bal

    print("\n**Assets by Account**\n")
    md_table(
        ["Account", "Balance (£)"],
        sorted(by_top.items(), key=lambda x: x[1], reverse=True),
        right={1},
    )

    # ── Table 3: Savings & investments at leaf granularity ───────────────────────
    savings_rows = [
        (path, bal)
        for tl, path, bal in asset_rows
        if tl in savings_filter
    ]
    savings_rows.sort(key=lambda x: x[1], reverse=True)

    if not savings_rows:
        print(f"\n(no accounts found matching: {', '.join(sorted(savings_filter))})",
              file=sys.stderr)
        return

    print(f"\n**Savings & Investments**\n")
    md_table(
        ["Account", "Balance (£)"],
        savings_rows,
        right={1},
    )


main()
