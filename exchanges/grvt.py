import asyncio
import logging
from typing import List

import httpx

from core.models import FundingRateItem

GRVT_INSTRUMENTS_URL = "https://market-data.grvt.io/lite/v1/instruments"
GRVT_TICKER_URL = "https://market-data.grvt.io/lite/v1/ticker"
REQUEST_TIMEOUT = 10.0
ENABLE_GRVT = True
GRVT_DEFAULT_LEVERAGE = 50.0
GRVT_CONCURRENCY = 10

logger = logging.getLogger(__name__)


def grvt_inst_to_unified(inst: str) -> str:
    """Convert GRVT instrument like BTC_USDT_Perp to BTC-USDT-PERP."""
    symbol = inst.replace("_", "-")
    if symbol.endswith("-Perp"):
        symbol = symbol[:-5] + "-PERP"
    return symbol


async def _fetch_instruments(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.post(GRVT_INSTRUMENTS_URL, json={})
    resp.raise_for_status()
    payload = resp.json()
    rows = (payload or {}).get("r") or []
    if not isinstance(rows, list):
        logger.warning("Unexpected GRVT instruments payload")
        return []
    return rows


async def _fetch_ticker(
    client: httpx.AsyncClient, instrument: str, interval_hours: float
) -> FundingRateItem | None:
    try:
        resp = await client.post(GRVT_TICKER_URL, json={"i": instrument})
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.debug("GRVT ticker request failed for %s: %s", instrument, exc)
        return None

    ticker = (payload or {}).get("r") or {}
    raw_rate_val = ticker.get("fr")
    if raw_rate_val is None:
        raw_rate_val = ticker.get("fr1")
    try:
        raw_rate_pct = float(raw_rate_val)
    except (TypeError, ValueError):
        return None

    raw_rate = raw_rate_pct / 100.0  # API returns percentage points

    interval = interval_hours or 8.0
    funding_rate_8h = raw_rate * (8.0 / interval) if interval else raw_rate

    return FundingRateItem(
        exchange="GRVT",
        symbol=instrument,
        unified_symbol=grvt_inst_to_unified(instrument),
        funding_rate_8h=funding_rate_8h,
        raw_funding_rate=raw_rate,
        next_funding_time=None,
        max_leverage=GRVT_DEFAULT_LEVERAGE,
    )


async def fetch_grvt_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates from GRVT (lite ticker endpoint).
    Safe to fail: returns [] on any error.
    """
    if not ENABLE_GRVT:
        logger.info("GRVT fetch disabled via flag")
        return []

    logger.info("Fetching GRVT funding rates")
    items: List[FundingRateItem] = []
    semaphore = asyncio.Semaphore(GRVT_CONCURRENCY)

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            instruments = await _fetch_instruments(client)
            # Only keep USDT perps
            perp_insts = [
                (row.get("i"), row.get("fi"))
                for row in instruments
                if row.get("k") == "PERPETUAL" and row.get("q") == "USDT" and row.get("i")
            ]

            async def _guarded_fetch(inst_name: str, interval: float):
                async with semaphore:
                    return await _fetch_ticker(client, inst_name, float(interval or 8))

            tasks = [
                _guarded_fetch(inst_name, interval or 8) for inst_name, interval in perp_insts
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.warning("Failed to fetch GRVT funding rates: %s", exc)
        return items

    for result in results:
        if isinstance(result, Exception):
            logger.debug("GRVT ticker task error: %s", result)
            continue
        if result:
            items.append(result)

    logger.info("Fetched %d GRVT funding items", len(items))
    return items
