#!/usr/bin/env python3
"""Hermes-facing Splitwise query wrapper.

This script reads the local SQLite database only. It does not call Splitwise.
Use splitwise_db.py sync/init-full to update the DB.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from splitwise_db import DEFAULT_DB_PATH, connect, init_schema, print_summary, render_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read Splitwise state from the local SQLite DB.")
    parser.add_argument("command", choices=["summary", "report", "payables"])
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite DB path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    with connect(db_path) as conn:
        init_schema(conn)
        report = render_report(conn)
        if args.command == "summary":
            print_summary(conn)
        elif args.command == "report":
            print(json.dumps(report, indent=2))
        elif args.command == "payables":
            owner = report["owner_name"]
            payables = [balance for balance in report["balances"] if balance["from"] == owner]
            print(json.dumps(payables, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
