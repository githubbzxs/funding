import asyncio
import logging
from typing import List, Optional

import httpx

from core.models import FundingRateItem

OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
OKX_INSTRUMENTS_URL = "https://www.okx.com/api/v5/public/instruments"
REQUEST_TIMEOUT = 10.0

logger = logging.getLogger(__name__)


def okx_instid_to_unified(inst_id: str) -> str:
    return inst_id.replace("-SWAP", "-PERP")


def _parse_next_time(next_time: Optional[str]) -> Optional[int]:
    if next_time is None:
        return None
    try:
        return int(next_time)
    except (TypeError, ValueError):
        return None


async def _fetch_single_instrument(client: httpx.AsyncClient, inst_id: str) -> List[FundingRateItem]:
    params = {"instId": inst_id}
    items: List[FundingRateItem] = []
    try:
        resp = await client.get(OKX_FUNDING_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or []
        if not data:
            return items
        row = data[0]
        raw_rate = float(row.get("fundingRate", "0"))
        next_time = _parse_next_time(row.get("nextFundingTime"))
        unified_symbol = okx_instid_to_unified(inst_id)
        items.append(
            FundingRateItem(
                exchange="OKX",
                symbol=inst_id,
                unified_symbol=unified_symbol,
                funding_rate_8h=raw_rate,
                raw_funding_rate=raw_rate,
                next_funding_time=next_time,
                max_leverage=None,  # filled later when available
            )
        )
    except Exception as exc:
        logger.warning("Failed to fetch OKX funding for %s: %s", inst_id, exc)
    return items


async def fetch_okx_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates for all USDT perpetual swap instruments on OKX.
    """
    logger.info("Fetching OKX funding rates")
    items: List[FundingRateItem] = []
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            inst_resp = await client.get(OKX_INSTRUMENTS_URL, params={"instType": "SWAP"})
            inst_resp.raise_for_status()
            inst_payload = inst_resp.json()
            inst_data = inst_payload.get("data") or []
            leverage_map: dict[str, float | None] = {}
            inst_ids = []
            for row in inst_data:
                if not isinstance(row, dict):
                    continue
                inst_id = row.get("instId")
                settle_ccy = row.get("settleCcy")
                if inst_id and (inst_id.endswith("-USDT-SWAP") or settle_ccy == "USDT"):
                    inst_ids.append(inst_id)
                    try:
                        lever_val = float(row.get("lever", "0"))
                        leverage_map[inst_id] = lever_val if lever_val > 0 else None  # type: ignore[assignment]
                    except (TypeError, ValueError):
                        leverage_map[inst_id] = None
            logger.info("Discovered %d OKX USDT swap instruments", len(inst_ids))

            tasks = [_fetch_single_instrument(client, inst) for inst in inst_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as exc:
        logger.warning("Failed to fetch OKX funding rates: %s", exc)
        return items

    for result in results:
        if isinstance(result, Exception):
            logger.warning("Error in OKX instrument fetch: %s", result)
            continue
        items.extend(result)

    # attach leverage info
    if leverage_map:
        for item in items:
            if item.symbol in leverage_map:
                item.max_leverage = leverage_map[item.symbol]

    logger.info("Fetched %d OKX funding items", len(items))
    return items
