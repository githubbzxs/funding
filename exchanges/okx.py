import asyncio
import logging
import os
from collections import Counter
from typing import List, Optional

import httpx

from core.models import FundingRateItem

OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate"
OKX_INSTRUMENTS_URL = "https://www.okx.com/api/v5/public/instruments"
REQUEST_TIMEOUT = 10.0
OKX_MAX_CONCURRENCY = int(os.getenv("OKX_MAX_CONCURRENCY", "5"))
OKX_TOTAL_TIMEOUT = float(os.getenv("OKX_TOTAL_TIMEOUT", "15"))
OKX_RETRIES = int(os.getenv("OKX_RETRIES", "2"))
OKX_RETRY_BACKOFF = float(os.getenv("OKX_RETRY_BACKOFF", "0.5"))

logger = logging.getLogger(__name__)


def _backoff_seconds(attempt: int) -> float:
    return OKX_RETRY_BACKOFF * (2**attempt)


def okx_instid_to_unified(inst_id: str) -> str:
    return inst_id.replace("-SWAP", "-PERP")


def _parse_next_time(next_time: Optional[str]) -> Optional[int]:
    if next_time is None:
        return None
    try:
        return int(next_time)
    except (TypeError, ValueError):
        return None


async def _fetch_single_instrument(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, inst_id: str
) -> tuple[List[FundingRateItem], str | None]:
    params = {"instId": inst_id}

    for attempt in range(OKX_RETRIES + 1):
        try:
            async with sem:
                resp = await client.get(OKX_FUNDING_URL, params=params)

            if resp.status_code == 429:
                if attempt < OKX_RETRIES:
                    delay = _backoff_seconds(attempt)
                    logger.debug("OKX 429 for %s; retrying in %.2fs", inst_id, delay)
                    await asyncio.sleep(delay)
                    continue
                return [], "http_429"

            resp.raise_for_status()
            try:
                payload = resp.json()
            except ValueError:
                if attempt < OKX_RETRIES:
                    delay = _backoff_seconds(attempt)
                    logger.debug("OKX invalid JSON for %s; retrying in %.2fs", inst_id, delay)
                    await asyncio.sleep(delay)
                    continue
                return [], "invalid_json"

            code = payload.get("code")
            if code and code != "0":
                msg = payload.get("msg")
                if attempt < OKX_RETRIES:
                    delay = _backoff_seconds(attempt)
                    logger.debug(
                        "OKX API error for %s (code=%s msg=%s); retrying in %.2fs",
                        inst_id,
                        code,
                        msg,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return [], f"api_code_{code}"

            data = payload.get("data") or []
            if not data:
                return [], "empty"

            row = data[0]
            try:
                raw_rate = float(row.get("fundingRate", "0"))
            except (TypeError, ValueError):
                return [], "bad_rate"

            next_time = _parse_next_time(row.get("nextFundingTime"))
            unified_symbol = okx_instid_to_unified(inst_id)
            return (
                [
                    FundingRateItem(
                        exchange="OKX",
                        symbol=inst_id,
                        unified_symbol=unified_symbol,
                        funding_rate_8h=raw_rate,
                        raw_funding_rate=raw_rate,
                        next_funding_time=next_time,
                        max_leverage=None,
                    )
                ],
                None,
            )
        except httpx.TimeoutException:
            if attempt < OKX_RETRIES:
                delay = _backoff_seconds(attempt)
                logger.debug("OKX timeout for %s; retrying in %.2fs", inst_id, delay)
                await asyncio.sleep(delay)
                continue
            return [], "timeout"
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status >= 500 and attempt < OKX_RETRIES:
                delay = _backoff_seconds(attempt)
                logger.debug("OKX HTTP %s for %s; retrying in %.2fs", status, inst_id, delay)
                await asyncio.sleep(delay)
                continue
            return [], f"http_{status}"
        except httpx.HTTPError:
            if attempt < OKX_RETRIES:
                delay = _backoff_seconds(attempt)
                logger.debug("OKX network error for %s; retrying in %.2fs", inst_id, delay)
                await asyncio.sleep(delay)
                continue
            return [], "network_error"
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("Unexpected error fetching OKX funding for %s", inst_id, exc_info=True)
            return [], "unknown"

    return [], "unknown"


async def fetch_okx_funding() -> List[FundingRateItem]:
    logger.info(
        "Fetching OKX funding rates (concurrency=%d retries=%d budget=%.1fs)",
        OKX_MAX_CONCURRENCY,
        OKX_RETRIES,
        OKX_TOTAL_TIMEOUT,
    )
    items: List[FundingRateItem] = []
    leverage_map: dict[str, float | None] = {}
    inst_ids: list[str] = []
    error_counts: Counter[str] = Counter()
    try:
        limits = httpx.Limits(
            max_connections=max(1, OKX_MAX_CONCURRENCY * 2),
            max_keepalive_connections=max(1, OKX_MAX_CONCURRENCY),
        )
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, limits=limits) as client:
            inst_resp = await client.get(OKX_INSTRUMENTS_URL, params={"instType": "SWAP"})
            inst_resp.raise_for_status()
            try:
                inst_payload = inst_resp.json()
            except ValueError:
                logger.warning("OKX instruments returned invalid JSON")
                return items

            code = inst_payload.get("code")
            if code and code != "0":
                logger.warning(
                    "OKX instruments API error: code=%s msg=%s", code, inst_payload.get("msg")
                )
                return items

            inst_data = inst_payload.get("data") or []
            for row in inst_data:
                if not isinstance(row, dict):
                    continue
                inst_id = row.get("instId")
                settle_ccy = row.get("settleCcy")
                if isinstance(inst_id, str) and (inst_id.endswith("-USDT-SWAP") or settle_ccy == "USDT"):
                    inst_ids.append(inst_id)
                    try:
                        lever_val = float(row.get("lever", "0"))
                        leverage_map[inst_id] = lever_val if lever_val > 0 else None
                    except (TypeError, ValueError):
                        leverage_map[inst_id] = None
            logger.info("Discovered %d OKX USDT swap instruments", len(inst_ids))
            if not inst_ids:
                logger.warning("OKX instruments returned 0 USDT swaps (data_len=%d)", len(inst_data))
                return items

            sem = asyncio.Semaphore(max(1, OKX_MAX_CONCURRENCY))
            tasks = [asyncio.create_task(_fetch_single_instrument(client, sem, inst)) for inst in inst_ids]
            done, pending = await asyncio.wait(tasks, timeout=OKX_TOTAL_TIMEOUT)
            if pending:
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                error_counts["budget_timeout"] += len(pending)
                logger.warning(
                    "OKX funding fetch timed out after %.1fs (done=%d pending=%d)",
                    OKX_TOTAL_TIMEOUT,
                    len(done),
                    len(pending),
                )

            for task in done:
                try:
                    instrument_items, error_key = task.result()
                except Exception:
                    error_counts["task_exception"] += 1
                    logger.debug("OKX task exception", exc_info=True)
                    continue
                if error_key:
                    error_counts[error_key] += 1
                items.extend(instrument_items)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("Failed to fetch OKX funding rates: %s", exc)
        return items

    if leverage_map:
        for item in items:
            if item.symbol in leverage_map:
                item.max_leverage = leverage_map[item.symbol]

    if error_counts:
        logger.info(
            "OKX fetch summary: instruments=%d items=%d errors=%s",
            len(inst_ids),
            len(items),
            dict(error_counts),
        )
    if not items and inst_ids:
        logger.warning(
            "OKX returned 0 funding items (instruments=%d). Possible rate limiting or connectivity issues.",
            len(inst_ids),
        )
    logger.info("Fetched %d OKX funding items", len(items))
    return items
