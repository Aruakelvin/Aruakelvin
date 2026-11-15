"""DefiLlama Yields: ~15k+ pools across 400+ protocols and 100+ chains.

Endpoints used (all public, no key):
  * https://yields.llama.fi/pools        - supply side: apyBase / apyReward per pool
  * https://yields.llama.fi/lendBorrow   - borrow side: apyRewardBorrow per lending pool
  * https://api.llama.fi/protocols       - protocol -> category (Dexs, Lending, ...)
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from ..http import HttpError
from ..models import Category, Opportunity, RewardToken
from ..normalize import canon_chain, canon_protocol, category_from_llama, to_float
from .base import Source

log = logging.getLogger(__name__)

POOLS_URL = "https://yields.llama.fi/pools"
LEND_BORROW_URL = "https://yields.llama.fi/lendBorrow"
PROTOCOLS_URL = "https://api.llama.fi/protocols"
POOL_PAGE = "https://defillama.com/yields/pool/{pool}"


class DefiLlamaSource(Source):
    name = "defillama"
    description = "DefiLlama Yields (pool rewards + lending borrow-side rewards)"

    def _protocol_categories(self) -> dict[str, str]:
        try:
            protocols = self.http.get_json(PROTOCOLS_URL)
        except HttpError as exc:
            log.warning("defillama: protocol categories unavailable (%s); using heuristics", exc)
            return {}
        out: dict[str, str] = {}
        for p in protocols or []:
            slug, cat = p.get("slug"), p.get("category")
            if slug and cat:
                out[slug] = cat
        return out

    def fetch(self) -> Iterable[Opportunity]:
        payload = self.http.get_json(POOLS_URL)
        pools = payload.get("data", payload) if isinstance(payload, dict) else payload
        categories = self._protocol_categories()

        by_pool: dict[str, dict] = {}
        for p in pools or []:
            pool_id = p.get("pool")
            if pool_id:
                by_pool[pool_id] = p
            reward_apr = to_float(p.get("apyReward"))
            if not reward_apr or reward_apr <= 0:
                continue  # we only care about incentivized markets
            yield self._to_opportunity(p, categories)

        # Borrow-side incentives (e.g. Aave/Compound/Morpho borrower rewards).
        try:
            borrow_rows = self.http.get_json(LEND_BORROW_URL)
        except HttpError as exc:
            log.warning("defillama: lendBorrow unavailable (%s)", exc)
            return
        for row in borrow_rows or []:
            reward = to_float(row.get("apyRewardBorrow"))
            if not reward or reward <= 0:
                continue
            base_pool = by_pool.get(row.get("pool"), {})
            symbol = base_pool.get("symbol") or row.get("symbol") or "?"
            base_borrow = to_float(row.get("apyBaseBorrow"))
            yield Opportunity(
                source=self.name,
                source_id=f"{row.get('pool')}:borrow",
                chain=canon_chain(base_pool.get("chain") or row.get("chain")),
                protocol=canon_protocol(base_pool.get("project") or row.get("project")),
                market=f"Borrow {symbol}",
                category=Category.BORROWING,
                tvl_usd=to_float(row.get("totalBorrowUsd")),
                # Borrowing *costs* base interest; express it as negative yield.
                base_apr=-base_borrow if base_borrow is not None else None,
                reward_apr=reward,
                reward_tokens=[RewardToken(symbol=_short(a), address=a) for a in (row.get("rewardTokens") or [])],
                stablecoin=base_pool.get("stablecoin"),
                url=POOL_PAGE.format(pool=row.get("pool")),
                tokens=list(base_pool.get("underlyingTokens") or []),
                extra={"ltv": row.get("ltv"), "totalSupplyUsd": row.get("totalSupplyUsd")},
            )

    def _to_opportunity(self, p: dict, categories: dict[str, str]) -> Opportunity:
        project = p.get("project") or ""
        symbol = p.get("symbol") or "?"
        meta = p.get("poolMeta")
        market = f"{symbol} ({meta})" if meta else symbol
        return Opportunity(
            source=self.name,
            source_id=str(p.get("pool")),
            chain=canon_chain(p.get("chain")),
            protocol=canon_protocol(project),
            market=market,
            category=category_from_llama(categories.get(project), p.get("exposure"), symbol),
            tvl_usd=to_float(p.get("tvlUsd")),
            base_apr=to_float(p.get("apyBase")),
            reward_apr=to_float(p.get("apyReward")),
            reward_tokens=[RewardToken(symbol=_short(a), address=a) for a in (p.get("rewardTokens") or [])],
            apr_30d_mean=to_float(p.get("apyMean30d")),
            stablecoin=p.get("stablecoin"),
            il_risk=(p.get("ilRisk") == "yes") if p.get("ilRisk") else None,
            url=POOL_PAGE.format(pool=p.get("pool")),
            tokens=list(p.get("underlyingTokens") or []),
            extra={
                "exposure": p.get("exposure"),
                "outlier": p.get("outlier"),
                "volume_usd_1d": to_float(p.get("volumeUsd1d")),
                "apy_pct_7d": to_float(p.get("apyPct7D")),
                "prediction": (p.get("predictions") or {}).get("predictedClass"),
            },
        )


def _short(addr: str) -> str:
    """DefiLlama gives reward tokens as addresses; shorten for display."""
    if isinstance(addr, str) and addr.startswith("0x") and len(addr) > 12:
        return f"{addr[:6]}…{addr[-4:]}"
    return str(addr)
