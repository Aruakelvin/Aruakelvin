"""Collection, filtering, risk flagging, scoring and aggregation."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .http import HttpClient
from .merge import merge_duplicates
from .models import Category, Opportunity
from .normalize import canon_chain, canon_protocol
from .sources import REGISTRY, Source

log = logging.getLogger(__name__)

# ---- risk thresholds -------------------------------------------------------
LOW_TVL_USD = 100_000
APR_OUTLIER = 500.0        # % total APR beyond which numbers are rarely real/sustainable
REWARD_DEPENDENT = 0.90    # >90% of yield is incentives
SPIKE_RATIO = 2.0          # current APR > 2x 30d mean
SCORE_APR_CAP = 150.0      # cap APR's contribution to the score


@dataclass
class ScanResult:
    opportunities: list[Opportunity]
    errors: dict[str, str] = field(default_factory=dict)
    source_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class Filters:
    chains: Sequence[str] = ()
    protocols: Sequence[str] = ()
    categories: Sequence[Category] = ()
    token: str | None = None            # deposited asset: substring of market name / deposit tokens
    reward_token: str | None = None     # asset the rewards are paid in
    min_tvl: float = 0.0
    min_reward_apr: float = 0.0
    max_apr: float | None = None
    min_daily_rewards: float = 0.0
    stablecoin_only: bool = False
    exclude_flags: Sequence[str] = ()

    def match(self, o: Opportunity) -> bool:
        if self.chains and o.chain not in {canon_chain(c) for c in self.chains}:
            return False
        if self.protocols:
            wanted = [canon_protocol(p) for p in self.protocols]
            if not any(o.protocol == w or o.protocol.startswith(w + "-") for w in wanted):
                return False
        if self.categories and o.category not in self.categories:
            return False
        if (o.tvl_usd or 0) < self.min_tvl:
            return False
        if (o.reward_apr or 0) < self.min_reward_apr:
            return False
        if self.max_apr is not None and o.total_apr > self.max_apr:
            return False
        if self.min_daily_rewards and (o.est_daily_rewards_usd or 0) < self.min_daily_rewards:
            return False
        if self.stablecoin_only and not o.stablecoin:
            return False
        if self.exclude_flags and set(self.exclude_flags) & set(o.flags):
            return False
        if self.token:
            needle = self.token.lower()
            if o.category == Category.COLLATERAL:
                # "Deposit USDe as collateral on USDe/USDC": only the collateral counts.
                hay = " ".join(o.tokens).lower()
            else:
                hay = " ".join([o.market, *o.tokens]).lower()
            if needle not in hay:
                return False
        if self.reward_token:
            needle = self.reward_token.lower()
            if not any(needle in r.symbol.lower() for r in o.reward_tokens):
                return False
        return True


class Analyzer:
    def __init__(
        self, http: HttpClient | None = None, sources: Iterable[str] | None = None, merge: bool = True
    ) -> None:
        self.http = http or HttpClient()
        self.merge = merge
        names = list(sources) if sources else list(REGISTRY)
        unknown = [n for n in names if n not in REGISTRY]
        if unknown:
            raise ValueError(f"unknown source(s): {', '.join(unknown)}; available: {', '.join(REGISTRY)}")
        self.sources: list[Source] = [REGISTRY[n](self.http) for n in names]

    # ---- collection --------------------------------------------------------
    def collect(self) -> ScanResult:
        result = ScanResult(opportunities=[])

        def run(src: Source) -> tuple[str, list[Opportunity] | None, str | None]:
            try:
                return src.name, list(src.fetch()), None
            except Exception as exc:  # one broken source must not kill the scan
                log.exception("source %s failed", src.name)
                return src.name, None, f"{type(exc).__name__}: {exc}"

        with ThreadPoolExecutor(max_workers=max(1, len(self.sources))) as pool:
            for name, opps, err in pool.map(run, self.sources):
                if err:
                    result.errors[name] = err
                    continue
                result.source_counts[name] = len(opps or [])
                result.opportunities.extend(opps or [])

        result.opportunities = enrich(result.opportunities, merge=self.merge)
        return result

    def scan(self, filters: Filters | None = None, sort: str = "score", limit: int | None = None) -> ScanResult:
        result = self.collect()
        result.opportunities = select(result.opportunities, filters, sort, limit)
        return result


# ---- pure functions (easy to test) -----------------------------------------
def select(
    opps: Iterable[Opportunity], filters: Filters | None = None, sort: str = "score", limit: int | None = None
) -> list[Opportunity]:
    filters = filters or Filters()
    out = [o for o in opps if filters.match(o)]
    out.sort(key=SORT_KEYS[sort], reverse=True)
    return out[:limit] if limit else out


SORT_KEYS = {
    "score": lambda o: o.score,
    "reward_apr": lambda o: o.reward_apr or 0.0,
    "total_apr": lambda o: o.total_apr,
    "tvl": lambda o: o.tvl_usd or 0.0,
    "daily_rewards": lambda o: o.est_daily_rewards_usd or 0.0,
}


def enrich(opps: list[Opportunity], merge: bool = True) -> list[Opportunity]:
    """Resolve symbols, merge cross-source duplicates, then flag and score.

    Returns the (possibly shorter) list; rows are modified in place.
    """
    resolve_token_symbols(opps)
    if merge:
        opps = merge_duplicates(opps)
    for o in opps:
        o.flags = risk_flags(o)
        o.score = score(o)
    return opps


def risk_flags(o: Opportunity) -> list[str]:
    flags: list[str] = []
    # Volume-based campaigns (e.g. swap rewards) have no TVL; don't penalize that.
    if o.tvl_usd is not None and o.tvl_usd < LOW_TVL_USD:
        flags.append("low_tvl")
    if o.total_apr > APR_OUTLIER or o.extra.get("outlier"):
        flags.append("apr_outlier")
    share = o.reward_share
    if (share is not None and share >= REWARD_DEPENDENT and o.base_apr is not None
            and o.category != Category.BORROWING):
        flags.append("reward_dependent")
    if o.il_risk:
        flags.append("il_risk")
    if o.apr_30d_mean and o.apr_30d_mean > 0 and o.total_apr > SPIKE_RATIO * o.apr_30d_mean:
        flags.append("apr_spike")
    if o.category == Category.BORROWING and o.total_apr <= 0:
        flags.append("net_negative")
    if "+" in o.source:
        flags.append("multi_source")
    if o.extra.get("reward_mismatch"):
        flags.append("reward_mismatch")
    if o.extra.get("unverified"):
        flags.append("unverified")
    if o.stablecoin:
        flags.append("stable")
    return flags


def score(o: Opportunity) -> float:
    """Risk-adjusted attractiveness, roughly 'APR you can trust'.

    * APR contribution is capped so absurd numbers do not dominate.
    * Depth: $1k TVL -> 0.05x weight, $1M -> 0.62x, $100M+ -> 1.0x (log scale).
    * Stability: penalize when current APR is far from its 30d mean.
    * Flags apply multiplicative haircuts.
    * Campaigns with no APR (pure volume/trading rewards) score on log10 of
      USD emitted per day, so a $10k/day pool scores ~8.
    """
    if o.total_apr <= 0 and o.category != Category.BORROWING and o.est_daily_rewards_usd:
        return round(2.0 * math.log10(max(o.est_daily_rewards_usd, 1.0)), 4)
    apr = max(0.0, min(o.total_apr, SCORE_APR_CAP))
    tvl = max(o.tvl_usd or 0.0, 1.0)
    depth = min(1.0, max(0.0, (math.log10(tvl) - 3.0) / 5.0))
    s = apr * (0.05 + 0.95 * depth)

    if o.apr_30d_mean and o.apr_30d_mean > 0 and o.total_apr > 0:
        ratio = min(o.total_apr, o.apr_30d_mean) / max(o.total_apr, o.apr_30d_mean)
        s *= 0.5 + 0.5 * ratio

    haircut = {"apr_outlier": 0.3, "low_tvl": 0.5, "il_risk": 0.85, "apr_spike": 0.8,
               "unverified": 0.5, "net_negative": 0.0}
    for f in o.flags:
        s *= haircut.get(f, 1.0)
    return round(s, 4)


def resolve_token_symbols(opps: list[Opportunity]) -> None:
    """Label address-only reward tokens (DefiLlama) with symbols other sources know (Merkl)."""
    known: dict[tuple[str, str], str] = {}
    for o in opps:
        for addr, sym in o.token_addresses.items():
            known[(o.chain, addr)] = sym
    if not known:
        return
    for o in opps:
        for r in o.reward_tokens:
            if r.address and r.symbol.startswith("0x"):
                sym = known.get((o.chain, r.address.lower()))
                if sym:
                    r.symbol = sym


# ---- aggregation -----------------------------------------------------------
def summarize(opps: Iterable[Opportunity], by: str = "chain", top: int = 25) -> list[dict]:
    if by not in {"chain", "protocol", "category", "source"}:
        raise ValueError("by must be one of chain, protocol, category, source")
    buckets: dict[str, dict] = {}
    for o in opps:
        key = str(getattr(o, by).value if by == "category" else getattr(o, by))
        b = buckets.setdefault(key, {by: key, "markets": 0, "tvl_usd": 0.0, "daily_rewards_usd": 0.0,
                                     "_apr_w": 0.0, "_tvl_w": 0.0, "best": None})
        b["markets"] += 1
        tvl = o.tvl_usd or 0.0
        b["tvl_usd"] += tvl
        b["daily_rewards_usd"] += o.est_daily_rewards_usd or 0.0
        if o.reward_apr is not None and tvl > 0:
            b["_apr_w"] += o.reward_apr * tvl
            b["_tvl_w"] += tvl
        if b["best"] is None or o.score > b["best"].score:
            b["best"] = o
    rows = []
    for b in buckets.values():
        best = b.pop("best")
        apr_w, tvl_w = b.pop("_apr_w"), b.pop("_tvl_w")
        b["tvl_weighted_reward_apr"] = apr_w / tvl_w if tvl_w else None
        b["best_market"] = f"{best.protocol}: {best.market} ({best.chain})" if best else None
        rows.append(b)
    rows.sort(key=lambda r: r["daily_rewards_usd"], reverse=True)
    return rows[:top]
