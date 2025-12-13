import asyncio
import logging
import os
import time
from collections import Counter
from dataclasses import asdict
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.aggregator import build_ranking, collect_all
from core.models import FundingDiffRow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REFRESH_INTERVAL = int(os.getenv("REFRESH_INTERVAL", "30"))
REFRESH_TIMEOUT = float(os.getenv("REFRESH_TIMEOUT", "9"))

REFRESH_LOCK = asyncio.Lock()
CACHE: Dict[str, Any] = {
    "timestamp": 0.0,
    "rows": [],
    "meta": {},
    "last_error": None,
    "last_error_at": None,
}
HISTORY: Dict[str, list[dict]] = {}

app = FastAPI(title="Funding Arbitrage Monitor", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


async def _refresh_cache() -> list[FundingDiffRow]:
    started_at = time.time()
    items, fetch_status = await collect_all()
    rows = build_ranking(items)
    now = time.time()
    exchange_item_counts = Counter(item.exchange for item in items)

    CACHE["timestamp"] = now
    CACHE["rows"] = rows
    CACHE["meta"] = {
        "item_total": len(items),
        "exchange_item_counts": dict(exchange_item_counts),
        "row_total": len(rows),
        "refresh_ms": int((now - started_at) * 1000),
        "fetch_status": fetch_status,
    }
    CACHE["last_error"] = None
    CACHE["last_error_at"] = None

    logger.info(
        "Refreshed funding cache: items=%d rows=%d in %dms (per exchange: %s)",
        len(items),
        len(rows),
        CACHE["meta"]["refresh_ms"],
        dict(exchange_item_counts),
    )
    for row in rows:
        hist = HISTORY.setdefault(row.unified_symbol, [])
        hist.append(
            {
                "ts": now,
                "diff": row.diff,
                "nominal": row.nominal_spread or row.nominal_funding_max_leverage,
                "max_rate": row.max_rate,
                "min_rate": row.min_rate,
                "max_ex": row.max_rate_exchange,
                "min_ex": row.min_rate_exchange,
            }
        )
        if len(hist) > 200:
            del hist[:-200]
    return rows


@app.get("/api/funding/ranking")
async def get_funding_ranking() -> dict:
    now = time.time()
    cached_rows = CACHE.get("rows", [])
    timestamp = CACHE.get("timestamp", 0.0)
    if timestamp and (now - timestamp) < REFRESH_INTERVAL:
        rows = cached_rows
    elif REFRESH_LOCK.locked():
        logger.debug("Funding refresh already in progress; serving cached data")
        rows = cached_rows
    else:
        async with REFRESH_LOCK:
            now = time.time()
            cached_rows = CACHE.get("rows", [])
            timestamp = CACHE.get("timestamp", 0.0)
            if timestamp and (now - timestamp) < REFRESH_INTERVAL:
                rows = cached_rows
            else:
                try:
                    rows = await asyncio.wait_for(_refresh_cache(), timeout=REFRESH_TIMEOUT)
                except asyncio.TimeoutError:
                    logger.warning(
                        "Funding refresh timed out after %ss; serving cached data", REFRESH_TIMEOUT
                    )
                    CACHE["last_error"] = f"refresh_timeout_{REFRESH_TIMEOUT}s"
                    CACHE["last_error_at"] = time.time()
                    rows = cached_rows or []
                except Exception as exc:
                    logger.exception("Failed to refresh funding data: %s", exc)
                    CACHE["last_error"] = str(exc)
                    CACHE["last_error_at"] = time.time()
                    rows = cached_rows or []

    serialized = [asdict(row) for row in rows]
    updated_at = CACHE.get("timestamp") or now
    meta: dict[str, Any] = dict(CACHE.get("meta") or {})
    ts = CACHE.get("timestamp")
    if isinstance(ts, (int, float)) and ts:
        meta["cache_age_s"] = round(time.time() - ts, 3)
    meta["refresh_in_progress"] = REFRESH_LOCK.locked()
    meta["last_error"] = CACHE.get("last_error")
    meta["last_error_at"] = CACHE.get("last_error_at")
    return {"updated_at": updated_at, "rows": serialized, "meta": meta}


@app.get("/api/funding/history")
async def get_funding_history(symbol: str) -> dict:
    history = HISTORY.get(symbol, [])
    return {"symbol": symbol, "history": history}


@app.get("/", include_in_schema=False)
async def read_root() -> FileResponse:
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WORKERS", "1"))
    uvicorn.run("app:app", host=host, port=port, workers=workers)
