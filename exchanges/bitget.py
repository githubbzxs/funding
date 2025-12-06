import logging
from typing import List, Optional

import httpx

from core.models import FundingRateItem

BITGET_TICKERS_URL = "https://api.bitget.com/api/v2/mix/market/tickers"
REQUEST_TIMEOUT = 10.0
BITGET_DEFAULT_LEVERAGE = 50.0
ENABLE_BITGET = True

logger = logging.getLogger(__name__)


def _bitget_symbol_to_unified(symbol: str) -> Optional[str]:
    """
    Convert Bitget symbol (new v2 format BTCUSDT or legacy BTCUSDT_UMCBL) to BTC-USDT-PERP.
    """
    if not symbol:
        return None

    base = ""
    quote = ""
    if symbol.endswith("_UMCBL"):
        base_quote = symbol.replace("_UMCBL", "")
        if base_quote.endswith("USDT"):
            base = base_quote[:-4]
            quote = "USDT"
    else:
        if symbol.endswith("USDT"):
            base = symbol[:-4]
            quote = "USDT"

    if not base or quote != "USDT":
        return None
    return f"{base}-USDT-PERP"


def _to_int_safe(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def fetch_bitget_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates from Bitget USDT-M perpetuals.
    """
    if not ENABLE_BITGET:
        return []

    logger.info("Fetching Bitget funding rates")
    items: List[FundingRateItem] = []
    params = {"productType": "USDT-FUTURES"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(BITGET_TICKERS_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch Bitget funding rates: %s", exc)
        return items

    if (payload or {}).get("code") not in ("00000", "0", 0, None):
        logger.warning("Unexpected Bitget status code: %s", payload.get("code"))
        return items

    rows = (payload or {}).get("data") or []
    if not isinstance(rows, list):
        logger.warning("Unexpected Bitget response shape")
        return items

    for row in rows:
        symbol = row.get("symbol") or row.get("instId")
        unified = _bitget_symbol_to_unified(symbol) if symbol else None
        if not unified:
            continue
        try:
            raw_rate = float(row.get("fundingRate", "0"))
        except (TypeError, ValueError):
            continue
        next_time = _to_int_safe(row.get("nextFundingTime") or row.get("fundingTime") or row.get("fundTime"))
        items.append(
            FundingRateItem(
                exchange="BITGET",
                symbol=symbol,
                unified_symbol=unified,
                funding_rate_8h=raw_rate,
                raw_funding_rate=raw_rate,
                next_funding_time=next_time,
                max_leverage=BITGET_DEFAULT_LEVERAGE,
            )
        )

    logger.info("Fetched %d Bitget funding items", len(items))
    return items
