import contextlib
import copy
import io
import json
import os
import time
import tempfile
import unittest
from pathlib import Path

from incentive_analyzer import cli
from incentive_analyzer.analyzer import Analyzer, Filters, select, summarize
from incentive_analyzer.http import HttpError
from incentive_analyzer.models import Category
from incentive_analyzer.sources import merkl as merkl_mod
from incentive_analyzer import analyzer as analyzer_mod
from incentive_analyzer import report

FIX = Path(__file__).parent / "fixtures"


class FakeHttp:
    """Serves fixtures instead of hitting the network."""

    def __init__(self, fail: set[str] = frozenset()):
        self.fail = fail
        self.calls = []
        self.gecko_429 = 0

    def get_json(self, url, params=None, ttl=None):
        self.calls.append((url, params))
        if any(f in url for f in self.fail):
            raise HttpError(f"simulated failure for {url}")
        if "/chart/" in url:
            f = FIX / f"chart_{url.rsplit('/', 1)[1]}.json"
            if not f.exists():
                raise HttpError(f"no chart fixture for {url}")
            return json.loads(f.read_text())
        if "api.geckoterminal.com" in url:
            if self.gecko_429 > 0:
                self.gecko_429 -= 1
                raise HttpError(f"GET {url} failed after 3 attempts: HTTP Error 429")
            net = url.split("/networks/")[1].split("/")[0]
            f = FIX / f"gecko_{net}.json"
            return json.loads(f.read_text()) if f.exists() else {"data": []}
        if url.endswith("/v4/campaigns"):
            f = FIX / f"merkl_campaigns_{(params or {}).get('opportunityId')}.json"
            return json.loads(f.read_text()) if f.exists() else []
        if url.endswith("/v4/tokens"):
            known = {(8453, "0x940181a94a35a4569e4529a3cdfb74e38fd98631"): "AERO",
                     (1, "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9"): "AAVE"}
            sym = known.get(((params or {}).get("chainId"), (params or {}).get("address")))
            return [{"address": params["address"], "symbol": sym}] if sym else []
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
    merge = False  # source-level tests look at raw rows; MergeTests turns it on
    def setUp(self):
        self._ps = merkl_mod.MerklSource.page_size
        merkl_mod.MerklSource.page_size = 2  # exercise pagination with tiny fixtures
        self.http = FakeHttp()
        self.result = Analyzer(self.http, merge=self.merge).collect()
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
        self.assertEqual(self.result.source_counts, {"defillama": 9, "merkl": 8})

    def test_merkl_pagination(self):
        pages = [p["page"] for u, p in self.http.calls if u.endswith("/v4/opportunities")]
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
        # a symbol Merkl knows on Base must not leak to another chain: Aave's
        # Ethereum reward token is named by its own (Ethereum) lookup instead
        self.assertEqual(self.get("defillama", "p-aave-usdc").reward_tokens[0].symbol, "AAVE")
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
        self.assertEqual(res.source_counts, {"defillama": 9})

    def test_unknown_source(self):
        with self.assertRaises(ValueError):
            Analyzer(self.http, ["nope"])


class FilterTests(Base):
    def ids(self, **kw):
        return {o.source_id for o in select(self.opps, Filters(**kw))}

    def test_chain_filter_with_alias(self):
        self.assertEqual(self.ids(chains=["BNB Chain"]), {"p-degen"})

    def test_category_and_tvl(self):
        self.assertEqual(self.ids(categories=[Category.LP], min_tvl=1e6), {"p-aero-weth-usdc", "m1", "p-gmx", "p-emptied"})
        lending = self.ids(categories=[Category.LENDING])
        self.assertNotIn("m8", lending)  # collateral deposit is not lending

    def test_token_matches_reward_tokens(self):
        # --token is the deposited asset: only USDC-AERO deposits AERO; the
        # WETH-USDC pools are merely paid in it
        self.assertEqual(self.ids(token="aero"), {"p-emptied"})
        self.assertEqual(self.ids(reward_token="aero"), {"m1", "p-aero-weth-usdc", "p-emptied"})
        self.assertEqual(self.ids(token="weth", reward_token="aero"), {"m1", "p-aero-weth-usdc"})
        self.assertIn("m2", self.ids(token="usdc"))

    def test_protocol_family_prefix(self):
        self.assertEqual(self.ids(protocols=["aerodrome"]), {"p-aero-weth-usdc", "m1", "p-emptied"})

    def test_safe_and_stable(self):
        safe = self.ids(exclude_flags=("apr_outlier", "low_tvl", "net_negative"))
        self.assertNotIn("p-degen", safe)
        self.assertEqual(self.ids(stablecoin_only=True),
                         {"p-aave-usdc", "p-aave-usdc:borrow", "p-sirloin", "p-aave4-usdc"})

    def test_sort_and_limit(self):
        top = select(self.opps, Filters(), sort="reward_apr", limit=2)
        self.assertEqual([o.source_id for o in top], ["p-degen", "p-emptied"])

    def test_summary(self):
        rows = summarize(self.opps, by="chain")
        base = next(r for r in rows if r["chain"] == "base")
        self.assertEqual(base["markets"], 8)
        self.assertEqual(rows, sorted(rows, key=lambda r: r["daily_rewards_usd"], reverse=True))


