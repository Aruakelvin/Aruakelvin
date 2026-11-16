"""Estimate LP trading-fee yield from GeckoTerminal pool data.

Merkl reports reward APR for concentrated-liquidity pools but often no fee
yield (``nativeApr``), so their Total% understates what LPs earn. GeckoTerminal
(``api.geckoterminal.com``, free, no key) has per-pool 24h volume, fee tier and
liquidity, from which::

    fee APR ≈ volume_24h × fee% ÷ liquidity × 365

Deliberately narrow:

* Only Merkl LP rows whose ``identifier`` is a DEX pool address (Uniswap V3/V4,
  PancakeSwap, SushiSwap, QuickSwap, HyperSwap ...) and that have no base APR.
* Never ve(3,3) DEXs (Aerodrome, Velodrome ...): their fees go to voters, not LPs.
* Dynamic-fee pools (no fixed fee tier, e.g. Uniswap V4 hooks) get their volume
  recorded and the ``fee_unknown`` flag, not a guessed fee.
* It's an average over all liquidity: in-range positions earn more, out-of-range
  ones nothing. 24h volume can also swing a lot day to day.

The free API allows roughly 8 requests a minute, so pools are batched per
network (``/pools/multi/``, up to 30 addresses) and fetched only for shown rows.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable, Iterable

from .http import HttpClient, HttpError
from .models import Category, Opportunity
from .normalize import to_float

log = logging.getLogger(__name__)

API = "https://api.geckoterminal.com/api/v2"
BATCH = 30
CACHE_TTL = 3600
RATE_LIMIT_WAIT_S = 30

# Merkl campaign types whose identifier is the pool address / V4 pool id.
POOL_TYPES = {
    "UNISWAP_V3", "UNISWAP_V4", "UNISWAP_V4_SUBSCRIPTION", "PANCAKESWAP", "SUSHI_SWAP",
    "QUICKSWAP", "QUICKSWAP_ALGEBRA_12", "HYPERSWAP", "PROJECT_X", "KYBERSWAP", "CAMELOT",
}
# ve(3,3) DEXs: LP fees go to voters, so a fee estimate would be wrong.
VE33_HINTS = ("aero", "velo", "pharaoh", "ramses", "shadow", "thena", "equalizer", "blackhole")

# canonical chain name -> GeckoTerminal network id
NETWORKS = {
    "ethereum": "eth", "base": "base", "arbitrum": "arbitrum", "optimism": "optimism", "bsc": "bsc",
    "polygon": "polygon_pos", "avalanche": "avax", "gnosis": "xdai", "monad": "monad",
    "robinhood-chain": "robinhood", "hyperliquid": "hyperevm", "sonic": "sonic", "unichain": "unichain",
    "linea": "linea", "scroll": "scroll", "mantle": "mantle", "berachain": "berachain", "katana": "katana",
    "hemi": "hemi", "plasma": "plasma", "sei": "sei-evm", "zksync": "zksync", "celo": "celo", "ink": "ink",
    "soneium": "soneium", "worldchain": "world-chain", "abstract": "abstract", "fraxtal": "fraxtal",
    "mode": "mode", "taiko": "taiko", "citrea": "citrea", "fluent": "fluent", "plume": "plume-network",
    "flare": "flare", "immutable": "immutable-zkevm", "lisk": "lisk", "etherlink": "etherlink",
    "tac": "tac", "megaeth": "megaeth", "arc": "arc",
}


def candidate(o: Opportunity) -> tuple[str, str] | None:
    """(GeckoTerminal network, pool address) if this row qualifies for an estimate."""
    if "merkl" not in o.source or o.category != Category.LP or o.base_apr is not None:
        return None
    if str(o.extra.get("type") or "").upper() not in POOL_TYPES:
        return None
    text = f"{o.protocol} {o.extra.get('type')} {o.market}".lower()
    if any(h in text for h in VE33_HINTS):
        return None
    network, ident = NETWORKS.get(o.chain), str(o.extra.get("identifier") or "")
    if not network or not ident.startswith("0x") or len(ident) not in (42, 66):
        return None
    return network, ident.lower()


def fee_apr(volume_24h: float | None, fee_pct: float | None, liquidity: float | None) -> float | None:
    if not volume_24h or fee_pct is None or not liquidity or liquidity <= 0:
        return None
    return volume_24h * fee_pct / liquidity * 365


def attach_fee_estimates(
    opps: Iterable[Opportunity], http: HttpClient, sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Set ``base_apr`` from a fee estimate where possible. Returns how many
    rows got an estimate. Rate-limited or failed lookups are skipped."""
    by_network: dict[str, dict[str, list[Opportunity]]] = defaultdict(lambda: defaultdict(list))
    for o in opps:
        if "gecko_checked" in o.extra:
            continue
        c = candidate(o)
        if c:
            by_network[c[0]][c[1]].append(o)
    estimated = 0
    for network, pools in by_network.items():
        addrs = list(pools)
        for i in range(0, len(addrs), BATCH):
            chunk = addrs[i:i + BATCH]
            data = _fetch(http, network, chunk, sleep)
            for o in (o for a in chunk for o in pools[a]):
                o.extra["gecko_checked"] = data is not None
            for a in data or []:
                attrs = a.get("attributes") or {}
                addr = str(attrs.get("address") or "").lower()
                vol = to_float((attrs.get("volume_usd") or {}).get("h24"))
                fee = to_float(attrs.get("pool_fee_percentage"))
                liq = to_float(attrs.get("reserve_in_usd"))
                for o in pools.get(addr, []):
                    o.extra.update({"volume_usd_1d": vol, "pool_liquidity_usd": liq, "pool_fee_pct": fee})
                    est = fee_apr(vol, fee, liq)
                    if est is not None:
                        o.base_apr = round(est, 4)
                        o.extra["base_apr_estimated"] = True
                        estimated += 1
                    elif vol:
                        o.extra["fee_unknown"] = True  # volume known, fee tier isn't (dynamic fee)
    return estimated


def _fetch(http: HttpClient, network: str, addrs: list[str], sleep: Callable[[float], None]):
    url = f"{API}/networks/{network}/pools/multi/{','.join(addrs)}"
    for attempt in range(2):
        try:
            d = http.get_json(url, ttl=CACHE_TTL)
            return d.get("data") if isinstance(d, dict) else None
        except HttpError as exc:
            rate_limited = "429" in str(exc) or "attempts" in str(exc)  # http.py retries 429s, then gives up
            if attempt == 0 and rate_limited:
                log.debug("geckoterminal rate-limited; waiting %ss", RATE_LIMIT_WAIT_S)
                sleep(RATE_LIMIT_WAIT_S)
                continue
            log.debug("geckoterminal %s failed: %s", network, exc)
            return None
    return None
