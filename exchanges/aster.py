import logging
from typing import List, Optional

import httpx

from core.models import FundingRateItem

ASTER_BASE = "https://fapi.asterdex.com"
PREMIUM_INDEX_PATH = "/fapi/v1/premiumIndex"
REQUEST_TIMEOUT = 10.0
ENABLE_ASTER = True
ASTER_DEFAULT_LEVERAGE = 50.0

logger = logging.getLogger(__name__)


def _aster_symbol_to_unified(symbol: str) -> Optional[str]:
    """
    Convert Aster symbol like BTCUSDT to BTC-USDT-PERP.
    """
    if not symbol.endswith("USDT"):
        return None
    base = symbol[:-4]
    if not base:
        return None
    return f"{base}-USDT-PERP"


async def fetch_aster_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates from Aster public endpoint (Binance-compatible schema).
    """
    if not ENABLE_ASTER:
        return []

    logger.info("Fetching Aster funding rates")
    items: List[FundingRateItem] = []
    url = ASTER_BASE + PREMIUM_INDEX_PATH
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch Aster funding rates: %s", exc)
        return items

    # Response can be an object or list; we normalize to list
    rows = data if isinstance(data, list) else [data]
    for row in rows:
        symbol = row.get("symbol")
        unified = _aster_symbol_to_unified(symbol) if symbol else None
        if not unified:
            continue
        try:
            raw_rate = float(row.get("lastFundingRate", "0"))
        except (TypeError, ValueError):
            continue

        next_time = row.get("nextFundingTime")
        items.append(
            FundingRateItem(
                exchange="ASTER",
                symbol=symbol,
                unified_symbol=unified,
                funding_rate_8h=raw_rate,
                raw_funding_rate=raw_rate,
                next_funding_time=int(next_time) if isinstance(next_time, (int, str)) and str(next_time).isdigit() else None,
                max_leverage=ASTER_DEFAULT_LEVERAGE,
            )
        )

    logger.info("Fetched %d Aster funding items", len(items))
    return items
