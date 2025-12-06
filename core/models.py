from dataclasses import dataclass
from typing import Literal

ExchangeName = Literal[
    "BINANCE",
    "OKX",
    "LIGHTER",
    "GRVT",
    "GATE",
    "BYBIT",
    "BITGET",
    "ASTER",
    "BACKPACK",
]


@dataclass
class FundingRateItem:
    exchange: ExchangeName
    symbol: str
    unified_symbol: str
    funding_rate_8h: float
    raw_funding_rate: float
    next_funding_time: int | None
    max_leverage: float | None = None


@dataclass
class FundingDiffRow:
    unified_symbol: str
    max_rate_exchange: ExchangeName
    max_rate: float
    min_rate_exchange: ExchangeName
    min_rate: float
    diff: float
    leverage_used: float
    nominal_funding_max_leverage: float
    # aliases for clarity in frontend
    actual_diff: float | None = None
    nominal_spread: float | None = None
    details: list[FundingRateItem]
