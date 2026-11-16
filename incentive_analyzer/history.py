"""TVL history for DefiLlama-backed rows (``yields.llama.fi/chart/{pool}``).

A high APR is often not a richer reward but an *emptier pool*: when liquidity
leaves and emissions stay the same, the APR multiplies. Spotting that needs TVL
history, which the bulk ``/pools`` endpoint doesn't include. It costs one
request per pool, so it is fetched only for the rows a scan will show.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from .http import HttpClient, HttpError
from .models import Opportunity
from .normalize import to_float

log = logging.getLogger(__name__)

CHART_URL = "https://yields.llama.fi/chart/{pool}"
WINDOW_DAYS = 30


def llama_pool_id(o: Opportunity) -> str | None:
    """The DefiLlama pool id behind a row, if any (borrow rows excluded)."""
    if "defillama" not in o.source:
        return None
    pid = o.extra.get("llama_pool")
    if pid:
        return pid
    merged = (o.extra.get("merged_from") or {}).get("defillama") or {}
    pid = merged.get("id") or (o.source_id if o.source == "defillama" else None)
    if not pid or ":" in str(pid):  # ":borrow" rows use the supply pool's chart
        return None
    return str(pid)


def tvl_change(points: list[dict], days: int = WINDOW_DAYS) -> tuple[float | None, float | None]:
    """Return (tvl_then, fractional change since then) from chart points."""
    if not points:
        return None, None
    parsed = []
    for p in points:
        try:
            ts = datetime.fromisoformat(str(p["timestamp"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        tvl = to_float(p.get("tvlUsd"))
        if tvl is not None:
            parsed.append((ts, tvl))
    if len(parsed) < 2:
        return None, None
    parsed.sort()
    now_ts, now_tvl = parsed[-1]
    cutoff = now_ts - timedelta(days=days)
    then = [tvl for ts, tvl in parsed if ts <= cutoff]
    if not then or then[-1] <= 0:
        return None, None  # pool younger than the window
    return then[-1], now_tvl / then[-1] - 1.0


def attach_history(opps: Iterable[Opportunity], http: HttpClient, workers: int = 8) -> int:
    """Fetch TVL history for each row and store it in ``extra``.

    Sets ``extra['tvl_30d_ago']`` and ``extra['tvl_change_30d']`` (fraction,
    -0.9 = down 90%). Returns how many rows got history. Failures are logged and
    skipped: history only ever adds a warning, so missing it is safe.
    """
    targets = [(o, pid) for o in opps if (pid := llama_pool_id(o))]
    if not targets:
        return 0

    def fetch(pid: str):
        try:
            data = http.get_json(CHART_URL.format(pool=pid))
        except HttpError as exc:
            log.debug("history for %s unavailable: %s", pid, exc)
            return None
        return data.get("data") if isinstance(data, dict) else data

    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for (o, _), points in zip(targets, pool.map(fetch, [p for _, p in targets])):
            then, change = tvl_change(points or [])
            if change is None:
                continue
            o.extra["tvl_30d_ago"] = then
            o.extra["tvl_change_30d"] = change
            done += 1
    return done

