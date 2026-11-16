"""Collection, filtering, risk flagging, scoring and aggregation."""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .http import HttpClient
from .history import attach_history, llama_pool_id
from .merge import merge_duplicates
from .token_names import resolve_reward_token_names
from .models import Category, Opportunity
from .normalize import canon_chain, canon_protocol
from .sources import REGISTRY, Source

log = logging.getLogger(__name__)

# ---- risk thresholds -------------------------------------------------------
LOW_TVL_USD = 100_000
APR_OUTLIER = 500.0        # % total APR beyond which numbers are rarely real/sustainable
REWARD_DEPENDENT = 0.90    # >90% of yield is incentives
SPIKE_RATIO = 2.0          # current APR > 2x its usual level...
SPIKE_MIN_PP = 5.0         # ...and at least 5 percentage points above it
TVL_DROP = -0.5            # TVL down 50%+ in 30 days
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
        self, http: HttpClient | None = None, sources: Iterable[str] | None = None, merge: bool = True,
        name_tokens: bool = True,
    ) -> None:
        self.http = http or HttpClient()
        self.merge = merge
        self.name_tokens = name_tokens
        self._history_checked: set[int] = set()
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

        if self.name_tokens:
            resolve_token_symbols(result.opportunities)  # free: symbols Merkl already reported
            resolve_reward_token_names(result.opportunities, self.http)
        result.opportunities = enrich(result.opportunities, merge=self.merge)
        return result

    def add_history(self, rows: list[Opportunity]) -> int:
        """Fetch TVL history for ``rows`` and re-flag / re-score them.

        Rows already checked by this analyzer are skipped.
        """
        rows = [o for o in rows if id(o) not in self._history_checked]
        self._history_checked.update(id(o) for o in rows)
        n = attach_history(rows, self.http)
        for o in rows:
            o.flags = risk_flags(o)
            o.score = score(o)
        return n

    def history_checked(self, o: Opportunity) -> bool:
        return id(o) in self._history_checked

    def scan(
        self, filters: Filters | None = None, sort: str = "score", limit: int | None = None,
        history: bool = True,
    ) -> ScanResult:
        result = self.collect()
        result.opportunities = select_with_history(
            self if history else None, result.opportunities, filters, sort, limit)
        return result


HISTORY_MIN_ROWS = 50
HISTORY_MAX_ROWS = 300  # one request per row; keeps a full export to ~300 requests


def select_with_history(
    analyzer: "Analyzer | None", opps: Iterable[Opportunity], filters: Filters | None = None,
    sort: str = "score", limit: int | None = None, history_limit: int = HISTORY_MAX_ROWS,
) -> list[Opportunity]:
    """Like :func:`select`, but first checks TVL history for the rows that would
    be shown and re-ranks them.

    The checked window is the top ``max(limit * 2, 50)`` rows, capped at
    ``history_limit`` (so exporting every market doesn't fetch ~1,500 charts).
    History flags only ever lower a score, so rows below the checked window
    can't overtake checked rows unfairly.
    """
    rows = select(opps, filters, sort)
    if analyzer is not None and rows and history_limit > 0:
        window = min(max((limit or len(rows)) * 2, HISTORY_MIN_ROWS), history_limit)
        analyzer.add_history(rows[:window])
        rows.sort(key=SORT_KEYS[sort], reverse=True)
    return rows[:limit] if limit else rows


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
    usual = baseline_apr(o)
    if usual is not None and o.total_apr > SPIKE_RATIO * usual and o.total_apr - usual >= SPIKE_MIN_PP:
        flags.append("apr_spike")
    change = o.extra.get("tvl_change_30d")
    if change is not None and change <= TVL_DROP:
        flags.append("tvl_drop")
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


def baseline_apr(o: Opportunity) -> float | None:
    """The market's usual APR: the median of its 30-day mean, its APR 30 days
    ago and its all-history mean (whichever the source provides).

    The median resists one distorted reference: after a pool empties, its
    30-day mean is already inflated, but the other two still show the old level.
    """
    refs = sorted(v for v in (o.apr_30d_mean, o.extra.get("apr_30d_ago"), o.extra.get("apr_hist_mean"))
                  if v is not None and v > 0)
    if not refs:
        return None
    mid = len(refs) // 2
    return refs[mid] if len(refs) % 2 else (refs[mid - 1] + refs[mid]) / 2


def score(o: Opportunity) -> float:
    """Risk-adjusted attractiveness, roughly 'APR you can trust'.

    * APR contribution is capped so absurd numbers do not dominate.
    * Depth: $1k TVL -> 0.05x weight, $1M -> 0.62x, $100M+ -> 1.0x (log scale).
    * Stability: penalize when current APR is far from its usual level
      (see :func:`baseline_apr`).
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

    usual = baseline_apr(o)
    if usual and o.total_apr > 0:
        ratio = min(o.total_apr, usual) / max(o.total_apr, usual)
        s *= 0.5 + 0.5 * ratio

    haircut = {"apr_outlier": 0.3, "low_tvl": 0.5, "il_risk": 0.85, "apr_spike": 0.8,
               "tvl_drop": 0.4, "unverified": 0.5, "net_negative": 0.0}
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
def _bucket_key(o: Opportunity, by: str) -> str:
    return str(getattr(o, by).value if by == "category" else getattr(o, by))


def summarize_with_history(
    analyzer: "Analyzer | None", opps: Iterable[Opportunity], by: str = "chain", top: int = 25,
    max_rounds: int = 25,
) -> list[dict]:
    """Like :func:`summarize`, but each shown group's "best market" has passed
    the TVL-history check.

    Repeats: find each group's best row; history-check the ones not yet
    checked; re-score. Flags only lower scores, so once every group's best has
    been checked (or has no history to check), it is the true best. Usually
    takes 1-3 rounds of at most one request per group.
    """
    opps = list(opps)
    if analyzer is None:
        return summarize(opps, by, top)
    # Group order (by USD/day) doesn't depend on history, so only shown groups need checking.
    shown = {r[by] for r in summarize(opps, by, top)}
    for _ in range(max_rounds):
        best: dict[str, Opportunity] = {}
        for o in opps:
            k = _bucket_key(o, by)
            if k in shown and (k not in best or o.score > best[k].score):
                best[k] = o
        pending = [o for o in best.values() if not analyzer.history_checked(o) and llama_pool_id(o)]
        if not pending:
            break
        analyzer.add_history(pending)
    return summarize(opps, by, top)


def summarize(opps: Iterable[Opportunity], by: str = "chain", top: int = 25) -> list[dict]:
    if by not in {"chain", "protocol", "category", "source"}:
        raise ValueError("by must be one of chain, protocol, category, source")
    buckets: dict[str, dict] = {}
    for o in opps:
        key = _bucket_key(o, by)
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
