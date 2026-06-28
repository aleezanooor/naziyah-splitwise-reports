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
EXPENSE_PAGE_SIZE = 100


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


def fetch_expenses(token: str) -> list[dict[str, Any]]:
    max_expenses = int(os.environ.get("SPLITWISE_EXPENSE_LIMIT", "500"))
    expenses: list[dict[str, Any]] = []

    for offset in range(0, max_expenses, EXPENSE_PAGE_SIZE):
        page = api_get(
            "/get_expenses",
            token,
            {
                "limit": EXPENSE_PAGE_SIZE,
                "offset": offset,
            },
        ).get("expenses", [])
        expenses.extend(page)
        if len(page) < EXPENSE_PAGE_SIZE:
            break

    return expenses[:max_expenses]


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


def balance_trails(
    current_user: dict[str, Any],
    expenses: list[dict[str, Any]],
) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    owner = person_name(current_user)
    trails: dict[tuple[str, str, str], list[dict[str, Any]]] = {}

    for expense in expenses:
        summarized = summarize_expense(expense)
        currency = summarized["cost"]["currency_code"]
        shares = summarized["shares"]
        owner_share = next((share for share in shares if share["name"] == owner), None)
        if not owner_share:
            continue

        owner_net = as_decimal(owner_share["net_balance"])
        if owner_net == 0:
            continue

        for share in shares:
            name = share["name"]
            if name == owner:
                continue

            friend_net = as_decimal(share["net_balance"])
            if owner_net < 0 and friend_net > 0:
                payer = owner
                payee = name
                amount = min(abs(owner_net), friend_net)
            elif owner_net > 0 and friend_net < 0:
                payer = name
                payee = owner
                amount = min(owner_net, abs(friend_net))
            else:
                continue

            trails.setdefault((payer, payee, currency), []).append({
                "expense_id": summarized["id"],
                "description": summarized["description"],
                "date": summarized["date"],
                "category": summarized["category"],
                "group_name": summarized["group_name"],
                "paid_by": summarized["paid_by"],
                "amount": float(amount),
                "currency": currency,
                "owner_paid_share": owner_share["paid_share"],
                "owner_owed_share": owner_share["owed_share"],
                "friend_name": name,
                "friend_paid_share": share["paid_share"],
                "friend_owed_share": share["owed_share"],
            })

    for trail in trails.values():
        trail.sort(key=lambda item: item.get("date") or "", reverse=True)

    return trails


def main() -> int:
    token = os.environ.get("SPLITWISE_ACCESS_TOKEN")
    if not token:
        print("SPLITWISE_ACCESS_TOKEN is required.", file=sys.stderr)
        return 2

    current_user = api_get("/get_current_user", token)["user"]
    friends = api_get("/get_friends", token).get("friends", [])
    expenses = fetch_expenses(token)
    summarized_expenses = [summarize_expense(expense) for expense in expenses]
    trails = balance_trails(current_user, expenses)
    balances = summarize_balances(current_user, friends)

    for balance in balances:
        balance["expense_trail"] = trails.get(
            (balance["from"], balance["to"], balance["currency"]),
            [],
        )

    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "owner_name": person_name(current_user),
        "balances": balances,
        "expenses": summarized_expenses,
    }

    json.dump(payload, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