class MergeTests(Base):
    merge = True

    def test_vault_pair_merged_into_one_row(self):
        rows = [o for o in self.opps if "p-sirloin" in o.source_id or o.source_id == "m6"]
        self.assertEqual(len(rows), 1)
        o = rows[0]
        self.assertEqual(o.source, "defillama+merkl")
        self.assertEqual(o.market, "Supply to Steakhouse High Yield USDC Edition V2 vault on Morpho")
        self.assertEqual(o.url, "https://app.morpho.org/base/vault/0xbeeff")       # protocol app, from Merkl
        self.assertEqual(o.base_apr, 3.69)                                        # DefiLlama's base APY
        self.assertEqual(o.apr_30d_mean, 6.1)
        self.assertEqual(o.daily_rewards_usd, 30350)                              # Merkl's USD/day
        self.assertEqual([r.symbol for r in o.reward_tokens], ["MORPHO", "USDC"])
        self.assertIn("multi_source", o.flags)
        self.assertEqual(set(o.extra["merged_from"]), {"defillama", "merkl"})

    def test_multi_asset_lp_pair_merged(self):
        ids = {o.source_id for o in self.opps}
        self.assertIn("p-aero-weth-usdc|m1", ids)
        self.assertNotIn("m1", ids)

    def test_different_tvl_not_merged(self):
        ids = {o.source_id for o in self.opps}
        self.assertIn("p-aave4-usdc", ids)   # $1.55M vs Merkl's $3.64M Aave V4 market
        self.assertIn("m7", ids)

    def test_borrow_and_collateral_never_merged(self):
        ids = {o.source_id for o in self.opps}
        self.assertTrue({"m8", "m4", "p-aave-weth:borrow"} <= ids)

    def test_reward_mismatch_flag(self):
        # Merkl's Aerodrome campaign (12.4%) vs DefiLlama's pool (31.5%): kept as max, flagged.
        o = next(o for o in self.opps if o.source_id == "p-aero-weth-usdc|m1")
        self.assertEqual(o.reward_apr, 31.5)
        self.assertIn("reward_mismatch", o.flags)

    def test_no_merge_keeps_rows(self):
        raw = Analyzer(FakeHttp(), merge=False).collect().opportunities
        self.assertEqual(len(raw), len(self.opps) + 2)

    def test_usdc_lending_on_base(self):
        rows = select(self.opps, Filters(chains=["base"], categories=[Category.LENDING], token="USDC"))
        self.assertEqual({o.source_id for o in rows}, {"p-sirloin|m6", "p-aave4-usdc", "m7"})


    def test_identical_listing_collapsed(self):
        from incentive_analyzer.merge import collapse_identical
        a = self.get("defillama+merkl", "p-sirloin|m6")
        twin = copy.deepcopy(a)
        twin.source, twin.source_id, twin.protocol = "defillama", "p-twin", "steakhouse"
        twin.reward_tokens = []
        other_chain = copy.deepcopy(twin)
        other_chain.chain, other_chain.source_id = "ethereum", "p-eth"
        out = collapse_identical([a, twin, other_chain])
        self.assertEqual([o.source_id for o in out], ["p-sirloin|m6", "p-eth"])
        self.assertEqual(a.extra["duplicates"][0]["protocol"], "steakhouse")

    def test_identical_merkl_rows_or_dust_not_collapsed(self):
        from incentive_analyzer.merge import collapse_identical
        m = self.get("merkl", "m7")
        twin = copy.deepcopy(m)
        twin.source_id = "m7-other-hub"
        self.assertEqual(len(collapse_identical([m, twin])), 2)
        dust = copy.deepcopy(self.get("defillama+merkl", "p-sirloin|m6"))
        dust.tvl_usd = 100
        dust2 = copy.deepcopy(dust)
        dust2.source, dust2.source_id = "defillama", "p-dust"
        self.assertEqual(len(collapse_identical([dust, dust2])), 2)


