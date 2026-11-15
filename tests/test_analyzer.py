import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from incentive_analyzer import cli
from incentive_analyzer.analyzer import Analyzer, Filters, select, summarize
from incentive_analyzer.http import HttpError
from incentive_analyzer.models import Category
from incentive_analyzer.sources import merkl as merkl_mod
from incentive_analyzer import report

FIX = Path(__file__).parent / "fixtures"


class FakeHttp:
    """Serves fixtures instead of hitting the network."""

    def __init__(self, fail: set[str] = frozenset()):
        self.fail = fail
        self.calls = []

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        if any(f in url for f in self.fail):
            raise HttpError(f"simulated failure for {url}")
        if url.endswith("/pools"):
            return json.loads((FIX / "llama_pools.json").read_text())
        if url.endswith("/lendBorrow"):
            return json.loads((FIX / "llama_lendborrow.json").read_text())
        if url.endswith("/protocols"):
            return json.loads((FIX / "llama_protocols.json").read_text())
        if "merkl" in url:
            page = (params or {}).get("page", 0)
            f = FIX / f"merkl_page{page}.json"
            return json.loads(f.read_text()) if f.exists() else []
        raise AssertionError(f"unexpected url {url}")


class Base(unittest.TestCase):
    def setUp(self):
        self._ps = merkl_mod.MerklSource.page_size
        merkl_mod.MerklSource.page_size = 2  # exercise pagination with tiny fixtures
        self.http = FakeHttp()
        self.result = Analyzer(self.http).collect()
        self.opps = self.result.opportunities

    def tearDown(self):
        merkl_mod.MerklSource.page_size = self._ps

    def get(self, source, source_id):
        return next(o for o in self.opps if o.source == source and o.source_id == source_id)


class CollectTests(Base):
    def test_only_incentivized_markets_are_kept(self):
        ids = {o.source_id for o in self.opps}
        self.assertNotIn("p-lido", ids)          # apyReward 0
        self.assertNotIn("p-aave-weth", ids)     # apyReward null (supply side)
        self.assertNotIn("m5", ids)              # dead merkl campaign
        self.assertEqual(self.result.source_counts, {"defillama": 6, "merkl": 4})

    def test_merkl_pagination(self):
        pages = [p["page"] for u, p in self.http.calls if "merkl" in u]
        self.assertEqual(pages, [0, 1, 2])

    def test_categories(self):
        self.assertEqual(self.get("defillama", "p-aave-usdc").category, Category.LENDING)
        self.assertEqual(self.get("defillama", "p-aero-weth-usdc").category, Category.LP)
        self.assertEqual(self.get("defillama", "p-gmx").category, Category.LP)  # perp LP vault
        self.assertEqual(self.get("defillama", "p-degen").category, Category.LP)  # heuristic fallback
        self.assertEqual(self.get("defillama", "p-aave-weth:borrow").category, Category.BORROWING)
        self.assertEqual(self.get("merkl", "m1").category, Category.LP)
        self.assertEqual(self.get("merkl", "m2").category, Category.LENDING)
        self.assertEqual(self.get("merkl", "m3").category, Category.TRADING)
        self.assertEqual(self.get("merkl", "m4").category, Category.BORROWING)

    def test_chain_normalization(self):
        self.assertEqual(self.get("defillama", "p-degen").chain, "bsc")
        self.assertEqual(self.get("merkl", "m4").chain, "sonic")
        self.assertEqual(self.get("defillama", "p-aave-weth:borrow").chain, "ethereum")

    def test_borrow_side_net_apr(self):
        o = self.get("defillama", "p-aave-weth:borrow")
        self.assertAlmostEqual(o.base_apr, -2.4)
        self.assertAlmostEqual(o.total_apr, 0.7)
        self.assertNotIn("net_negative", o.flags)
        neg = self.get("defillama", "p-aave-usdc:borrow")
        self.assertIn("net_negative", neg.flags)
        self.assertEqual(neg.score, 0)

    def test_risk_flags(self):
        degen = self.get("defillama", "p-degen")
        for f in ("low_tvl", "apr_outlier", "reward_dependent", "il_risk", "apr_spike"):
            self.assertIn(f, degen.flags)
        self.assertIn("stable", self.get("defillama", "p-aave-usdc").flags)

    def test_cross_source_link(self):
        llama = self.get("defillama", "p-aero-weth-usdc")
        merkl = self.get("merkl", "m1")
        self.assertIn("multi_source", llama.flags)
        self.assertEqual(llama.extra["also_on"], ["merkl"])
        self.assertEqual(merkl.extra["also_on"], ["defillama"])

    def test_volume_campaign_scored_on_daily_rewards(self):
        swap = self.get("merkl", "m3")
        self.assertNotIn("low_tvl", swap.flags)
        self.assertAlmostEqual(swap.score, 2 * 3.39794, places=3)
        self.assertNotIn("reward_dependent", self.get("merkl", "m4").flags)  # base yield unknown

    def test_merkl_native_apr_and_protocol_fallback(self):
        m1, m2 = self.get("merkl", "m1"), self.get("merkl", "m2")
        self.assertEqual(m1.base_apr, 7.5)
        self.assertAlmostEqual(m1.total_apr, 19.9)
        self.assertEqual(m2.protocol, "morpho")  # from tags when protocol is null
        self.assertIn("unverified", m2.flags)

    def test_reward_symbols_resolved_across_sources(self):
        aero = self.get("defillama", "p-aero-weth-usdc")
        self.assertEqual(aero.reward_tokens[0].symbol, "AERO")
        # same address on another chain must not be relabelled
        self.assertTrue(self.get("defillama", "p-aave-usdc").reward_tokens[0].symbol.startswith("0x"))
        self.assertNotIn("token_addresses", self.get("merkl", "m1").to_dict())

    def test_daily_rewards(self):
        self.assertEqual(self.get("merkl", "m1").est_daily_rewards_usd, 14400)
        aave = self.get("defillama", "p-aave-usdc")
        self.assertAlmostEqual(aave.est_daily_rewards_usd, 850e6 * 0.012 / 365)

    def test_scoring_prefers_deep_real_yield_over_degen(self):
        degen = self.get("defillama", "p-degen")
        aero = self.get("defillama", "p-aero-weth-usdc")
        self.assertGreater(aero.score, degen.score)

    def test_source_failure_is_isolated(self):
        res = Analyzer(FakeHttp(fail={"merkl"})).collect()
        self.assertIn("merkl", res.errors)
        self.assertEqual(res.source_counts, {"defillama": 6})

    def test_unknown_source(self):
        with self.assertRaises(ValueError):
            Analyzer(self.http, ["nope"])


