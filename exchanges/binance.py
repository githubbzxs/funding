import logging
from typing import List, Optional

import httpx

from core.models import ExchangeName, FundingRateItem

BINANCE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BINANCE_QUOTE = "USDT"
REQUEST_TIMEOUT = 10.0
# Binance USDT-M 通常支持最高 125x，作为无权限下的保守估计
BINANCE_DEFAULT_LEVERAGE = 125.0

logger = logging.getLogger(__name__)


def binance_symbol_to_unified(symbol: str) -> Optional[str]:
    """
    Convert Binance symbol like BTCUSDT to BTC-USDT-PERP.
    Returns None for symbols that are not USDT-margined perps.
    """
    if not symbol.endswith(BINANCE_QUOTE):
        return None
    base = symbol[: -len(BINANCE_QUOTE)]
    if not base:
        return None
    return f"{base}-USDT-PERP"


async def fetch_binance_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates from Binance USDT-M futures.
    """
    logger.info("Fetching Binance funding rates")
    items: List[FundingRateItem] = []
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(BINANCE_URL)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch Binance funding rates: %s", exc)
        return items

    for entry in data:
        symbol = entry.get("symbol")
        unified_symbol = binance_symbol_to_unified(symbol) if symbol else None
        if not unified_symbol:
            continue
        try:
            raw_rate = float(entry.get("lastFundingRate", "0"))
        except (TypeError, ValueError):
            logger.debug("Skipping Binance symbol with invalid rate: %s", symbol)
            continue

        next_time = entry.get("nextFundingTime")
        items.append(
            FundingRateItem(
                exchange="BINANCE",
                symbol=symbol,
                unified_symbol=unified_symbol,
                funding_rate_8h=raw_rate,
                raw_funding_rate=raw_rate,
                next_funding_time=next_time if isinstance(next_time, int) else None,
                max_leverage=BINANCE_DEFAULT_LEVERAGE,
            )
        )

    logger.info("Fetched %d Binance funding items", len(items))
    return items