class HistoryTests(Base):
    """The USDC-AERO case: APR up ~8x because 92% of the liquidity left."""

    def test_apr_spike_without_history(self):
        o = self.get("defillama", "p-emptied")
        # 30d mean (184%) is already inflated; median of (184, 33, 30.5) = 33 still sees the spike
        self.assertAlmostEqual(analyzer_mod.baseline_apr(o), 33.03, places=2)
        self.assertIn("apr_spike", o.flags)
        self.assertNotIn("tvl_drop", o.flags)  # needs history

    def test_tvl_drop_after_history(self):
        o = self.get("defillama", "p-emptied")
        healthy = self.get("defillama", "p-aero-weth-usdc")
        before = o.score
        an = Analyzer(self.http)
        self.assertEqual(an.add_history([o, healthy]), 2)
        self.assertAlmostEqual(o.extra["tvl_change_30d"], 3.64e6 / 44e6 - 1, places=3)
        self.assertIn("tvl_drop", o.flags)
        self.assertAlmostEqual(o.score, before * 0.4, places=3)
        self.assertNotIn("tvl_drop", healthy.flags)
        self.assertGreater(healthy.score, o.score)

    def test_missing_history_is_harmless(self):
        o = self.get("defillama", "p-aave-usdc")
        before = (list(o.flags), o.score)
        self.assertEqual(Analyzer(self.http).add_history([o]), 0)
        self.assertEqual((o.flags, o.score), before)

    def test_merged_and_merkl_rows(self):
        from incentive_analyzer.history import llama_pool_id
        merged = next(o for o in Analyzer(FakeHttp()).collect().opportunities if o.source == "defillama+merkl")
        self.assertTrue(llama_pool_id(merged))
        self.assertIsNone(llama_pool_id(self.get("merkl", "m2")))
        self.assertIsNone(llama_pool_id(self.get("defillama", "p-aave-weth:borrow")))

    def test_young_pool_has_no_change(self):
        from incentive_analyzer.history import tvl_change
        pts = [{"timestamp": "2026-11-10T00:00:00.000Z", "tvlUsd": 1},
               {"timestamp": "2026-11-16T00:00:00.000Z", "tvlUsd": 5}]
        self.assertEqual(tvl_change(pts), (None, None))

    def test_select_with_history_reranks(self):
        an = Analyzer(self.http)
        rows = analyzer_mod.select_with_history(an, self.opps, Filters(chains=["base"], categories=[Category.LP]))
        ids = [o.source_id for o in rows]
        self.assertLess(ids.index("p-aero-weth-usdc"), ids.index("p-emptied"))
        charts = [u for u, _ in self.http.calls if "/chart/" in u]
        self.assertIn("https://yields.llama.fi/chart/p-emptied", charts)


class TokenNameTests(Base):
    def test_address_only_reward_tokens_named(self):
        self.assertEqual([r.symbol for r in self.get("defillama", "p-aave-usdc").reward_tokens], ["AAVE"])
        self.assertEqual([r.symbol for r in self.get("defillama", "p-emptied").reward_tokens], ["AERO"])
        self.assertIn("p-emptied", {o.source_id for o in select(self.opps, Filters(reward_token="AERO"))})

    def test_unknown_and_non_evm_left_alone(self):
        degen = self.get("defillama", "p-degen")  # Merkl doesn't know this token
        self.assertTrue(degen.reward_tokens[0].symbol.startswith("0x"))
        looked_up = [p for u, p in self.http.calls if u.endswith("/v4/tokens")]
        self.assertTrue(all(p["address"].startswith("0x") for p in looked_up))

    def test_lookup_can_be_disabled(self):
        http = FakeHttp()
        Analyzer(http, name_tokens=False).collect()
        self.assertFalse([u for u, _ in http.calls if u.endswith("/v4/tokens")])


