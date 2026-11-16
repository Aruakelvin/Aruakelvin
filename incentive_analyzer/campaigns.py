"""When incentives end, and whether they tend to be renewed.

Merkl reports each market's latest campaign end (``latestCampaignEnd``). About
half of all live campaigns end within a week, but many are weekly or
fortnightly programs that get topped up back-to-back. So "ends soon" alone is
noise; what matters is "ends soon *and* has no record of being renewed".

The renewal record comes from ``api.merkl.xyz/v4/campaigns?opportunityId=…``,
one request per market, fetched only for rows a scan shows that end within
``ENDING_SOON_DAYS``.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from .http import HttpClient, HttpError
from .models import Opportunity
from .normalize import to_float

log = logging.getLogger(__name__)

CAMPAIGNS_URL = "https://api.merkl.xyz/v4/campaigns"
ENDING_SOON_DAYS = 7
RENEWAL_GAP_S = 2 * 86400   # a follow-up campaign starting within 2 days of the last one counts as a renewal
CAMPAIGNS_CACHE_TTL = 3600


def days_left(o: Opportunity, now: float | None = None) -> float | None:
    """Days until the market's last live campaign ends (Merkl rows only)."""
    return o.days_left(now)


def merkl_id(o: Opportunity) -> str | None:
    if o.source == "merkl":
        return o.source_id
    merged = (o.extra.get("merged_from") or {}).get("merkl") or {}
    return merged.get("id")


def count_renewals(campaigns: list[dict], now: float | None = None) -> int:
    """How many times the program was renewed back-to-back before the
    current campaign: walk back from the latest start through campaigns that
    ended within ``RENEWAL_GAP_S`` of the next one's start."""
    spans = sorted(
        (s, e) for c in campaigns
        if (s := to_float(c.get("startTimestamp"))) is not None
        and (e := to_float(c.get("endTimestamp"))) is not None
    )
    if not spans:
        return 0
    now = time.time() if now is None else now
    started = [sp for sp in spans if sp[0] <= now] or spans
    renewals = 0
    next_start = started[-1][0]
    for start, end in reversed(started[:-1]):
        if 0 <= next_start - end <= RENEWAL_GAP_S or start < next_start <= end:
            renewals += 1
            next_start = start
        elif end < next_start - RENEWAL_GAP_S:
            break
    return renewals


def attach_renewals(opps: Iterable[Opportunity], http: HttpClient, workers: int = 8,
                    now: float | None = None) -> int:
    """For rows ending within ``ENDING_SOON_DAYS``, fetch campaign history and
    set ``extra['renewals']``. Returns how many rows were checked."""
    targets = []
    for o in opps:
        left, mid = days_left(o, now), merkl_id(o)
        if mid and left is not None and left <= ENDING_SOON_DAYS and "renewals" not in o.extra:
            targets.append((o, mid))
    if not targets:
        return 0

    def fetch(mid: str):
        try:
            rows = http.get_json(CAMPAIGNS_URL, {"opportunityId": mid, "items": 50}, ttl=CAMPAIGNS_CACHE_TTL)
        except HttpError as exc:
            log.debug("campaign history for %s unavailable: %s", mid, exc)
            return None
        return rows if isinstance(rows, list) else None

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for (o, _), rows in zip(targets, pool.map(fetch, [m for _, m in targets])):
            if rows is None:
                continue
            o.extra["renewals"] = count_renewals(rows, now)
            done += 1
    return done
