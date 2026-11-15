"""Command-line interface: ``incentives scan | summary | sources``."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, report
from .analyzer import SORT_KEYS, Analyzer, Filters, select, summarize
from .http import DEFAULT_CACHE_DIR, HttpClient
from .models import Category
from .sources import REGISTRY


def _csv(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _common(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("filters")
    g.add_argument("-c", "--chain", type=_csv, default=[], help="comma list, e.g. ethereum,base,arbitrum")
    g.add_argument("-p", "--protocol", type=_csv, default=[], help="comma list, e.g. aave-v3,uniswap-v3,aerodrome")
    g.add_argument("-t", "--type", dest="categories", type=_csv, default=[],
                   help=f"comma list of: {', '.join(c.value for c in Category)}")
    g.add_argument("--token", help="asset you deposit, matched in the market name / deposit tokens (e.g. USDC)")
    g.add_argument("--reward-token", help="asset the rewards are paid in (e.g. MORPHO, AERO, OP)")
    g.add_argument("--min-tvl", type=float, default=0.0, help="minimum TVL in USD (default 0)")
    g.add_argument("--min-reward-apr", type=float, default=0.0, help="minimum incentive APR %% (default 0)")
    g.add_argument("--max-apr", type=float, help="drop markets above this total APR %%")
    g.add_argument("--min-daily-rewards", type=float, default=0.0, help="minimum USD rewards emitted per day")
    g.add_argument("--stable", action="store_true", help="stablecoin-only markets")
    g.add_argument("--safe", action="store_true", help="exclude apr_outlier, low_tvl and net_negative markets")
    s = p.add_argument_group("data")
    s.add_argument("-s", "--source", type=_csv, default=[], help=f"sources to use (default all: {', '.join(REGISTRY)})")
    s.add_argument("--no-merge", action="store_true",
                   help="keep DefiLlama and Merkl rows for the same market separate")
    s.add_argument("--cache-ttl", type=int, default=600, help="seconds to reuse cached API responses (0 disables)")
    s.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    s.add_argument("--timeout", type=float, default=45.0)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="incentives",
        description="Find incentivized LP, trading, lending, borrowing and staking markets across chains and protocols.",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("-v", "--verbose", action="count", default=0)
    sub = ap.add_subparsers(dest="cmd", required=True)

    scan = sub.add_parser("scan", help="list matching opportunities")
    _common(scan)
    scan.add_argument("--sort", choices=list(SORT_KEYS), default="score")
    scan.add_argument("-n", "--limit", type=int, default=50, help="rows to show (0 = all)")
    scan.add_argument("-f", "--format", choices=["table", "json", "csv", "md", "html"], default="table")
    scan.add_argument("-o", "--output", type=Path, help="write to file instead of stdout")

    summ = sub.add_parser("summary", help="aggregate incentives by chain / protocol / type / source")
    _common(summ)
    summ.add_argument("--by", choices=["chain", "protocol", "category", "source"], default="chain")
    summ.add_argument("-n", "--limit", type=int, default=25)

    sub.add_parser("sources", help="list available data sources")
    return ap


def _filters(args: argparse.Namespace) -> Filters:
    try:
        cats = [Category(c.lower()) for c in args.categories]
    except ValueError as exc:
        raise SystemExit(f"error: {exc}; valid types: {', '.join(c.value for c in Category)}") from None
    return Filters(
        chains=args.chain, protocols=args.protocol, categories=cats, token=args.token, reward_token=args.reward_token,
        min_tvl=args.min_tvl, min_reward_apr=args.min_reward_apr, max_apr=args.max_apr,
        min_daily_rewards=args.min_daily_rewards, stablecoin_only=args.stable,
        exclude_flags=("apr_outlier", "low_tvl", "net_negative") if args.safe else (),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING - 10 * min(args.verbose, 2), format="%(levelname)s %(name)s: %(message)s")

    if args.cmd == "sources":
        for name, cls in REGISTRY.items():
            print(f"{name:12} {cls.description}")
        return 0

    http = HttpClient(cache_dir=args.cache_dir, cache_ttl=args.cache_ttl, timeout=args.timeout)
    try:
        analyzer = Analyzer(http, args.source or None, merge=not args.no_merge)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not args.verbose:
        print("Fetching incentive data…", file=sys.stderr)
    collected = analyzer.collect()
    for name, err in collected.errors.items():
        print(f"warning: source '{name}' failed: {err}", file=sys.stderr)
    if not collected.source_counts:
        print("error: no source returned data", file=sys.stderr)
        return 1
    counts = ", ".join(f"{k}={v}" for k, v in collected.source_counts.items())
    print(f"Collected {len(collected.opportunities)} incentivized markets ({counts})", file=sys.stderr)


    filters = _filters(args)
    if args.cmd == "summary":
        matched = select(collected.opportunities, filters)
        print(report.summary_table(summarize(matched, by=args.by, top=args.limit), args.by))
        return 0

    rows = select(collected.opportunities, filters, args.sort, args.limit or None)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": collected.source_counts,
        "errors": collected.errors,
        "filters": {k: v for k, v in vars(args).items() if k not in {"cmd", "output", "cache_dir"}},
    }
    if args.format == "table":
        out = report.table(rows)
    elif args.format == "json":
        out = report.to_json(rows, meta)
    elif args.format == "csv":
        out = report.to_csv(rows)
    elif args.format == "md":
        out = report.to_markdown(rows)
    else:
        all_matched = select(collected.opportunities, filters)
        out = report.to_html(rows, summarize(all_matched, by="chain"), meta)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out)
        print(f"Wrote {len(rows)} rows to {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
