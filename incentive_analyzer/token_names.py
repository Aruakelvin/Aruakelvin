"""Name reward tokens that a source reports only as contract addresses.

DefiLlama lists reward tokens by address (``0x9401…8631``). Symbols that Merkl
already reported for the same chain are applied first, for free (see
``analyzer.resolve_token_symbols``); the rest are looked up one by one via
``api.merkl.xyz/v4/tokens?chainId=…&address=…``. Token symbols don't change,
so lookups are cached for a week.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from .http import HttpClient, HttpError
from .models import Opportunity
from .normalize import CHAIN_IDS

log = logging.getLogger(__name__)

TOKENS_URL = "https://api.merkl.xyz/v4/tokens"
SYMBOL_CACHE_TTL = 7 * 24 * 3600


def _chain_ids(opps: list[Opportunity]) -> dict[str, int]:
    """Canonical chain name -> EVM chain id, extended with ids Merkl reported."""
    ids = {name: cid for cid, name in CHAIN_IDS.items()}
    for o in opps:
        cid = o.extra.get("chain_id")
        if isinstance(cid, int):
            ids.setdefault(o.chain, cid)
    return ids


def _unnamed(symbol: str) -> bool:
    return symbol.startswith("0x") or "…" in symbol


def resolve_reward_token_names(opps: list[Opportunity], http: HttpClient, workers: int = 8) -> int:
    """Replace address-only reward token symbols in place. Returns how many
    distinct tokens were named. Lookups that fail are skipped."""
    ids = _chain_ids(opps)
    wanted: set[tuple[str, str]] = set()
    for o in opps:
        for r in o.reward_tokens:
            if r.address and r.address.startswith("0x") and _unnamed(r.symbol) and o.chain in ids:
                wanted.add((o.chain, r.address.lower()))
    if not wanted:
        return 0

    def fetch(key: tuple[str, str]) -> str | None:
        chain, addr = key
        try:
            rows = http.get_json(TOKENS_URL, {"chainId": ids[chain], "address": addr}, ttl=SYMBOL_CACHE_TTL)
        except HttpError as exc:
            log.debug("token lookup %s:%s failed: %s", chain, addr, exc)
            return None
        for t in rows if isinstance(rows, list) else []:
            if str(t.get("address", "")).lower() == addr and t.get("symbol"):
                return t.get("displaySymbol") or t["symbol"]
        return None

    keys = sorted(wanted)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        names = dict(zip(keys, pool.map(fetch, keys)))

    for o in opps:
        for r in o.reward_tokens:
            if r.address and _unnamed(r.symbol):
                sym = names.get((o.chain, r.address.lower()))
                if sym:
                    r.symbol = sym
    return sum(1 for v in names.values() if v)
