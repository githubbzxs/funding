import logging
from typing import List

from core.models import FundingRateItem

# TODO: wire real Aster funding endpoint when available.
ENABLE_ASTER = False
ASTER_DEFAULT_LEVERAGE = 50.0

logger = logging.getLogger(__name__)


async def fetch_aster_funding() -> List[FundingRateItem]:
    """
    Placeholder for Aster funding rates.
    Returns [] until the official public endpoint is confirmed.
    """
    if not ENABLE_ASTER:
        logger.info("Aster funding fetch disabled (no public endpoint configured)")
        return []
    return []
