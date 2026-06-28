#!/usr/bin/env python3
"""SQLite-backed Splitwise sync and report queries.

Commands:
  init-full    Fetch current Splitwise state into SQLite.
  sync         Check notifications and update only changed expenses.
  export       Render dashboard JSON from SQLite.
  summary      Print a compact Hermes-friendly settlement summary.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from splitwise_export import (
    api_get,
    build_payload,
    fetch_expenses,
    person_name,
    summarize_balances,
    summarize_expense,
)

DEFAULT_DB_PATH = Path(os.environ.get("SPLITWISE_DB_PATH", "/root/.hermes/splitwise/splitwise.db"))
EXPENSE_ACTIVITY_TYPES = {0, 1, 2, 11, 13, 14, 15}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS expenses (
          id INTEGER PRIMARY KEY,
          description TEXT NOT NULL,
          date TEXT,
          updated_at TEXT,
          deleted_at TEXT,
          currency_code TEXT NOT NULL,
          amount TEXT NOT NULL,
          paid_by TEXT NOT NULL,
          category TEXT NOT NULL,
          group_name TEXT NOT NULL,
          raw_json TEXT NOT NULL,
          summary_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS balances (
          payer TEXT NOT NULL,
          payee TEXT NOT NULL,
          amount REAL NOT NULL,
          currency TEXT NOT NULL,
          expense_trail_json TEXT NOT NULL DEFAULT '[]',
          PRIMARY KEY (payer, payee, currency)
        );

        CREATE TABLE IF NOT EXISTS notifications (
          id INTEGER PRIMARY KEY,
          type INTEGER,
          created_at TEXT,
          source_type TEXT,
          source_id INTEGER,
          raw_json TEXT NOT NULL
        );
        """
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM metadata WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO metadata (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def require_token() -> str:
    token = os.environ.get("SPLITWISE_ACCESS_TOKEN")
    if not token:
        raise SystemExit("SPLITWISE_ACCESS_TOKEN is required.")
    return token


def upsert_expense(conn: sqlite3.Connection, expense: dict[str, Any]) -> None:
    summary = summarize_expense(expense)
    conn.execute(
        """
        INSERT INTO expenses (
          id, description, date, updated_at, deleted_at, currency_code, amount,
          paid_by, category, group_name, raw_json, summary_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          description = excluded.description,
          date = excluded.date,
          updated_at = excluded.updated_at,
          deleted_at = excluded.deleted_at,
          currency_code = excluded.currency_code,
          amount = excluded.amount,
          paid_by = excluded.paid_by,
          category = excluded.category,
          group_name = excluded.group_name,
          raw_json = excluded.raw_json,
          summary_json = excluded.summary_json
        """,
        (
            expense.get("id"),
            summary["description"],
            summary["date"],
            expense.get("updated_at"),
            expense.get("deleted_at"),
            summary["cost"]["currency_code"],
            summary["cost"]["amount"],
            summary["paid_by"],
            summary["category"],
            summary["group_name"],
            json.dumps(expense, separators=(",", ":")),
            json.dumps(summary, separators=(",", ":")),
        ),
    )


def upsert_summary(conn: sqlite3.Connection, summary: dict[str, Any], raw: dict[str, Any] | None = None) -> None:
    raw_expense = raw or {
        "id": summary.get("id"),
        "description": summary.get("description"),
        "date": summary.get("date"),
        "updated_at": summary.get("date"),
        "deleted_at": None,
        "currency_code": (summary.get("cost") or {}).get("currency_code"),
        "cost": (summary.get("cost") or {}).get("amount"),
        "category": {"name": summary.get("category")},
        "group": {"name": summary.get("group_name")},
        "users": [
            {
                "user": {"first_name": share.get("name")},
                "paid_share": share.get("paid_share"),
                "owed_share": share.get("owed_share"),
            }
            for share in summary.get("shares", [])
        ],
    }
    conn.execute(
        """
        INSERT INTO expenses (
          id, description, date, updated_at, deleted_at, currency_code, amount,
          paid_by, category, group_name, raw_json, summary_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          description = excluded.description,
          date = excluded.date,
          updated_at = excluded.updated_at,
          deleted_at = excluded.deleted_at,
          currency_code = excluded.currency_code,
          amount = excluded.amount,
          paid_by = excluded.paid_by,
          category = excluded.category,
          group_name = excluded.group_name,
          raw_json = excluded.raw_json,
          summary_json = excluded.summary_json
        """,
        (
            summary.get("id"),
            summary.get("description") or "Untitled expense",
            summary.get("date"),
            raw_expense.get("updated_at") or summary.get("date"),
            raw_expense.get("deleted_at"),
            (summary.get("cost") or {}).get("currency_code") or "USD",
            (summary.get("cost") or {}).get("amount") or "0",
            summary.get("paid_by") or "Unknown",
            summary.get("category") or "Uncategorized",
            summary.get("group_name") or "Ungrouped",
            json.dumps(raw_expense, separators=(",", ":")),
            json.dumps(summary, separators=(",", ":")),
        ),
    )


def upsert_notification(conn: sqlite3.Connection, notification: dict[str, Any]) -> None:
    source = notification.get("source") or {}
    conn.execute(
        """
        INSERT INTO notifications (id, type, created_at, source_type, source_id, raw_json)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          type = excluded.type,
          created_at = excluded.created_at,
          source_type = excluded.source_type,
          source_id = excluded.source_id,
          raw_json = excluded.raw_json
        """,
        (
            notification.get("id"),
            notification.get("type"),
            notification.get("created_at"),
            source.get("type"),
            source.get("id"),
            json.dumps(notification, separators=(",", ":")),
        ),
    )


def load_current_user(conn: sqlite3.Connection, token: str) -> dict[str, Any]:
    raw = get_meta(conn, "current_user_json")
    if raw:
        return json.loads(raw)
    current_user = api_get("/get_current_user", token)["user"]
    set_meta(conn, "current_user_json", json.dumps(current_user, separators=(",", ":")))
    set_meta(conn, "owner_name", person_name(current_user))
    return current_user


def load_expense_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT raw_json FROM expenses WHERE deleted_at IS NULL ORDER BY COALESCE(date, updated_at, '') DESC"
    ).fetchall()
    return [json.loads(row["raw_json"]) for row in rows]


