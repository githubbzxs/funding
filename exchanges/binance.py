import logging
import os
from typing import List, Optional
from urllib.parse import quote

import httpx

from core.models import ExchangeName, FundingRateItem

BINANCE_API_PATH = "/fapi/v1/premiumIndex"
BINANCE_HOSTS = [
    "www.binance.com",
    "fapi.binance.com",
    "fapi1.binance.com",
    "fapi2.binance.com",
]
PROXY_TEMPLATES = [
    "https://api.allorigins.win/raw?url={url}",
    "https://corsproxy.io/?{url}",
]
BINANCE_QUOTE = "USDT"
REQUEST_TIMEOUT = 8.0
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
    Tries direct access first, then falls back to proxy services.
    """
    logger.info("Fetching Binance funding rates")
    items: List[FundingRateItem] = []
    data = None
    errors = []

    urls_to_try = []
    for host in BINANCE_HOSTS:
        urls_to_try.append(f"https://{host}{BINANCE_API_PATH}")
    for host in BINANCE_HOSTS[:2]:
        direct_url = f"https://{host}{BINANCE_API_PATH}"
        for proxy_tpl in PROXY_TEMPLATES:
            urls_to_try.append(proxy_tpl.format(url=quote(direct_url, safe="")))

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        for url in urls_to_try:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    logger.info("Binance fetch succeeded: %s (%d items)", url[:60], len(data))
                    break
                else:
                    err_msg = f"{url[:40]}... invalid response"
                    errors.append(err_msg)
                    logger.debug("Binance URL returned invalid data: %s", url[:60])
                    data = None
            except httpx.ConnectError as e:
                errors.append(f"{url[:40]}... connect_error")
                logger.debug("Binance connect error %s: %s", url[:40], e)
            except httpx.TimeoutException as e:
                errors.append(f"{url[:40]}... timeout")
                logger.debug("Binance timeout %s: %s", url[:40], e)
            except Exception as exc:
                errors.append(f"{url[:40]}... {type(exc).__name__}")
                logger.debug("Binance endpoint failed %s: %s", url[:50], exc)
                continue

    if not data:
        logger.warning("All Binance endpoints failed: %s", "; ".join(errors[:5]))
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
