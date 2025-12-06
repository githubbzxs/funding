import logging
from typing import List, Optional

import httpx

from core.models import FundingRateItem

BACKPACK_BASE = "https://api.backpack.exchange"
MARK_PRICES_PATH = "/api/v1/markPrices"
REQUEST_TIMEOUT = 10.0
ENABLE_BACKPACK = True
BACKPACK_DEFAULT_LEVERAGE = 50.0

logger = logging.getLogger(__name__)


def _to_int_safe(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _unify_symbol(symbol: str) -> Optional[str]:
    """
    Convert Backpack symbol (e.g., BTC/USDC or SOL_USDC) to BTC-USDC-PERP.
    """
    if not symbol:
        return None
    normalized = symbol.replace("/", "-").replace("_", "-")
    return f"{normalized}-PERP"


async def fetch_backpack_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates from Backpack public markPrices endpoint.
    """
    if not ENABLE_BACKPACK:
        return []

    logger.info("Fetching Backpack funding rates")
    items: List[FundingRateItem] = []
    url = BACKPACK_BASE + MARK_PRICES_PATH
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch Backpack funding rates: %s", exc)
        return items

    rows = data if isinstance(data, list) else [data]
    for row in rows:
        symbol = row.get("symbol")
        unified = _unify_symbol(symbol) if symbol else None
        if not unified:
            continue
        try:
            raw_rate = float(row.get("fundingRate", "0"))
        except (TypeError, ValueError):
            continue

        next_time = _to_int_safe(row.get("nextFundingTimestamp"))
        items.append(
            FundingRateItem(
                exchange="BACKPACK",
                symbol=symbol,
                unified_symbol=unified,
                funding_rate_8h=raw_rate,
                raw_funding_rate=raw_rate,
                next_funding_time=next_time,
                max_leverage=BACKPACK_DEFAULT_LEVERAGE,
            )
        )

    logger.info("Fetched %d Backpack funding items", len(items))
    return items
