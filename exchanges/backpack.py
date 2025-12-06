import logging
from typing import List

from core.models import FundingRateItem

# TODO: add Backpack Exchange funding API once available.
ENABLE_BACKPACK = False
BACKPACK_DEFAULT_LEVERAGE = 50.0

logger = logging.getLogger(__name__)


async def fetch_backpack_funding() -> List[FundingRateItem]:
    """
    Placeholder for Backpack funding rates.
    Returns [] until the public funding endpoint is added.
    """
    if not ENABLE_BACKPACK:
        logger.info("Backpack funding fetch disabled (no public endpoint configured)")
        return []
    return []
