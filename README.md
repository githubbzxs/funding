# Funding Rate Arbitrage Monitor

Async FastAPI service that aggregates perpetual funding rates from Binance, OKX, zkLighter, and GRVT, normalizes them to 8-hour rates, ranks arbitrage spreads, and exposes them via REST plus a simple CLI table.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run CLI

```bash
python main_cli.py
```

## Run API

```bash
uvicorn app:app --reload
```

Endpoint: `GET /api/funding/ranking`

## Notes

- Uses public endpoints only; no API keys required.
- Refresh interval is controlled via `REFRESH_INTERVAL` in `app.py`.
- OKX instrument list is in `exchanges/okx.py` (`OKX_INSTRUMENTS`).
