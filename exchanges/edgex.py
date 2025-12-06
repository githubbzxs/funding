import logging
from typing import List

from core.models import FundingRateItem

# TODO: add EdgeX funding API when specs are available.
ENABLE_EDGEX = False
EDGEX_DEFAULT_LEVERAGE = 50.0

logger = logging.getLogger(__name__)


async def fetch_edgex_funding() -> List[FundingRateItem]:
    """
    Placeholder for EdgeX funding rates.
    Returns [] until the public endpoint is confirmed.
    """
    if not ENABLE_EDGEX:
        logger.info("EdgeX funding fetch disabled (no public endpoint configured)")
        return []
    return []
