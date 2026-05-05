#!/usr/bin/env python3
"""Fetch historical mid-market FX rates from Frankfurter (ECB data) and write to JSON.

Rates are forward-filled across weekends and public holidays so every
calendar day in the requested range has an entry.

Usage:
    python fetch_rates.py --quarter 2026-Q1
    python fetch_rates.py --date 2026-03-07
    python fetch_rates.py --quarter 2026-Q1 --base GBP --symbols EUR,SGD --output rates.json
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

import requests

sys.path.insert(0, os.path.dirname(__file__))
from export import parse_date_range


FRANKFURTER_URL = "https://api.frankfurter.dev/v2/rates"


def fetch_rates(start: date, end: date, base: str, symbols: list[str]) -> dict:
    params = {"from": start, "to": end, "base": base, "quotes": ",".join(symbols)}
    print(f"Fetching {FRANKFURTER_URL} {params} ...", file=sys.stderr)
    resp = requests.get(FRANKFURTER_URL, params=params)
    resp.raise_for_status()
    # v2 returns a flat list: [{date, base, quote, rate}, ...]
    # Reshape to {date: {symbol: rate}} to match forward_fill expectations
    rates: dict = {}
    for row in resp.json():
        rates.setdefault(row["date"], {})[row["quote"]] = row["rate"]
    return rates


def forward_fill(rates_by_date: dict, start: date, end: date) -> dict:
    """Extend sparse trading-day rates to every calendar day."""
    filled = {}
    last = None
    d = start
    while d <= end:
        key = d.isoformat()
        if key in rates_by_date:
            last = rates_by_date[key]
        if last is not None:
            filled[key] = last
        d += timedelta(days=1)
    return filled


def main():
    parser = argparse.ArgumentParser(description="Fetch historical FX rates from Frankfurter")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--quarter", metavar="YYYY-QN",    help="Quarter to fetch rates for (e.g. 2026-Q1)")
    group.add_argument("--date",    metavar="YYYY-MM-DD", help="Single day to fetch rates for (e.g. 2026-03-07)")
    parser.add_argument("--base",    default="GBP",        help="Base currency (default: GBP)")
    parser.add_argument("--symbols", default="EUR,SGD",    help="Comma-separated target currencies (default: EUR,SGD)")
    parser.add_argument("--output",  default="rates.json", metavar="FILE", help="Output JSON file (default: rates.json)")
    args = parser.parse_args()

    start_str, end_str = parse_date_range(args)
    start = date.fromisoformat(start_str)
    end   = date.fromisoformat(end_str) - timedelta(days=1)  # end from parse_date_range is exclusive
    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    rates = fetch_rates(start, end, args.base, symbols)
    filled = forward_fill(rates, start, end)

    output = {
        "base":    args.base,
        "symbols": symbols,
        "updated": date.today().isoformat(),
        "rates":   filled,
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(filled)} days of rates to {args.output}", file=sys.stderr)


main()
