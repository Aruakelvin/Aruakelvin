"""Canonicalization helpers so that the same chain / protocol from different
sources compares equal."""

from __future__ import annotations

import re

from .models import Category

_CHAIN_ALIASES = {
    "eth": "ethereum", "mainnet": "ethereum", "ethereum mainnet": "ethereum",
    "arbitrum one": "arbitrum", "arb": "arbitrum",
    "op mainnet": "optimism", "op": "optimism",
    "bsc": "bsc", "bnb": "bsc", "bnb chain": "bsc", "binance": "bsc", "bnb smart chain": "bsc",
    "matic": "polygon", "polygon pos": "polygon",
    "avax": "avalanche", "avalanche c-chain": "avalanche",
    "zksync era": "zksync", "zksync": "zksync", "era": "zksync",
    "polygon zkevm": "polygon-zkevm", "polygonzkevm": "polygon-zkevm",
    "xdai": "gnosis", "gnosis chain": "gnosis",
    "hyperliquid l1": "hyperliquid", "hyperevm": "hyperliquid",
    "sonic mainnet": "sonic",
}

# EVM chain ids -> canonical names (used by Merkl, which keys on chainId).
CHAIN_IDS = {
    1: "ethereum", 10: "optimism", 25: "cronos", 56: "bsc", 100: "gnosis", 130: "unichain",
    137: "polygon", 146: "sonic", 250: "fantom", 252: "fraxtal", 324: "zksync", 1101: "polygon-zkevm",
    1284: "moonbeam", 1329: "sei", 1868: "soneium", 2741: "abstract", 5000: "mantle", 8453: "base",
    9745: "plasma", 34443: "mode", 42161: "arbitrum", 42220: "celo", 43114: "avalanche",
    48900: "zircuit", 57073: "ink", 59144: "linea", 60808: "bob", 80094: "berachain",
    81457: "blast", 167000: "taiko", 534352: "scroll", 999: "hyperliquid", 747474: "katana",
    1923: "swellchain", 480: "worldchain", 1135: "lisk", 42793: "etherlink", 14: "flare",
    239: "tac", 98866: "plume", 143: "monad",
}


def canon_chain(name: str | int | None) -> str:
    if name is None:
        return "unknown"
    if isinstance(name, int):
        return CHAIN_IDS.get(name, f"chain-{name}")
    key = str(name).strip().lower()
    return _CHAIN_ALIASES.get(key, key.replace(" ", "-"))


def canon_protocol(name: str | None) -> str:
    if not name:
        return "unknown"
    s = name.strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    return re.sub(r"[^a-z0-9.\-]", "", s)


# DefiLlama protocol categories -> our categories.
_LLAMA_CATEGORY = {
    "dexs": Category.LP, "dexes": Category.LP, "dex": Category.LP,
    # DefiLlama pools are deposits; on trading venues that means LP-ing (GLP/GLV/HLP style vaults).
    "derivatives": Category.LP, "options": Category.LP, "perps": Category.LP,
    "options vault": Category.STAKING, "prediction market": Category.LP,
    "lending": Category.LENDING, "cdp": Category.LENDING, "nft lending": Category.LENDING,
    "uncollateralized lending": Category.LENDING, "rwa lending": Category.LENDING,
    "liquid staking": Category.STAKING, "liquid restaking": Category.STAKING, "restaking": Category.STAKING,
    "staking pool": Category.STAKING, "yield": Category.STAKING, "yield aggregator": Category.STAKING,
    "leveraged farming": Category.LP, "farm": Category.LP, "liquidity manager": Category.LP,
    "basis trading": Category.STAKING, "rwa": Category.HOLDING, "synthetics": Category.LP,
    "algo-stables": Category.HOLDING, "cross chain": Category.LP, "bridge": Category.LP,
    "cross chain bridge": Category.LP, "canonical bridge": Category.LP, "bridge aggregator": Category.LP,
    "dex aggregator": Category.LP, "perps aggregator": Category.LP, "trading app": Category.LP,
    "liquidity automation": Category.LP, "risk curators": Category.LENDING, "onchain capital allocator": Category.STAKING,
    "reserve currency": Category.STAKING, "governance incentives": Category.STAKING, "cedefi": Category.STAKING,
    "indexes": Category.HOLDING, "insurance": Category.STAKING, "launchpad": Category.STAKING,
}


def category_from_llama(protocol_category: str | None, exposure: str | None, symbol: str) -> Category:
    if protocol_category:
        cat = _LLAMA_CATEGORY.get(protocol_category.strip().lower())
        if cat:
            return cat
    if exposure == "multi" or "-" in symbol or "/" in symbol:
        return Category.LP
    return Category.OTHER


# Merkl "action" / "type" values -> our categories.
_MERKL_ACTION = {
    "pool": Category.LP, "lp": Category.LP, "clamm": Category.LP,
    "swap": Category.TRADING, "trade": Category.TRADING, "trading": Category.TRADING, "perp": Category.TRADING,
    "lend": Category.LENDING, "supply": Category.LENDING,
    "borrow": Category.BORROWING,
    "hold": Category.HOLDING, "drop": Category.HOLDING,
    "stake": Category.STAKING, "vault": Category.STAKING,
}


def is_collateral_campaign(type_: str | None, name: str | None) -> bool:
    """Rewards for *posting collateral* (Morpho/Fluid/... collateral campaigns).

    Excludes "borrow from collateral" campaigns, which reward borrowing.
    """
    t = (type_ or "").upper()
    if "COLLATERAL" in t and "BORROW" not in t:
        return True
    return bool(re.search(r"\bas collateral\b", (name or "").lower()))


def category_from_merkl(action: str | None, type_: str | None, name: str | None = None) -> Category:
    if is_collateral_campaign(type_, name):
        return Category.COLLATERAL
    for value in (action, type_):
        if not value:
            continue
        v = value.strip().lower()
        if v in _MERKL_ACTION:
            return _MERKL_ACTION[v]
        for key, cat in _MERKL_ACTION.items():
            if key in v:
                return cat
    return Category.OTHER


def to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return f
