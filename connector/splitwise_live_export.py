#!/usr/bin/env python3
"""Generate a live dashboard export with a cheap notification precheck."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from splitwise_export import api_get, build_payload

EXPENSE_ACTIVITY_TYPES = {
    0,   # Expense added
    1,   # Expense updated
    2,   # Expense deleted
    11,  # Debt simplification
    13,  # Expense undeleted
    14,  # Group currency conversion
    15,  # Friend currency conversion
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str) -> dict[str, Any] | None:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return None


def has_expense_activity(notifications: list[dict[str, Any]]) -> bool:
    for notification in notifications:
        source = notification.get("source") or {}
        if source.get("type") == "Expense":
            return True
        if notification.get("type") in EXPENSE_ACTIVITY_TYPES:
            return True
    return False


def export_fresh(token: str, reason: str, notifications: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    payload = build_payload(token)
    payload["refresh_reason"] = reason
    payload["checked_at"] = utc_now()
    payload["notification_count"] = len(notifications or [])
    return payload


def main() -> int:
    token = os.environ.get("SPLITWISE_ACCESS_TOKEN")
    if not token:
        print("SPLITWISE_ACCESS_TOKEN is required.", file=sys.stderr)
        return 2

    previous_url = os.environ.get("PREVIOUS_EXPORT_URL")
    previous = fetch_json(previous_url) if previous_url else None
    if not previous or not previous.get("exported_at"):
        payload = export_fresh(token, "no_previous_export")
    else:
        notifications = api_get(
            "/get_notifications",
            token,
            {
                "updated_after": previous["exported_at"],
                "limit": 20,
            },
        ).get("notifications", [])

        if has_expense_activity(notifications):
            payload = export_fresh(token, "expense_activity", notifications)
        else:
            payload = previous
            payload["refresh_reason"] = "no_expense_activity"
            payload["checked_at"] = utc_now()
            payload["notification_count"] = len(notifications)

    json.dump(payload, sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