class HistoryScopeTests(Base):
    merge = True

    def test_summary_best_market_is_history_checked(self):
        from incentive_analyzer.analyzer import summarize, summarize_with_history
        base = lambda rows: next(r for r in rows if r["chain"] == "base")
        # Without history the emptied pool looks like Base's best market...
        self.assertIn("USDC-AERO", base(summarize(self.opps))["best_market"])
        # ...with history it is flagged tvl_drop and loses the spot.
        rows = summarize_with_history(Analyzer(self.http), self.opps)
        self.assertNotIn("USDC-AERO", base(rows)["best_market"])
        self.assertIn("tvl_drop", self.get("defillama", "p-emptied").flags)

    def test_summary_checks_only_shown_groups_best_rows(self):
        from incentive_analyzer.analyzer import summarize_with_history
        rows = summarize_with_history(Analyzer(self.http), self.opps, by="chain")
        charts = [u for u, _ in self.http.calls if "/chart/" in u]
        self.assertIn("https://yields.llama.fi/chart/p-emptied", charts)
        # a round or two per shown group, not one request per pool
        self.assertLessEqual(len(charts), 2 * len(rows))
        self.http.calls.clear()
        summarize_with_history(Analyzer(self.http), self.opps, by="chain", top=1)
        # the top group (Ethereum by USD/day) is led by a Merkl-only row: nothing to check
        self.assertFalse([u for u, _ in self.http.calls if "/chart/" in u])

    def test_history_limit_caps_requests(self):
        rows = analyzer_mod.select_with_history(Analyzer(self.http), self.opps, history_limit=1)
        self.assertEqual(len([u for u, _ in self.http.calls if "/chart/" in u]), 1)
        self.assertEqual(len(rows), len(self.opps))

    def test_rows_checked_once(self):
        an = Analyzer(self.http)
        o = self.get("defillama", "p-emptied")
        an.add_history([o])
        an.add_history([o])
        self.assertEqual(len([u for u, _ in self.http.calls if "/chart/" in u]), 1)


