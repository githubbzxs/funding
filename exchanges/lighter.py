import logging
import re
import time
from typing import Dict, List

import httpx

from core.models import FundingRateItem

LIGHTER_URL = "https://mainnet.zklighter.elliot.ai/api/v1/funding-rates"
LIGHTER_LEVERAGE_DOC_URL = (
    "https://r.jina.ai/https://docs.lighter.xyz/perpetual-futures/contract-specifications"
)
REQUEST_TIMEOUT = 10.0
ENABLE_LIGHTER = True
LIGHTER_DEFAULT_LEVERAGE = 50.0
LEVERAGE_CACHE_TTL = 1800  # seconds

logger = logging.getLogger(__name__)

_LEVERAGE_CACHE: Dict[str, object] = {"timestamp": 0.0, "map": {}}
LEVERAGE_LINE_RE = re.compile(r"^(?P<lev>\d+(?:\.\d+)?)x$")
SYMBOL_RE = re.compile(r"^[A-Z0-9]+$")


def _parse_leverage_from_markdown(text: str) -> dict[str, float]:
    """
    Parse leverage table from Lighter docs (markdown rendered by jina ai proxy).
    We look for sequences like: SYMBOL, price step, amount step, Leverage -> "50x".
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    mapping: dict[str, float] = {}
    for idx, line in enumerate(lines):
        m = LEVERAGE_LINE_RE.fullmatch(line)
        if not m:
            continue
        symbol_idx = idx - 3  # table layout puts leverage 3 rows after symbol
        if symbol_idx < 0:
            continue
        symbol = lines[symbol_idx]
        if symbol.lower() in {"symbol", "leverage"}:
            continue
        if not SYMBOL_RE.fullmatch(symbol):
            continue
        try:
            lev = float(m.group("lev"))
        except (TypeError, ValueError):
            continue
        mapping[symbol] = lev
    return mapping


async def _get_lighter_leverages(client: httpx.AsyncClient) -> dict[str, float]:
    """
    Pull per-symbol leverage settings from Lighter docs.
    Cached for LEVERAGE_CACHE_TTL to avoid hammering the docs site.
    """
    now = time.time()
    cached_ts = float(_LEVERAGE_CACHE.get("timestamp", 0.0))
    cached_map = _LEVERAGE_CACHE.get("map") or {}
    if cached_map and (now - cached_ts) < LEVERAGE_CACHE_TTL:
        return cached_map  # type: ignore[return-value]

    try:
        resp = await client.get(LIGHTER_LEVERAGE_DOC_URL)
        resp.raise_for_status()
        mapping = _parse_leverage_from_markdown(resp.text)
        if mapping:
            _LEVERAGE_CACHE["timestamp"] = now
            _LEVERAGE_CACHE["map"] = mapping
        return mapping
    except Exception as exc:
        logger.warning("Failed to fetch Lighter leverage table: %s", exc)
        # fall back to any cached map we might have
        return cached_map if isinstance(cached_map, dict) else {}


async def fetch_lighter_funding() -> List[FundingRateItem]:
    """
    Fetch funding rates from zkLighter public endpoint.
    Safe to fail: returns [] on any error.
    """
    if not ENABLE_LIGHTER:
        logger.info("Lighter fetch disabled via flag")
        return []

    logger.info("Fetching Lighter funding rates")
    items: List[FundingRateItem] = []
    missing_leverage: set[str] = set()
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.get(LIGHTER_URL)
            resp.raise_for_status()
            data = resp.json()
            leverage_map = await _get_lighter_leverages(client)

        # Schema 1: {"funding_rates": [...]} (current as of 2025-11)
        if isinstance(data, dict) and isinstance(data.get("funding_rates"), list):
            entries = data["funding_rates"]
            for entry in entries:
                exch = str(entry.get("exchange", "")).lower()
                # Only trust rows that are explicitly from lighter to avoid mixing in other exchanges
                if exch not in {"lighter", "zklighter"}:
                    continue
                symbol = entry.get("symbol")
                if not symbol:
                    continue
                try:
                    raw_rate = float(entry.get("rate", "0"))
                except (TypeError, ValueError):
                    continue
                unified_symbol = f"{symbol}-USDT-PERP"
                symbol_key = symbol.upper()
                lever_val = leverage_map.get(symbol_key)
                if lever_val is None:
                    missing_leverage.add(symbol_key)
                items.append(
                    FundingRateItem(
                        exchange="LIGHTER",
                        symbol=symbol,
                        unified_symbol=unified_symbol,
                        funding_rate_8h=raw_rate,
                        raw_funding_rate=raw_rate,
                        next_funding_time=None,
                        max_leverage=lever_val if lever_val is not None else LIGHTER_DEFAULT_LEVERAGE,
                    )
                )
        # Schema 2: list of dicts with instrument/fundingRate/fundingIntervalHours
        elif isinstance(data, list):
            for entry in data:
                instrument = entry.get("instrument")
                if not instrument:
                    continue
                try:
                    raw_rate = float(entry.get("fundingRate", "0"))
                    interval_hours = float(entry.get("fundingIntervalHours", 8)) or 8.0
                except (TypeError, ValueError):
                    logger.debug("Skipping Lighter entry with invalid numbers: %s", entry)
                    continue

                next_time = entry.get("nextFundingTime")
                funding_rate_8h = raw_rate * (8.0 / interval_hours)
                symbol_key = instrument.upper()
                lever_val = leverage_map.get(symbol_key)
                if lever_val is None:
                    missing_leverage.add(symbol_key)
                items.append(
                    FundingRateItem(
                        exchange="LIGHTER",
                        symbol=instrument,
                        unified_symbol=instrument,
                        funding_rate_8h=funding_rate_8h,
                        raw_funding_rate=raw_rate,
                        next_funding_time=next_time if isinstance(next_time, int) else None,
                        max_leverage=lever_val if lever_val is not None else LIGHTER_DEFAULT_LEVERAGE,
                    )
                )
        else:
            logger.warning("Unexpected Lighter response shape")

        if missing_leverage:
            sample = ", ".join(sorted(list(missing_leverage))[:10])
            logger.info(
                "Lighter leverage missing for %d symbols (sample: %s); defaulting to %.0fx",
                len(missing_leverage),
                sample,
                LIGHTER_DEFAULT_LEVERAGE,
            )
        logger.info("Fetched %d Lighter funding items", len(items))
        return items
    except Exception as exc:
        logger.warning("Failed to fetch Lighter funding rates: %s", exc)
        return []
