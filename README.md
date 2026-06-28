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

## Local SQLite Sync

The lightweight local store is SQLite. By default it lives at:

```text
/root/.hermes/splitwise/splitwise.db
```

Initial import:

```bash
SPLITWISE_ACCESS_TOKEN=your_token_here python3 connector/splitwise_db.py init-full
```

Incremental sync:

```bash
SPLITWISE_ACCESS_TOKEN=your_token_here python3 connector/splitwise_db.py sync
```

The incremental sync checks Splitwise notifications first. When no expense
activity is present, it only updates DB metadata. When an expense was added or
changed, it fetches the changed expense and refreshes balances.

Hermes can read from the same DB without calling Splitwise:

```bash
python3 connector/hermes_splitwise.py summary
python3 connector/hermes_splitwise.py payables
```

## Dashboard

The static dashboard lives in `docs/`. It uses browser ESM imports for React and
does not require a local build step.

## GitHub Pages Deployment

The dashboard deploys through `.github/workflows/pages.yml` to:

```text
https://aleezanooor.github.io/naziyah-splitwise-reports/
```

Add this repository secret before running the workflow:

```text
SPLITWISE_ACCESS_TOKEN
```

The workflow runs on pushes to `main`, manually through `workflow_dispatch`, and
every five minutes through GitHub Actions cron. Scheduled runs seed a temporary
SQLite DB from the previously deployed dashboard JSON, check Splitwise
notifications, fetch only changed expenses when needed, then render
`splitwise-export.live.json` from SQLite. The dashboard refreshes that file every
minute while it is open.

The passcode screen is a lightweight static gate for casual privacy only. GitHub
Pages serves static files publicly, so do not treat it as secure storage for
sensitive financial data.

It is not an official Splitwise product and is not endorsed by Splitwise.