def load_expense_summaries(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT summary_json FROM expenses WHERE deleted_at IS NULL ORDER BY COALESCE(date, updated_at, '') DESC"
    ).fetchall()
    return [json.loads(row["summary_json"]) for row in rows]


def trails_from_summaries(owner: str, summaries: list[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    trails: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for summary in summaries:
        currency = (summary.get("cost") or {}).get("currency_code") or "USD"
        owner_share = next((share for share in summary.get("shares", []) if share.get("name") == owner), None)
        if not owner_share:
            continue
        owner_net = Decimal(str(owner_share.get("net_balance") or "0"))

        for share in summary.get("shares", []):
            name = share.get("name")
            if not name or name == owner:
                continue
            friend_net = Decimal(str(share.get("net_balance") or "0"))
            if owner_net < 0 and friend_net > 0:
                payer, payee = owner, name
                amount = min(abs(owner_net), friend_net)
            elif owner_net > 0 and friend_net < 0:
                payer, payee = name, owner
                amount = min(owner_net, abs(friend_net))
            else:
                continue

            trails.setdefault((payer, payee, currency), []).append({
                "expense_id": summary.get("id"),
                "description": summary.get("description") or "Untitled expense",
                "date": summary.get("date"),
                "category": summary.get("category") or "Uncategorized",
                "group_name": summary.get("group_name") or "Ungrouped",
                "paid_by": summary.get("paid_by") or "Unknown",
                "amount": float(amount),
                "currency": currency,
                "owner_paid_share": owner_share.get("paid_share") or "0",
                "owner_owed_share": owner_share.get("owed_share") or "0",
                "friend_name": name,
                "friend_paid_share": share.get("paid_share") or "0",
                "friend_owed_share": share.get("owed_share") or "0",
            })

    for trail in trails.values():
        trail.sort(key=lambda item: item.get("date") or "", reverse=True)
    return trails


def refresh_balances(conn: sqlite3.Connection, token: str) -> None:
    current_user = load_current_user(conn, token)
    friends = api_get("/get_friends", token).get("friends", [])
    summaries = load_expense_summaries(conn)
    trails = trails_from_summaries(person_name(current_user), summaries)
    balances = summarize_balances(current_user, friends)

    conn.execute("DELETE FROM balances")
    for balance in balances:
        trail = trails.get((balance["from"], balance["to"], balance["currency"]), [])
        conn.execute(
            """
            INSERT INTO balances (payer, payee, amount, currency, expense_trail_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                balance["from"],
                balance["to"],
                balance["amount"],
                balance["currency"],
                json.dumps(trail, separators=(",", ":")),
            ),
        )


def init_full(conn: sqlite3.Connection, token: str) -> dict[str, Any]:
    payload = build_payload(token)
    set_meta(conn, "current_user_json", json.dumps(api_get("/get_current_user", token)["user"], separators=(",", ":")))
    set_meta(conn, "owner_name", payload["owner_name"])
    set_meta(conn, "exported_at", payload["exported_at"])
    set_meta(conn, "last_checked_at", payload["exported_at"])
    set_meta(conn, "refresh_reason", "initial_full_import")

    for expense in fetch_expenses(token):
        upsert_expense(conn, expense)

    refresh_balances(conn, token)
    return render_report(conn)


def import_report(conn: sqlite3.Connection, report: dict[str, Any]) -> dict[str, Any]:
    set_meta(conn, "owner_name", report.get("owner_name") or "Owner")
    set_meta(conn, "exported_at", report.get("exported_at") or utc_now())
    set_meta(conn, "last_checked_at", report.get("checked_at") or report.get("exported_at") or utc_now())
    set_meta(conn, "refresh_reason", report.get("refresh_reason") or "imported_report")
    set_meta(conn, "notification_count", str(report.get("notification_count") or 0))

    conn.execute("DELETE FROM balances")
    for balance in report.get("balances", []):
        conn.execute(
            """
            INSERT INTO balances (payer, payee, amount, currency, expense_trail_json)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(payer, payee, currency) DO UPDATE SET
              amount = excluded.amount,
              expense_trail_json = excluded.expense_trail_json
            """,
            (
                balance.get("from"),
                balance.get("to"),
                balance.get("amount") or 0,
                balance.get("currency") or "USD",
                json.dumps(balance.get("expense_trail") or [], separators=(",", ":")),
            ),
        )

    for summary in report.get("expenses", []):
        upsert_summary(conn, summary)

    return render_report(conn)


def fetch_json(url: str) -> dict[str, Any] | None:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return None


def notification_is_expense_activity(notification: dict[str, Any]) -> bool:
    source = notification.get("source") or {}
    return source.get("type") == "Expense" or notification.get("type") in EXPENSE_ACTIVITY_TYPES


def fetch_changed_expenses(token: str, notifications: list[dict[str, Any]], updated_after: str) -> list[dict[str, Any]]:
    expense_ids = {
        int((notification.get("source") or {}).get("id"))
        for notification in notifications
        if (notification.get("source") or {}).get("type") == "Expense"
        and (notification.get("source") or {}).get("id") is not None
    }
    expenses: list[dict[str, Any]] = []

    for expense_id in sorted(expense_ids):
        try:
            expenses.append(api_get(f"/get_expense/{expense_id}", token)["expense"])
        except Exception:
            pass

    if not expenses and any(notification_is_expense_activity(item) for item in notifications):
        expenses.extend(
            api_get(
                "/get_expenses",
                token,
                {
                    "updated_after": updated_after,
                    "limit": 100,
                    "offset": 0,
                },
            ).get("expenses", [])
        )

    return expenses


def sync_incremental(conn: sqlite3.Connection, token: str) -> dict[str, Any]:
    previous_export = get_meta(conn, "exported_at")
    if not previous_export:
        return init_full(conn, token)

    notifications = api_get(
        "/get_notifications",
        token,
        {
            "updated_after": previous_export,
            "limit": 20,
        },
    ).get("notifications", [])

    for notification in notifications:
        upsert_notification(conn, notification)

    changed = [item for item in notifications if notification_is_expense_activity(item)]
    if changed:
        for expense in fetch_changed_expenses(token, changed, previous_export):
            upsert_expense(conn, expense)
        refresh_balances(conn, token)
        set_meta(conn, "exported_at", utc_now())
        set_meta(conn, "refresh_reason", "expense_activity")
    else:
        set_meta(conn, "refresh_reason", "no_expense_activity")

    set_meta(conn, "last_checked_at", utc_now())
    set_meta(conn, "notification_count", str(len(notifications)))
    return render_report(conn)


def render_report(conn: sqlite3.Connection) -> dict[str, Any]:
    balances = [
        {
            "from": row["payer"],
            "to": row["payee"],
            "amount": row["amount"],
            "currency": row["currency"],
            "expense_trail": json.loads(row["expense_trail_json"]),
        }
        for row in conn.execute("SELECT * FROM balances ORDER BY currency, amount DESC")
    ]
    expenses = [
        json.loads(row["summary_json"])
        for row in conn.execute(
            "SELECT summary_json FROM expenses WHERE deleted_at IS NULL ORDER BY COALESCE(date, updated_at, '') DESC"
        )
    ]
    return {
        "exported_at": get_meta(conn, "exported_at") or utc_now(),
        "checked_at": get_meta(conn, "last_checked_at") or utc_now(),
        "refresh_reason": get_meta(conn, "refresh_reason") or "db_export",
        "notification_count": int(get_meta(conn, "notification_count") or "0"),
        "owner_name": get_meta(conn, "owner_name") or "Owner",
        "balances": balances,
        "expenses": expenses,
    }


def print_summary(conn: sqlite3.Connection) -> None:
    report = render_report(conn)
    owner = report["owner_name"]
    print(f"Splitwise summary for {owner}")
    print(f"Last export: {report['exported_at']}")
    print(f"Last check: {report['checked_at']} ({report['refresh_reason']})")

    payables = [balance for balance in report["balances"] if balance["from"] == owner]
    receivables = [balance for balance in report["balances"] if balance["to"] == owner]
    if not payables:
        print("Nothing to pay right now.")
    else:
        print("To pay:")
        for balance in payables:
            reasons = ", ".join(item["description"] for item in balance.get("expense_trail", [])[:4])
            if not reasons:
                reasons = "older expenses or settlement history"
            print(f"- {balance['to']}: {balance['amount']:.2f} {balance['currency']} for {reasons}")

    if receivables:
        print("Owed to you:")
        for balance in receivables:
            print(f"- {balance['from']}: {balance['amount']:.2f} {balance['currency']}")


def write_json(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, indent=2) + "\n"
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQLite-backed Splitwise sync and queries.")
    parser.add_argument("command", choices=["init-full", "import-url", "sync", "export", "summary"])
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite DB path.")
    parser.add_argument("--output", help="Write JSON report to this path.")
    parser.add_argument("--url", help="Existing dashboard JSON URL for import-url.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db)
    with connect(db_path) as conn:
        init_schema(conn)
        if args.command == "init-full":
            payload = init_full(conn, require_token())
            write_json(payload, args.output)
        elif args.command == "sync":
            payload = sync_incremental(conn, require_token())
            write_json(payload, args.output)
        elif args.command == "import-url":
            if not args.url:
                raise SystemExit("--url is required for import-url.")
            report = fetch_json(args.url)
            if not report:
                raise SystemExit(f"Could not fetch report from {args.url}")
            write_json(import_report(conn, report), args.output)
        elif args.command == "export":
            write_json(render_report(conn), args.output)
        elif args.command == "summary":
            print_summary(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
