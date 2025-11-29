import logging
from typing import List

import httpx

from core.models import FundingRateItem

GRVT_URL = "https://api.grvt.io/market-data/funding-rates"
REQUEST_TIMEOUT = 10.0
ENABLE_GRVT = True
GRVT_DEFAULT_LEVERAGE = 50.0

logger = logging.getLogger(__name__)


def grvt_inst_to_unified(inst: str) -> str:
    symbol = inst.replace("_", "-")
    if symbol.endswith("-Perp"):
        symbol = symbol[:-5] + "-PERP"
    return symbol


async def fetch_grvt_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates from GRVT public endpoint.
    Safe to fail: returns [] on any error.
    """
    if not ENABLE_GRVT:
        logger.info("GRVT fetch disabled via flag")
        return []

    logger.info("Fetching GRVT funding rates")
    items: List[FundingRateItem] = []
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(GRVT_URL)
            resp.raise_for_status()
            data = resp.json()

        if not isinstance(data, list):
            logger.warning("Unexpected GRVT response shape")
            return items

        for entry in data:
            inst = entry.get("i")
            if not inst:
                continue
            unified_symbol = grvt_inst_to_unified(inst)
            try:
                raw_rate = float(entry.get("fr", "0"))
                interval_hours = float(entry.get("fi", 8)) or 8.0
            except (TypeError, ValueError):
                logger.debug("Skipping GRVT entry with invalid numbers: %s", entry)
                continue

            funding_rate_8h = raw_rate * (8.0 / interval_hours)
            next_time = entry.get("ft")
            items.append(
                FundingRateItem(
                    exchange="GRVT",
                    symbol=inst,
                    unified_symbol=unified_symbol,
                    funding_rate_8h=funding_rate_8h,
                    raw_funding_rate=raw_rate,
                    next_funding_time=next_time if isinstance(next_time, int) else None,
                    max_leverage=GRVT_DEFAULT_LEVERAGE,
                )
            )

        logger.info("Fetched %d GRVT funding items", len(items))
        return items
    except Exception as exc:
        logger.warning("Failed to fetch GRVT funding rates: %s", exc)
        return []
