"""Merkl: the main off-chain incentive distributor used by Uniswap, Aerodrome,
Morpho, Euler, Pendle, Curve, Balancer and hundreds of other protocols on 40+
chains. Covers LP, lending, borrowing, holding and swap/trading campaigns.

Endpoint: https://api.merkl.xyz/v4/opportunities (public, paginated).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from ..models import Opportunity, RewardToken
from ..normalize import canon_chain, canon_protocol, category_from_merkl, to_float
from .base import Source

log = logging.getLogger(__name__)

OPPORTUNITIES_URL = "https://api.merkl.xyz/v4/opportunities"
APP_URL = "https://app.merkl.xyz/opportunities/{chain}/{type}/{identifier}"


class MerklSource(Source):
    name = "merkl"
    description = "Merkl live incentive campaigns (LP, lend, borrow, hold, swap)"

    page_size = 100
    max_pages = 200  # hard stop: 20k opportunities

    def fetch(self) -> Iterable[Opportunity]:
        for page in range(self.max_pages):
            rows = self.http.get_json(
                OPPORTUNITIES_URL, {"status": "LIVE", "items": self.page_size, "page": page}
            )
            if isinstance(rows, dict):  # tolerate wrapped responses
                rows = rows.get("data") or rows.get("opportunities") or []
            if not rows:
                return
            for row in rows:
                opp = self._to_opportunity(row)
                if opp is not None:
                    yield opp
            if len(rows) < self.page_size:
                return
        log.warning("merkl: stopped after %d pages", self.max_pages)

    def _to_opportunity(self, r: dict) -> Opportunity | None:
        apr = to_float(r.get("apr"))
        daily = to_float(r.get("dailyRewards"))
        if not apr and not daily:
            return None

        chain_obj = r.get("chain") or {}
        chain = canon_chain(chain_obj.get("name")) if chain_obj.get("name") else canon_chain(r.get("chainId"))
        proto_obj = r.get("protocol") or {}
        protocol = canon_protocol(proto_obj.get("id") or proto_obj.get("name") or r.get("mainProtocol"))

        reward_tokens: list[RewardToken] = []
        seen: set[str] = set()
        for b in ((r.get("rewardsRecord") or {}).get("breakdowns") or []):
            tok = b.get("token") or {}
            sym = tok.get("symbol") or "?"
            if sym in seen:
                continue
            seen.add(sym)
            reward_tokens.append(RewardToken(symbol=sym, address=tok.get("address"), daily_usd=to_float(b.get("value"))))

        url = r.get("depositUrl")
        if not url and r.get("identifier"):
            url = APP_URL.format(
                chain=(chain_obj.get("name") or chain).lower(),
                type=str(r.get("type", "")).lower(),
                identifier=r.get("identifier"),
            )

        return Opportunity(
            source=self.name,
            source_id=str(r.get("id") or r.get("identifier")),
            chain=chain,
            protocol=protocol,
            market=r.get("name") or r.get("identifier") or "?",
            category=category_from_merkl(r.get("action"), r.get("type")),
            tvl_usd=to_float(r.get("tvl")),
            base_apr=None,  # Merkl reports incentive APR only
            reward_apr=apr,
            reward_tokens=reward_tokens,
            daily_rewards_usd=daily,
            url=url,
            tokens=[t.get("symbol") for t in (r.get("tokens") or []) if t.get("symbol")],
            extra={"type": r.get("type"), "action": r.get("action"), "tags": r.get("tags")},
        )
