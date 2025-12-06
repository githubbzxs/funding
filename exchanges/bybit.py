import logging
from typing import List, Optional

import httpx

from core.models import FundingRateItem

BYBIT_TICKERS_URL = "https://api.bybit.com/v5/market/tickers"
REQUEST_TIMEOUT = 10.0
BYBIT_DEFAULT_LEVERAGE = 50.0
ENABLE_BYBIT = True

logger = logging.getLogger(__name__)


def _bybit_symbol_to_unified(symbol: str) -> Optional[str]:
    """
    Convert Bybit linear symbol like BTCUSDT to BTC-USDT-PERP.
    """
    if not symbol.endswith("USDT"):
        return None
    base = symbol[:-4]
    if not base:
        return None
    return f"{base}-USDT-PERP"


def _to_int_safe(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def fetch_bybit_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates from Bybit USDT perpetuals (linear).
    """
    if not ENABLE_BYBIT:
        return []

    logger.info("Fetching Bybit funding rates")
    items: List[FundingRateItem] = []
    params = {"category": "linear"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(BYBIT_TICKERS_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch Bybit funding rates: %s", exc)
        return items

    result = (payload or {}).get("result") or {}
    rows = result.get("list") or []
    if not isinstance(rows, list):
        logger.warning("Unexpected Bybit response shape")
        return items

    for row in rows:
        symbol = row.get("symbol")
        unified = _bybit_symbol_to_unified(symbol) if symbol else None
        if not unified:
            continue
        try:
            raw_rate = float(row.get("fundingRate", "0"))
        except (TypeError, ValueError):
            continue
        next_time = _to_int_safe(row.get("nextFundingTime"))
        items.append(
            FundingRateItem(
                exchange="BYBIT",
                symbol=symbol,
                unified_symbol=unified,
                funding_rate_8h=raw_rate,
                raw_funding_rate=raw_rate,
                next_funding_time=next_time,
                max_leverage=BYBIT_DEFAULT_LEVERAGE,
            )
        )

    logger.info("Fetched %d Bybit funding items", len(items))
    return items
