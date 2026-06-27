#!/usr/bin/env python3
"""Export Splitwise data into the JSON shape used by the dashboard.

Set SPLITWISE_ACCESS_TOKEN before running:
  SPLITWISE_ACCESS_TOKEN=... python connector/splitwise_export.py > splitwise-export.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://secure.splitwise.com/api/v3.0"


def api_get(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        f"{API_BASE}{path}{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "Naziyah Splitwise Reports"
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def as_decimal(value: str | int | float | None) -> Decimal:
    return Decimal(str(value or "0"))


def person_name(user: dict[str, Any]) -> str:
    first = user.get("first_name") or ""
    last = user.get("last_name") or ""
    full_name = f"{first} {last}".strip()
    return full_name or user.get("email") or f"User {user.get('id', '')}".strip()


def expense_paid_by(expense: dict[str, Any]) -> str:
    for user in expense.get("users", []):
        if as_decimal(user.get("paid_share")) > 0:
            return person_name(user.get("user", {}))
    return "Unknown"


def summarize_expense(expense: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": expense.get("id"),
        "description": expense.get("description") or "Untitled expense",
        "date": expense.get("date") or expense.get("created_at"),
        "category": (expense.get("category") or {}).get("name") or "Uncategorized",
        "group_name": (expense.get("group") or {}).get("name") or "Ungrouped",
        "paid_by": expense_paid_by(expense),
        "cost": {
            "currency_code": expense.get("currency_code") or "USD",
            "amount": expense.get("cost") or "0"
        },
        "shares": [
            {
                "name": person_name(user.get("user", {})),
                "paid_share": user.get("paid_share") or "0",
                "owed_share": user.get("owed_share") or "0",
                "net_balance": str(
                    as_decimal(user.get("paid_share")) - as_decimal(user.get("owed_share"))
                )
            }
            for user in expense.get("users", [])
        ]
    }


def summarize_balances(current_user: dict[str, Any], friends: list[dict[str, Any]]) -> list[dict[str, Any]]:
    owner = person_name(current_user)
    balances: list[dict[str, Any]] = []
    for friend in friends:
        friend_name = person_name(friend)
        for balance in friend.get("balance", []):
            amount = as_decimal(balance.get("amount"))
            currency = balance.get("currency_code") or "USD"
            if amount < 0:
                balances.append({
                    "from": owner,
                    "to": friend_name,
                    "amount": float(abs(amount)),
                    "currency": currency
                })
            elif amount > 0:
                balances.append({
                    "from": friend_name,
                    "to": owner,
                    "amount": float(amount),
                    "currency": currency
                })
    return balances


def main() -> int:
    token = os.environ.get("SPLITWISE_ACCESS_TOKEN")
    if not token:
        print("SPLITWISE_ACCESS_TOKEN is required.", file=sys.stderr)
        return 2

    current_user = api_get("/get_current_user", token)["user"]
    friends = api_get("/get_friends", token).get("friends", [])
    expenses = api_get("/get_expenses", token, {"limit": 100}).get("expenses", [])

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "owner_name": person_name(current_user),
        "balances": summarize_balances(current_user, friends),
        "expenses": [summarize_expense(expense) for expense in expenses],
    }

    json.dump(payload, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
