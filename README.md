# Rule Mirror

Rule Mirror is a private beta web app for reviewing trading decisions after the fact. It imports user-owned CSV exports, reconstructs trades from executions, attaches historical market context, and scores rule adherence with deterministic logic. It is built for reflection and recordkeeping, not prediction or financial advice.

The project is designed as a serious full-stack portfolio piece: a FastAPI backend, SQLAlchemy/Alembic persistence, deterministic import and reconstruction logic, a polished TypeScript web client, and a preserved Flutter/iOS client scaffold for future native work.

## What it does

- Imports execution CSVs and maps broker/platform columns into normalized fills
- Reconstructs open and closed trades from the user's execution history
- Reviews closed trades against visible strategy rule profiles
- Keeps holdings snapshots separate in a `My portfolio` section
- Publishes only selected account summary metrics when public profile visibility is enabled
- Serves the frontend and API from one same-origin app for simple deployment

## Product boundaries

Rule Mirror does not place trades, recommend trades, predict outcomes, redistribute raw market data, or provide financial, legal, tax, brokerage, or fiduciary advice. Scores describe historical rule adherence only. Users are responsible for their own decisions and for making sure they have the right to upload each file.

## Architecture

- `backend/` contains the FastAPI API, authentication, SQLAlchemy models, Alembic migrations, CSV importers, trade reconstruction, market-data integration, strategy evaluation, and tests.
- `web/` contains the Vite TypeScript client with the main dashboard, imports, trades, portfolio, public profiles, settings, legal links, and responsive styling.
- `scripts/run_local.py` builds the web client, runs database migrations, and starts the combined local web/API service.
- `clients/ios_flutter/` preserves the earlier Flutter app structure for future iOS work.

## Local run

Install the Python and web dependencies first, then run:

```text
cd /path/to/Rule-Mirror
python3 scripts/run_local.py
```

The app starts at:

```text
http://127.0.0.1:8000
```

The local runner intentionally installs nothing. It expects `.venv` and `web/node_modules` to already exist.

## Configuration

Create a local `.env` from your deployment settings. Never commit `.env` files.

Important production values:

- `SECRET_KEY`: strong random secret
- `DATABASE_URL`: durable database connection
- `MARKET_DATA_PROVIDER`: `mock` locally or `twelve_data` when Twelve Data is configured
- `TWELVE_DATA_API_KEY`: required only for Twelve Data
- `ENVIRONMENT`: use `production` outside local development

The intended beta domain is:

```text
https://rulemirror.com
```

Support contact:

```text
silas@rulemirror.com
```

## Public beta deployment

Rule Mirror is designed to run behind Cloudflare. Use Cloudflare DNS for `rulemirror.com`, same-origin API requests under `/api/v1`, and Cloudflare SSL/TLS in Full (strict) mode once the origin has a valid certificate. Cloudflare Tunnel is a good option if the home server should not expose ports directly.

Do not deploy with local SQLite for real public traffic. Use a durable database, backups, HTTPS, a strong secret key, and a reviewed `.env`.

## Portfolio imports

Execution imports and holdings imports are separate on purpose.

- Execution CSVs feed the trade reconstruction and analysis engine.
- Holdings and purchase-history CSVs feed `My portfolio`.
- Portfolio snapshots never become strategy-scored trades unless they contain explicit execution fields and are imported through the execution importer.

## Verification

Backend:

```text
.venv/bin/python -m pytest -q
```

Frontend:

```text
cd web
npm run build
```

Additional gates used during hardening:

```text
.venv/bin/ruff check backend scripts
.venv/bin/mypy backend/app scripts/run_local.py
```

## License

This repository is source-available for evaluation and demonstration only. It is proprietary and not open source. See `LICENSE`.
