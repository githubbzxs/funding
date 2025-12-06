import logging
from typing import List, Optional

import httpx

from core.models import FundingRateItem

GATE_TICKERS_URL = "https://api.gateio.ws/api/v4/futures/usdt/tickers"
REQUEST_TIMEOUT = 10.0
GATE_DEFAULT_LEVERAGE = 50.0
ENABLE_GATE = True

logger = logging.getLogger(__name__)


def _gate_contract_to_unified(contract: str) -> Optional[str]:
    """
    Convert contract like BTC_USDT to BTC-USDT-PERP.
    """
    if "_" not in contract:
        return None
    base, quote = contract.split("_", 1)
    if not base or not quote:
        return None
    return f"{base}-USDT-PERP"


async def fetch_gate_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates from Gate USDT-M perpetuals.
    """
    if not ENABLE_GATE:
        return []

    logger.info("Fetching Gate funding rates")
    items: List[FundingRateItem] = []
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(GATE_TICKERS_URL)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch Gate funding rates: %s", exc)
        return items

    if not isinstance(data, list):
        logger.warning("Unexpected Gate response shape")
        return items

    for row in data:
        contract = row.get("contract")
        unified = _gate_contract_to_unified(contract) if contract else None
        if not unified:
            continue
        try:
            rate = row.get("funding_rate8h", row.get("funding_rate"))
            raw_rate = float(rate if rate is not None else "0")
        except (TypeError, ValueError):
            continue
        next_time = row.get("funding_next_apply")
        items.append(
            FundingRateItem(
                exchange="GATE",
                symbol=contract,
                unified_symbol=unified,
                funding_rate_8h=raw_rate,
                raw_funding_rate=raw_rate,
                next_funding_time=int(next_time) if isinstance(next_time, (int, str)) and str(next_time).isdigit() else None,
                max_leverage=GATE_DEFAULT_LEVERAGE,
            )
        )

    logger.info("Fetched %d Gate funding items", len(items))
    return items
