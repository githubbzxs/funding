import asyncio
import logging
import math
from collections import defaultdict
from dataclasses import asdict
from typing import Iterable, List

from core.models import ExchangeName, FundingDiffRow, FundingRateItem
from exchanges.binance import fetch_binance_funding
from exchanges.okx import fetch_okx_funding

logger = logging.getLogger(__name__)
DEFAULT_LEVERAGE = 50.0  # fallback when no leverage info is available
EXCHANGE_CACHE: dict[str, list[FundingRateItem]] = {}


async def collect_all() -> list[FundingRateItem]:
    """
    Fetch funding rates from all exchanges concurrently.
    If an exchange失败或返回空数据，尽量使用上次的缓存，降低“全是0”情况。
    """
    exchanges = [("BINANCE", fetch_binance_funding()), ("OKX", fetch_okx_funding())]
    coros = [c for _, c in exchanges]
    results = await asyncio.gather(*coros, return_exceptions=True)

    items: list[FundingRateItem] = []
    for (name, _), result in zip(exchanges, results):
        if isinstance(result, Exception):
            logger.error("Error while collecting funding for %s", name, exc_info=result)
            cached = EXCHANGE_CACHE.get(name, [])
            if cached:
                logger.info("Using cached %d items for %s due to error", len(cached), name)
                items.extend(cached)
            continue

        current = result or []
        if not current:
            cached = EXCHANGE_CACHE.get(name, [])
            if cached:
                logger.info("Using cached %d items for %s due to empty fetch", len(cached), name)
                items.extend(cached)
            else:
                logger.warning("No items for %s and no cache available", name)
            continue

        EXCHANGE_CACHE[name] = current
        items.extend(current)

    logger.info("Collected %d total funding items", len(items))
    return items


def build_ranking(items: Iterable[FundingRateItem]) -> list[FundingDiffRow]:
    """
    Build ranking rows grouped by unified_symbol and sorted by absolute diff descending.
    """
    grouped: defaultdict[str, List[FundingRateItem]] = defaultdict(list)
    for item in items:
        grouped[item.unified_symbol].append(item)

    rows: list[FundingDiffRow] = []
    for unified_symbol, symbol_items in grouped.items():
        # 只有同时存在两个交易所数据才计算价差
        if len(symbol_items) < 2:
            continue

        max_rate = max(si.funding_rate_8h for si in symbol_items)
        min_rate = min(si.funding_rate_8h for si in symbol_items)

        max_candidates = [si for si in symbol_items if math.isclose(si.funding_rate_8h, max_rate)]
        min_candidates = [si for si in symbol_items if math.isclose(si.funding_rate_8h, min_rate)]

        max_item = max_candidates[0]
        min_item = min_candidates[0]

        # Avoid showing the same exchange on both sides when we have alternatives
        if max_item.exchange == min_item.exchange:
            alt_min = next((si for si in min_candidates if si.exchange != max_item.exchange), None)
            if alt_min:
                min_item = alt_min
            else:
                alt_max = next((si for si in max_candidates if si.exchange != min_item.exchange), None)
                if alt_max:
                    max_item = alt_max

        diff = max_item.funding_rate_8h - min_item.funding_rate_8h

        lever_a = max_item.max_leverage or DEFAULT_LEVERAGE
        lever_b = min_item.max_leverage or DEFAULT_LEVERAGE
        leverage_used = min(lever_a, lever_b)
        nominal_diff = diff * leverage_used

        rows.append(
            FundingDiffRow(
                unified_symbol=unified_symbol,
                max_rate_exchange=max_item.exchange,
                max_rate=max_item.funding_rate_8h,
                min_rate_exchange=min_item.exchange,
                min_rate=min_item.funding_rate_8h,
                diff=diff,
                leverage_used=leverage_used,
                nominal_funding_max_leverage=nominal_diff,
                actual_diff=diff,
                nominal_spread=nominal_diff,
                details=symbol_items,
            )
        )

    rows.sort(key=lambda r: abs(r.diff), reverse=True)
    logger.info("Built ranking with %d rows", len(rows))
    return rows


def serialize_rows(rows: Iterable[FundingDiffRow]) -> list[dict]:
    """Helper to convert dataclass rows into plain dicts for JSON responses."""
    return [asdict(row) for row in rows]