class CampaignEndTests(Base):
    """ETH/USDG on Robinhood Chain: 50K USDG over Nov 12-26, renewed back-to-back."""
    NOW = 1794830400  # 2026-11-15 12:00 UTC: 11.05 days before the Nov 26 13:00 end

    def setUp(self):
        super().setUp()
        self.real_time = time.time
        time.time = lambda: self.NOW

    def tearDown(self):
        time.time = self.real_time
        super().tearDown()

    def ending_in(self, o, days):
        o.extra["campaign_end"] = str(int(self.NOW + days * 86400))
        o.extra.pop("renewals", None)
        o.flags = analyzer_mod.risk_flags(o)
        o.score = analyzer_mod.score(o)
        return o

    def test_days_left_and_column(self):
        o = self.ending_in(self.get("merkl", "m2"), 11.04)
        self.assertAlmostEqual(o.days_left(), 11.04, places=2)
        self.assertEqual(report.ends(o), "11d")
        self.assertNotIn("ending_soon", o.flags)
        self.assertEqual(report.ends(self.get("defillama", "p-aave-usdc")), "-")  # unknown end

    def test_ending_soon_without_renewal_record(self):
        o = self.get("merkl", "m2")   # no campaign-history fixture: checked, 0 renewals
        before = analyzer_mod.score(o)
        self.ending_in(o, 3)
        self.assertNotIn("ending_soon", o.flags)        # not checked yet: no flag
        Analyzer(self.http).add_history([o])
        self.assertEqual(o.extra["renewals"], 0)
        self.assertIn("ending_soon", o.flags)
        self.assertAlmostEqual(o.score, before * 0.75, places=3)
        self.assertEqual(report.ends(self.ending_in(o, 0.5)), "<1d")
        self.assertEqual(report.ends(self.ending_in(o, -0.1)), "ended")

    def test_renewed_campaign_not_flagged(self):
        o = self.ending_in(self.get("merkl", "m1"), 3)   # fixture history: renewed once back-to-back
        self.assertNotIn("ending_soon", o.flags)       # not checked yet: no flag
        Analyzer(self.http).add_history([o])
        self.assertEqual(o.extra["renewals"], 1)
        self.assertNotIn("ending_soon", o.flags)
        self.assertEqual(report.ends(o), "3d ↻1")
        self.assertTrue(any(u.endswith("/v4/campaigns") for u, _ in self.http.calls))

    def test_failed_history_lookup_does_not_flag(self):
        o = self.ending_in(self.get("merkl", "m2"), 3)
        Analyzer(FakeHttp(fail={"/v4/campaigns"})).add_history([o])
        self.assertNotIn("renewals", o.extra)
        self.assertNotIn("ending_soon", o.flags)

    def test_long_campaigns_skip_renewal_lookup(self):
        o = self.ending_in(self.get("merkl", "m1"), 30)
        Analyzer(self.http).add_history([o])
        self.assertNotIn("renewals", o.extra)
        self.assertFalse([u for u, _ in self.http.calls if u.endswith("/v4/campaigns")])

    def test_count_renewals(self):
        from incentive_analyzer.campaigns import count_renewals
        day = 86400
        chain3 = [{"startTimestamp": s, "endTimestamp": s + 7 * day} for s in (0, 7 * day, 14 * day)]
        self.assertEqual(count_renewals(chain3, now=15 * day), 2)
        gap = [{"startTimestamp": 0, "endTimestamp": 7 * day}, {"startTimestamp": 20 * day, "endTimestamp": 27 * day}]
        self.assertEqual(count_renewals(gap, now=21 * day), 0)      # 13-day gap: a new program, not a renewal
        overlap = [{"startTimestamp": 0, "endTimestamp": 10 * day}, {"startTimestamp": 8 * day, "endTimestamp": 15 * day}]
        self.assertEqual(count_renewals(overlap, now=9 * day), 1)
        future = chain3 + [{"startTimestamp": 30 * day, "endTimestamp": 37 * day}]
        self.assertEqual(count_renewals(future, now=15 * day), 2)   # scheduled-but-unstarted ignored
        self.assertEqual(count_renewals([], now=0), 0)
        real = json.loads((FIX / "merkl_campaigns_m1.json").read_text())
        self.assertEqual(count_renewals(real, now=self.NOW), 1)

    def test_min_days_left_filter(self):
        self.ending_in(self.get("merkl", "m2"), 2)
        self.ending_in(self.get("merkl", "m1"), 20)
        ids = {o.source_id for o in select(self.opps, Filters(min_days_left=7))}
        self.assertNotIn("m2", ids)
        self.assertIn("m1", ids)
        self.assertIn("p-aave-usdc", ids)   # end unknown: kept

    def test_exports_include_days_left(self):
        self.ending_in(self.get("merkl", "m2"), 5)
        rows = select(self.opps, Filters(token="usdc"))
        self.assertIn("days_left", report.to_csv(rows).splitlines()[0])
        d = next(x for x in json.loads(report.to_json(rows))["opportunities"] if x["source_id"] == "m2")
        self.assertAlmostEqual(d["days_left"], 5, places=3)


