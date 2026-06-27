# Naziyah Splitwise Reports

Personal non-commercial Splitwise reporting connector and dashboard.

The deployed React dashboard shows who the account owner needs to pay, who owes
the account owner, recent expenses, expense categories, groups, and per-person
shares. It is hosted as a static GitHub Pages app from `docs/` so no Splitwise
credentials are stored in the browser or in this repository.

## Local Export

Use the connector script locally after obtaining a Splitwise OAuth access token:

```bash
SPLITWISE_ACCESS_TOKEN=your_token_here python connector/splitwise_export.py > splitwise-export.json
```

Then open the dashboard and import `splitwise-export.json`.

## Dashboard

The static dashboard lives in `docs/`. It uses browser ESM imports for React and
does not require a local build step.

It is not an official Splitwise product and is not endorsed by Splitwise.
