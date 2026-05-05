#!/usr/bin/env python3
"""Print income, expense and liability balances from a GnuCash SQLite database."""
import sqlite3
import sys
from collections import defaultdict


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


def fetch_balances(cur, account_type: str, cache: dict, negate: bool = False) -> list[tuple[str, str, float]]:
    rows = cur.execute("""
        SELECT a.guid, c.mnemonic, SUM(CAST(s.quantity_num AS REAL) / s.quantity_denom) AS balance
        FROM accounts a
        JOIN splits s ON s.account_guid = a.guid
        JOIN commodities c ON c.guid = a.commodity_guid
        WHERE a.account_type = ?
        GROUP BY a.guid, c.mnemonic
        ORDER BY balance DESC
    """, (account_type,)).fetchall()
    sign = -1 if negate else 1
    return [(full_name(cur, guid, cache), mnemonic, sign * balance) for guid, mnemonic, balance in rows]


def fetch_balances_by_root(cur, root_name: str, cache: dict, negate: bool = False) -> list[tuple[str, str, float]]:
    """Fetch balances for all accounts under a named top-level account, recursively."""
    rows = cur.execute("""
        WITH RECURSIVE subtree(guid) AS (
            SELECT a.guid
            FROM accounts a
            JOIN accounts p ON a.parent_guid = p.guid
            WHERE a.name = ? AND p.account_type = 'ROOT'
            UNION ALL
            SELECT a.guid
            FROM accounts a
            JOIN subtree s ON a.parent_guid = s.guid
        )
        SELECT a.guid, c.mnemonic, SUM(CAST(s.quantity_num AS REAL) / s.quantity_denom) AS balance
        FROM subtree st
        JOIN accounts a ON a.guid = st.guid
        JOIN splits s ON s.account_guid = a.guid
        JOIN commodities c ON c.guid = a.commodity_guid
        GROUP BY a.guid, c.mnemonic
        HAVING balance != 0
        ORDER BY balance DESC
    """, (root_name,)).fetchall()
    sign = -1 if negate else 1
    return [(full_name(cur, guid, cache), mnemonic, sign * balance) for guid, mnemonic, balance in rows]


def print_table(title: str, rows: list[tuple[str, str, float]], col: int) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for _, ccy, balance in rows:
        totals[ccy] += balance

    width = col + 20
    print(f"\n{title}")
    print(f"{'Account':<{col}}  {'CCY':3}  {'Balance':>12}")
    print("-" * width)
    for name, ccy, balance in rows:
        print(f"{name:<{col}}  {ccy:3}  {balance:>12.2f}")
    print("-" * width)
    for ccy, total in sorted(totals.items()):
        print(f"{'Total (' + ccy + ')':<{col}}  {ccy:3}  {total:>12.2f}")

    return dict(totals)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <db-file>", file=sys.stderr)
        sys.exit(1)

    con = sqlite3.connect(sys.argv[1])
    cur = con.cursor()
    cache = {}

    expenses    = fetch_balances(cur, "EXPENSE", cache)
    income      = fetch_balances(cur, "INCOME", cache, negate=True)
    liabilities = fetch_balances_by_root(cur, "Liabilities", cache, negate=True)
    assets      = fetch_balances_by_root(cur, "Assets", cache)

    col = max(len(name) for name, _, _ in expenses + income + liabilities + assets)

    exp_totals  = print_table("EXPENSES",    expenses,    col)
    inc_totals  = print_table("INCOME",      income,      col)
    liab_totals = print_table("LIABILITIES", liabilities, col)
    asset_totals = print_table("ASSETS",     assets,      col)

    all_ccys = sorted(set(inc_totals) | set(exp_totals) | set(liab_totals) | set(asset_totals))
    width = col + 20
    print(f"\n{'=' * width}")
    for ccy in all_ccys:
        inc  = inc_totals.get(ccy, 0)
        exp  = exp_totals.get(ccy, 0)
        pnl  = inc - exp
        print(f"  {ccy}  income {inc:>12.2f}  expenses {exp:>12.2f}  PnL {pnl:>12.2f}")
    print(f"{'─' * width}")
    for ccy in all_ccys:
        ast  = asset_totals.get(ccy, 0)
        liab = liab_totals.get(ccy, 0)
        nw   = ast - liab
        print(f"  {ccy}  assets {ast:>12.2f}  liabilities {liab:>12.2f}  net worth {nw:>12.2f}")
    print(f"{'=' * width}")

    con.close()


main()