class FeeEstimateTests(Base):
    V3, V4 = "0x" + "ab" * 20, "0x" + "cd" * 32

    def pool(self, ident, type_="UNISWAP_V4", chain="robinhood-chain", protocol="uniswap", base=None):
        o = copy.deepcopy(self.get("merkl", "m1"))
        o.source_id, o.chain, o.protocol, o.base_apr = f"pool-{ident[:6]}-{protocol}", chain, protocol, base
        o.market = "Provide liquidity to UniswapV4 SPY-MU 0.05%"
        o.extra.update({"type": type_, "identifier": ident})
        o.extra.pop("base_apr_estimated", None)
        return o

    def test_estimate_matches_formula(self):
        from incentive_analyzer.gecko import attach_fee_estimates
        o = self.pool(self.V3)
        self.assertEqual(attach_fee_estimates([o], self.http, sleep=lambda s: None), 1)
        self.assertAlmostEqual(o.base_apr, 849318 * 0.05 / 410702 * 365, places=3)   # ~37.7%
        o.flags = analyzer_mod.risk_flags(o)
        self.assertIn("fee_estimated", o.flags)
        self.assertTrue(report.COLUMNS[6][1](1, o).startswith("~"))                   # Base% shown as ~37.74

    def test_dynamic_fee_pool_gets_volume_not_guess(self):
        from incentive_analyzer.gecko import attach_fee_estimates
        o = self.pool(self.V4)  # like ETH/USDG: volume known, fee set by a hook
        attach_fee_estimates([o], self.http, sleep=lambda s: None)
        self.assertIsNone(o.base_apr)
        self.assertEqual(o.extra["volume_usd_1d"], 37368404.0)
        o.flags = analyzer_mod.risk_flags(o)
        self.assertIn("fee_unknown", o.flags)

    def test_ineligible_rows_skipped(self):
        from incentive_analyzer.gecko import candidate
        self.assertIsNotNone(candidate(self.pool(self.V3)))
        self.assertIsNone(candidate(self.pool(self.V3, protocol="aerodrome")))     # ve(3,3): fees go to voters
        self.assertIsNone(candidate(self.pool(self.V3, type_="ERC20LOGPROCESSOR")))  # identifier isn't a pool
        self.assertIsNone(candidate(self.pool(self.V3, base=5.0)))                  # source already has base APR
        self.assertIsNone(candidate(self.pool("0xpool1")))                           # not an address
        self.assertIsNone(candidate(self.pool(self.V3, chain="neo")))                # network not mapped
        self.assertIsNone(candidate(self.get("defillama", "p-aero-weth-usdc")))      # not a Merkl row

    def test_rate_limit_waits_once_then_retries(self):
        from incentive_analyzer.gecko import RATE_LIMIT_WAIT_S, attach_fee_estimates
        waits = []
        self.http.gecko_429 = 1
        o = self.pool(self.V3)
        self.assertEqual(attach_fee_estimates([o], self.http, sleep=waits.append), 1)
        self.assertEqual(waits, [RATE_LIMIT_WAIT_S])

    def test_persistent_rate_limit_is_harmless(self):
        from incentive_analyzer.gecko import attach_fee_estimates
        self.http.gecko_429 = 5
        o = self.pool(self.V3)
        self.assertEqual(attach_fee_estimates([o], self.http, sleep=lambda s: None), 0)
        self.assertIsNone(o.base_apr)
        self.assertFalse(o.extra["gecko_checked"])

    def test_batched_per_network(self):
        from incentive_analyzer.gecko import attach_fee_estimates
        attach_fee_estimates([self.pool(self.V3), self.pool(self.V4)], self.http, sleep=lambda s: None)
        gecko = [u for u, _ in self.http.calls if "geckoterminal" in u]
        self.assertEqual(len(gecko), 1)
        self.assertIn("/networks/robinhood/pools/multi/", gecko[0])

    def test_can_be_disabled(self):
        o = self.pool(self.V3)
        Analyzer(self.http, fee_estimates=False).add_history([o])
        self.assertIsNone(o.base_apr)
        self.assertFalse([u for u, _ in self.http.calls if "geckoterminal" in u])


class CollateralTests(Base):
    def test_collateral_category(self):
        self.assertEqual(self.get("merkl", "m8").category, Category.COLLATERAL)
        # "borrow from collateral" rewards borrowing, so it stays borrowing
        self.assertEqual(self.get("merkl", "m9").category, Category.BORROWING)

    def test_token_filter_uses_collateral_asset_only(self):
        usdc = {o.source_id for o in select(self.opps, Filters(token="USDC"))}
        self.assertNotIn("m8", usdc)
        usde = {o.source_id for o in select(self.opps, Filters(token="USDe"))}
        self.assertIn("m8", usde)


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

    def test_no_history_skips_chart_requests(self):
        http = FakeHttp()
        orig = cli.HttpClient
        cli.HttpClient = lambda **kw: http
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                cli.main(["scan", "--no-history"])
        finally:
            cli.HttpClient = orig
        self.assertFalse([u for u, _ in http.calls if "/chart/" in u])

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
