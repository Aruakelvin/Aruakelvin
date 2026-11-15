"""Normalized data model shared by every incentive source."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Category(str, Enum):
    """What the user has to do to earn the incentive."""

    LP = "lp"                # provide liquidity to an AMM / DEX pool
    TRADING = "trading"      # swap / perp volume, trading-fee rebates
    LENDING = "lending"      # supply assets to a money market
    BORROWING = "borrowing"  # borrow assets (borrow-side rewards)
    STAKING = "staking"      # stake / restake / vault deposit
    HOLDING = "holding"      # simply hold a token / position
    OTHER = "other"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


@dataclass
class RewardToken:
    symbol: str
    address: str | None = None
    daily_usd: float | None = None


@dataclass
class Opportunity:
    """A single incentivized market, normalized across sources."""

    source: str                      # e.g. "defillama", "merkl"
    source_id: str                   # id inside the source
    chain: str                       # canonical lowercase chain name
    protocol: str                    # canonical lowercase protocol slug
    market: str                      # human-readable market name / pair
    category: Category
    tvl_usd: float | None = None
    base_apr: float | None = None    # organic yield (fees / interest), percent
    reward_apr: float | None = None  # incentive yield, percent
    reward_tokens: list[RewardToken] = field(default_factory=list)
    daily_rewards_usd: float | None = None
    apr_30d_mean: float | None = None
    stablecoin: bool | None = None
    il_risk: bool | None = None
    url: str | None = None
    tokens: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    # Populated by the analyzer.
    score: float = 0.0
    flags: list[str] = field(default_factory=list)

    @property
    def total_apr(self) -> float:
        return (self.base_apr or 0.0) + (self.reward_apr or 0.0)

    @property
    def reward_share(self) -> float | None:
        """Fraction of total APR coming from incentives (0..1)."""
        total = self.total_apr
        if total <= 0 or self.reward_apr is None:
            return None
        return max(0.0, min(1.0, self.reward_apr / total))

    @property
    def est_daily_rewards_usd(self) -> float | None:
        """Explicit daily rewards if known, else derived from TVL * reward APR."""
        if self.daily_rewards_usd is not None:
            return self.daily_rewards_usd
        if self.tvl_usd and self.reward_apr:
            return self.tvl_usd * self.reward_apr / 100.0 / 365.0
        return None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["total_apr"] = self.total_apr
        d["reward_share"] = self.reward_share
        d["est_daily_rewards_usd"] = self.est_daily_rewards_usd
        return d