class FilterTests(Base):
    def ids(self, **kw):
        return {o.source_id for o in select(self.opps, Filters(**kw))}

    def test_chain_filter_with_alias(self):
        self.assertEqual(self.ids(chains=["BNB Chain"]), {"p-degen"})

    def test_category_and_tvl(self):
        self.assertEqual(self.ids(categories=[Category.LP], min_tvl=1e6), {"p-aero-weth-usdc", "m1", "p-gmx"})

    def test_token_matches_reward_tokens(self):
        self.assertEqual(self.ids(token="aero"), {"m1", "p-aero-weth-usdc"})
        self.assertIn("m2", self.ids(token="usdc"))

    def test_protocol_family_prefix(self):
        self.assertEqual(self.ids(protocols=["aerodrome"]), {"p-aero-weth-usdc", "m1"})

    def test_safe_and_stable(self):
        safe = self.ids(exclude_flags=("apr_outlier", "low_tvl", "net_negative"))
        self.assertNotIn("p-degen", safe)
        self.assertEqual(self.ids(stablecoin_only=True), {"p-aave-usdc", "p-aave-usdc:borrow"})

    def test_sort_and_limit(self):
        top = select(self.opps, Filters(), sort="reward_apr", limit=2)
        self.assertEqual([o.source_id for o in top], ["p-degen", "p-aero-weth-usdc"])

    def test_summary(self):
        rows = summarize(self.opps, by="chain")
        base = next(r for r in rows if r["chain"] == "base")
        self.assertEqual(base["markets"], 2)
        self.assertAlmostEqual(base["tvl_usd"], 84.5e6)
        self.assertEqual(rows, sorted(rows, key=lambda r: r["daily_rewards_usd"], reverse=True))


class ReportTests(Base):
    def test_renderers(self):
        rows = select(self.opps, Filters())
        self.assertIn("aerodrome", report.table(rows, width=140))
        self.assertEqual(len(json.loads(report.to_json(rows))["opportunities"]), len(rows))
        self.assertEqual(report.to_csv(rows).count("\n"), len(rows) + 1)
        self.assertIn("](https://", report.to_markdown(rows))
        html = report.to_html(rows, summarize(rows))
        self.assertIn("<!doctype html>", html)
        self.assertNotIn("__DATA__", html)

    def test_html_escapes_script_breakout(self):
        o = self.opps[0]
        o.market = "</script><script>alert(1)</script>"
        self.assertNotIn("</script><script>alert", report.to_html([o]))

    def test_usd(self):
        self.assertEqual(report.usd(1_234_567), "$1.23M")
        self.assertEqual(report.usd(None), "-")


@unittest.skipUnless(os.environ.get("INCENTIVES_LIVE"), "set INCENTIVES_LIVE=1 to hit the real APIs")
class LiveSmokeTests(unittest.TestCase):
    def test_live_scan(self):
        from incentive_analyzer.http import HttpClient
        res = Analyzer(HttpClient(cache_ttl=0)).collect()
        self.assertEqual(res.errors, {})
        self.assertGreater(res.source_counts.get("defillama", 0), 200)
        self.assertGreater(res.source_counts.get("merkl", 0), 50)
        cats = {o.category for o in res.opportunities}
        self.assertTrue({Category.LP, Category.LENDING, Category.BORROWING} <= cats)
        self.assertGreater(len({o.chain for o in res.opportunities}), 20)


class CliTests(unittest.TestCase):
    def run_cli(self, *argv):
        orig = cli.HttpClient
        cli.HttpClient = lambda **kw: FakeHttp()
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(list(argv))
        finally:
            cli.HttpClient = orig
        return code, out.getvalue(), err.getvalue()

    def test_scan_json(self):
        code, out, _ = self.run_cli("scan", "-t", "lp", "--min-tvl", "1000000", "-f", "json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertTrue(all(o["category"] == "lp" for o in data["opportunities"]))

    def test_summary_and_html_file(self):
        code, out, _ = self.run_cli("summary", "--by", "protocol")
        self.assertEqual(code, 0)
        self.assertIn("aerodrome", out)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "r.html"
            code, _, err = self.run_cli("scan", "-f", "html", "-o", str(path))
            self.assertEqual(code, 0)
            self.assertTrue(path.read_text().startswith("<!doctype html>"))

    def test_bad_type(self):
        with self.assertRaises(SystemExit):
            self.run_cli("scan", "-t", "nonsense")


if __name__ == "__main__":
    unittest.main()
