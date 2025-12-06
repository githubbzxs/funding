import logging
import time
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

REFRESH_INTERVAL = 30  # seconds

CACHE: Dict[str, Any] = {"timestamp": 0.0, "rows": []}
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
    items = await collect_all()
    rows = build_ranking(items)
    now = time.time()
    CACHE["timestamp"] = now
    CACHE["rows"] = rows
    # append to in-memory history
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
    """
    Return funding rate arbitrage ranking, refreshing periodically.
    """
    now = time.time()
    cached_rows = CACHE.get("rows", [])
    timestamp = CACHE.get("timestamp", 0.0)
    if cached_rows and (now - timestamp) < REFRESH_INTERVAL:
        rows = cached_rows
    else:
        try:
            rows = await _refresh_cache()
        except Exception as exc:
            logger.exception("Failed to refresh funding data: %s", exc)
            rows = cached_rows or []

    serialized = [asdict(row) for row in rows]
    return {"updated_at": CACHE.get("timestamp", now), "rows": serialized}


@app.get("/api/funding/history")
async def get_funding_history(symbol: str) -> dict:
    """
    Return recent funding history for a symbol collected in memory.
    """
    history = HISTORY.get(symbol, [])
    return {"symbol": symbol, "history": history}


@app.get("/", include_in_schema=False)
async def read_root() -> FileResponse:
    """Serve the minimal frontend."""
    return FileResponse("static/index.html")


if __name__ == "__main__":
    import os
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WORKERS", "1"))
    uvicorn.run("app:app", host=host, port=port, workers=workers)
