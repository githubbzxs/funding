import asyncio
import logging
from typing import List

from core.aggregator import build_ranking, collect_all
from core.models import FundingDiffRow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def format_row(row: FundingDiffRow) -> str:
    max_part = f"{row.max_rate_exchange}({row.max_rate:.6f})"
    min_part = f"{row.min_rate_exchange}({row.min_rate:.6f})"
    nominal = row.nominal_funding_max_leverage
    return f"{row.unified_symbol:<16} {row.diff:+.6f} {nominal:+.6f} {max_part:<18} {min_part:<18}"


async def run_cli() -> None:
    logger.info("Collecting funding data...")
    items = await collect_all()
    ranking: List[FundingDiffRow] = build_ranking(items)
    top_rows = ranking[:20]

    print("Symbol            Diff(8h)   Nominal@lev  Max(Exch)          Min(Exch)")
    print("-" * 80)
    for row in top_rows:
        print(format_row(row))


if __name__ == "__main__":
    asyncio.run(run_cli())
