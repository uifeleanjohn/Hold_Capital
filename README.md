# HoldCapital API — Phase A

The hosted starting point: a FastAPI service that wraps the **same verified
engine** as the local app, with accounts, a database, CSV import, an EODHD
price job, and an engine-backed dashboard.

## Run locally

```
cd server
pip install -r requirements.txt
uvicorn app.main:app --reload --port 5055
```

Open http://127.0.0.1:5055/docs for interactive API docs. With no config it uses
a local SQLite database and seed prices — it runs offline out of the box.

## Verify it works

```
python scripts/smoke_test.py
```

Signs up a user, imports the sample broker CSVs, refreshes prices, and asserts
the dashboard's net capital gain matches the engine ($3,668.68). Expect `PASS`.

## Endpoints

| Method & path | Purpose |
|---|---|
| `POST /auth/signup` · `POST /auth/login` | Get a JWT bearer token |
| `GET /me` · `POST /me/income` | Profile; set salary for ATO-bracket tax |
| `POST /portfolio/import` | Import broker/statement CSVs (reuses the importer) |
| `POST /portfolio/trade` | Add one manual trade |
| `GET /portfolio` | List trades & dividends |
| `POST /prices/refresh` · `GET /prices` | Refresh / read cached prices |
| `GET /dashboard` | Engine-computed CGT, income, tax, exposure, positions, actions |
| `POST /billing/checkout` · `GET /billing/status` | Stripe subscription (stub mode without keys) |
| `POST /billing/webhook` | Stripe events → update user tier |
| `GET /pro/edge` | Example feature gated to Plus/Pro |
| `GET /` | Serves the connected web app (login + dashboard) |
| `GET /healthz` | Liveness check |

All routes except signup/login/healthz/`/` require `Authorization: Bearer <token>`.

## The web app

Open `http://127.0.0.1:5055/` — the full 4-tab app (tax, performance, journal,
screener) served from the API. Sign up, add trades or import CSVs, and it runs
the same engine against your saved portfolio with live (cached) prices. It's the
hosted counterpart of the standalone `HoldCapital.html`.

## Billing

Tiers: `free` / `plus` / `pro` on the user. With no Stripe keys it runs in
**stub mode** (a fake checkout that flips the tier, so the flow is testable).
Set `STRIPE_SECRET_KEY`, the price ids, and `STRIPE_WEBHOOK_SECRET` to go live;
point a Stripe webhook at `/billing/webhook`.

## Deploy (Render blueprint)

Push this folder to GitHub, then in Render choose **New → Blueprint** and select
`render.yaml`. It provisions the API (Docker), a Postgres database, and a daily
price-refresh cron. Set `EODHD_API_KEY`, `PUBLIC_URL`, and the Stripe vars in the
dashboard. Other hosts: use the `Dockerfile` or the `Procfile`.

## Configuration (`.env`)

| Var | Default | Notes |
|---|---|---|
| `DATABASE_URL` | SQLite file | Set to a managed Postgres URL in production |
| `JWT_SECRET` | dev value | **Change this** to a long random string |
| `EODHD_API_KEY` | blank | Blank = seed prices; set to pull live (delayed) prices |

## Architecture

- `app/core/` — the vendored, verified engine + importer (single source of truth
  for all calculations; shared with the local app).
- `app/bridge.py` — turns stored trades/dividends + cached prices into engine
  inputs and returns a JSON dashboard.
- `app/marketdata.py` — EODHD client + cache refresh (seed fallback).
- `jobs/refresh_prices.py` — daily price job; schedule with cron / platform scheduler.

## Deploy (sketch)

1. Provision managed Postgres; set `DATABASE_URL`.
2. Deploy to Render / Fly.io / Railway: start command `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Set `JWT_SECRET` and `EODHD_API_KEY`.
4. Add a daily scheduled job running `python -m jobs.refresh_prices`.

## Production hardening (done)

- **bcrypt** password hashing (legacy PBKDF2 hashes still verify).
- **Server-side journal notes** (`/journal`) — annotations persist per user in
  the database, not just the browser.
- **Live metals** — gold/silver/platinum priced via EODHD forex (USD spot ÷
  AUD/USD), using the same EODHD key as equities; seed fallback when unset.

## Still to do before real users

Trade-confirmation email sync and the SnapTrade "connect your broker" flow;
a privacy policy + data export/delete; rate limiting and basic abuse controls;
and a lawyer check on AFSL/TPB positioning. None are large.

This is a prototype scaffold — general information tooling, not financial or
tax advice.
