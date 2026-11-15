"""Merge the same market reported twice into one row.

Two passes: :func:`find_matches` pairs DefiLlama and Merkl rows, then
:func:`collapse_identical` folds rows with identical numbers (e.g. one vault
listed by DefiLlama under two protocol names).

Pass 1: DefiLlama vs Merkl.

DefiLlama and Merkl name markets differently ("SIRLOINUSDC" vs "Supply to
Steakhouse High Yield USDC ... vault on Morpho"), so names alone can't be
compared. Two rows are treated as the same market only when *all* of these hold:

* same chain and same protocol family (``morpho`` == ``morpho-blue``);
* TVL within ``TVL_TOLERANCE`` of each other;
* they share tokens: every part of the DefiLlama symbol appears among Merkl's
  token symbols (Merkl lists vault share tokens such as ``sirloinUSDC``), or a
  DefiLlama underlying-token address appears among Merkl's token addresses.

Matching is one-to-one (closest TVL wins). The merged row keeps DefiLlama's
history-based fields (base APY, 30d mean, IL risk, stablecoin) and Merkl's
campaign fields (readable name, protocol app link, reward symbols, USD/day).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .models import Category, Opportunity

TVL_TOLERANCE = 0.05       # 5% relative TVL difference
REWARD_MISMATCH = 0.25     # flag when the two reward APRs differ by >25%


def _family(protocol: str) -> str:
    return protocol.split("-")[0]


def _tvl_gap(a: Opportunity, b: Opportunity) -> float | None:
    if not a.tvl_usd or not b.tvl_usd:
        return None
    return abs(a.tvl_usd - b.tvl_usd) / max(a.tvl_usd, b.tvl_usd)


def _shares_tokens(llama: Opportunity, merkl: Opportunity) -> bool:
    merkl_syms = {s.lower() for s in merkl.tokens}
    parts = {p.lower() for p in llama.market.split(" (")[0].split("-") if p}
    if parts and parts <= merkl_syms:
        return True
    llama_addrs = {t.lower() for t in llama.tokens if isinstance(t, str) and t.startswith("0x")}
    return bool(llama_addrs & set(merkl.token_addresses))


def find_matches(opps: list[Opportunity]) -> list[tuple[Opportunity, Opportunity]]:
    """Return (defillama, merkl) pairs that describe the same market."""
    merkl_by_key: dict[tuple[str, str], list[Opportunity]] = defaultdict(list)
    for o in opps:
        if o.source == "merkl":
            merkl_by_key[(o.chain, _family(o.protocol))].append(o)

    candidates: list[tuple[float, int, int, Opportunity, Opportunity]] = []
    for llama in opps:
        if llama.source != "defillama" or llama.category == Category.BORROWING:
            continue
        for merkl in merkl_by_key.get((llama.chain, _family(llama.protocol)), []):
            if merkl.category in (Category.BORROWING, Category.COLLATERAL):
                continue
            gap = _tvl_gap(llama, merkl)
            if gap is None or gap > TVL_TOLERANCE or not _shares_tokens(llama, merkl):
                continue
            candidates.append((gap, id(llama), id(merkl), llama, merkl))

    candidates.sort(key=lambda c: c[0])
    used: set[int] = set()
    pairs = []
    for _, lid, mid, llama, merkl in candidates:
        if lid in used or mid in used:
            continue
        used.update((lid, mid))
        pairs.append((llama, merkl))
    return pairs


def merge_pair(llama: Opportunity, merkl: Opportunity) -> Opportunity:
    rewards = [r for r in (llama.reward_apr, merkl.reward_apr) if r is not None]
    reward_apr = max(rewards) if rewards else None
    merged = replace(
        llama,
        source="defillama+merkl",
        source_id=f"{llama.source_id}|{merkl.source_id}",
        protocol=merkl.protocol if len(merkl.protocol) >= len(llama.protocol) else llama.protocol,
        market=merkl.market,
        category=merkl.category if merkl.category != Category.OTHER else llama.category,
        base_apr=llama.base_apr if llama.base_apr is not None else merkl.base_apr,
        reward_apr=reward_apr,
        reward_tokens=merkl.reward_tokens or llama.reward_tokens,
        daily_rewards_usd=merkl.daily_rewards_usd,
        url=merkl.url or llama.url,
        tokens=merkl.tokens or llama.tokens,
        token_addresses={**llama.token_addresses, **merkl.token_addresses},
        extra={
            **llama.extra,
            **merkl.extra,
            "merged_from": {
                "defillama": {"id": llama.source_id, "market": llama.market, "tvl_usd": llama.tvl_usd,
                              "base_apr": llama.base_apr, "reward_apr": llama.reward_apr, "url": llama.url},
                "merkl": {"id": merkl.source_id, "market": merkl.market, "tvl_usd": merkl.tvl_usd,
                          "base_apr": merkl.base_apr, "reward_apr": merkl.reward_apr, "url": merkl.url},
            },
        },
        flags=[],
        score=0.0,
    )
    if llama.reward_apr and merkl.reward_apr:
        hi, lo = max(llama.reward_apr, merkl.reward_apr), min(llama.reward_apr, merkl.reward_apr)
        if (hi - lo) / hi > REWARD_MISMATCH:
            merged.extra["reward_mismatch"] = True
    return merged


def merge_duplicates(opps: list[Opportunity]) -> list[Opportunity]:
    """Return a new list where matched DefiLlama/Merkl pairs become one row."""
    pairs = find_matches(opps)
    replaced = {id(l): merge_pair(l, m) for l, m in pairs}
    dropped = {id(m) for _, m in pairs}
    out = [replaced.get(id(o), o) for o in opps if id(o) not in dropped]
    return collapse_identical(out)


IDENTICAL_TVL = 0.005  # 0.5%
IDENTICAL_APR = 0.01   # percentage points
IDENTICAL_MIN_TVL = 50_000  # below this, equal numbers are coincidence (dust vaults)


def _token_ids(o: Opportunity) -> set[str]:
    ids = {t.lower() for t in o.tokens if isinstance(t, str)}
    ids |= set(o.token_addresses)
    return ids


def _richness(o: Opportunity) -> tuple:
    """Prefer merged rows, then rows with named reward tokens and a USD/day figure."""
    return ("+" in o.source, sum(not r.symbol.startswith("0x") for r in o.reward_tokens),
            o.daily_rewards_usd is not None, o.source == "merkl")


def collapse_identical(opps: list[Opportunity]) -> list[Opportunity]:
    """Fold rows that are the same market listed twice, possibly by the same
    source under two protocol names (DefiLlama lists some vaults under both
    the curator and the vault protocol): same chain and type, TVL within 0.5%,
    identical base and reward APR, and at least one shared token. Never folds
    two Merkl rows (Merkl lists each market once) or markets under $50k TVL,
    where identical numbers are usually coincidence."""
    buckets: dict[tuple, list[Opportunity]] = defaultdict(list)
    for o in opps:
        if o.tvl_usd and o.tvl_usd >= IDENTICAL_MIN_TVL and o.reward_apr is not None:
            buckets[(o.chain, o.category, round(o.reward_apr, 1))].append(o)

    drop: set[int] = set()
    for group in buckets.values():
        if len(group) < 2:
            continue
        group.sort(key=_richness, reverse=True)
        for i, keep in enumerate(group):
            if id(keep) in drop:
                continue
            for other in group[i + 1:]:
                if id(other) in drop:
                    continue
                # Merkl lists each market once; two Merkl rows are different markets.
                if "defillama" not in keep.source and "defillama" not in other.source:
                    continue
                if keep.source == "merkl" and other.source == "merkl":
                    continue
                same = (
                    _tvl_gap(keep, other) is not None and _tvl_gap(keep, other) <= IDENTICAL_TVL
                    and abs((keep.base_apr or 0) - (other.base_apr or 0)) <= IDENTICAL_APR
                    and abs((keep.reward_apr or 0) - (other.reward_apr or 0)) <= IDENTICAL_APR
                    and _token_ids(keep) & _token_ids(other)
                )
                if same:
                    drop.add(id(other))
                    keep.extra.setdefault("duplicates", []).append(
                        {"source": other.source, "protocol": other.protocol, "market": other.market, "url": other.url}
                    )
    return [o for o in opps if id(o) not in drop]
