# Cross-Chain Incentive Analyzer

A command-line tool that finds **incentivized DeFi markets** (LP pools, trading/volume campaigns, lending, borrowing, staking and holding rewards) across every chain and protocol covered by its data sources. It normalizes them into one schema, flags risks, ranks them with a risk-adjusted score, and exports tables, JSON, CSV, Markdown or a standalone HTML dashboard.

It uses only the Python standard library (3.10+), and none of the APIs it calls need a key.

## Data sources

| Source | What it covers | Endpoint |
|---|---|---|
| `defillama` | ~15k+ yield pools across 400+ protocols and 100+ chains. Supply-side `apyReward`, plus borrow-side `apyRewardBorrow` from lending markets. Protocol categories come from `api.llama.fi/protocols`. | `yields.llama.fi/pools`, `/lendBorrow` |
| `merkl` | All live Merkl campaigns (used by Uniswap, Aerodrome, Morpho, Euler, Pendle, Curve, Balancer, Ekubo and others on 40+ chains): LP, lend, borrow, hold, stake and swap/trading rewards, with USD/day per reward token and the market's native (organic) APR. | `api.merkl.xyz/v4/opportunities` |

If one source fails, the scan continues with the others and prints a warning.

**Duplicate merging.** Many markets appear in both sources under different names (DefiLlama "SIRLOINUSDC" and Merkl "Supply to Steakhouse High Yield USDC vault on Morpho"). These are merged into one row with source `defillama+merkl`. Two rows merge only if they are on the same chain and protocol family, their TVL is within 5%, and they share a deposit token (by symbol, including vault share tokens, or by contract address).

The merged row keeps DefiLlama's base APY, 30-day mean and risk data, and takes Merkl's readable name, protocol app link, reward token symbols and USD/day. A second pass folds markets that one source lists twice under two protocol names; it needs identical numbers and at least $50k TVL. Both original rows are kept in the JSON output under `extra.merged_from` / `extra.duplicates`. Use `--no-merge` to see the raw rows.

In a live run on 2026-11-15, a full scan took about 3 seconds and returned **2,057 incentivized markets** (DefiLlama 1,477 + Merkl 580) on more than 20 chains, worth about $4.6M/day in rewards.

DefiLlama reports reward tokens as contract addresses. Where Merkl knows the same token on the same chain, the address is replaced with its symbol.

To add a source (for example a points program, a perp DEX's trading-rewards API, or a chain foundation's incentive list), subclass `incentive_analyzer.sources.base.Source`, yield `Opportunity` objects from `fetch()`, and register the class in `sources/__init__.py`.

## Install

```bash
pip install -e .          # installs the `incentives` command
# or run without installing:
python -m incentive_analyzer --help
```

## Usage

```bash
# Top 50 opportunities overall, by risk-adjusted score
incentives scan

# LP incentives on Base and Arbitrum with at least $1M TVL and 10% reward APR
incentives scan -t lp -c base,arbitrum --min-tvl 1e6 --min-reward-apr 10

# Stablecoin lending/borrowing rewards, excluding outliers and thin markets
incentives scan -t lending,borrowing --stable --safe --sort reward_apr

# Markets where you deposit USDC, ranked by USD emitted per day
incentives scan --token USDC --sort daily_rewards -n 100

# USDC lending on Base
incentives scan -c base -t lending --token USDC

# Anything paying rewards in MORPHO
incentives scan --reward-token MORPHO

# Trading / volume incentives only
incentives scan -t trading

# Where is the incentive money going? (by chain / protocol / category / source)
incentives summary --by chain
incentives summary --by protocol -t lp --min-tvl 5e5

# Exports
incentives scan -n 0 -f html -o reports/incentives.html   # interactive dashboard
incentives scan -n 0 -f csv  -o reports/incentives.csv
incentives scan -f json | jq '.opportunities[0]'
```

Types (`-t`): `lp`, `trading`, `lending`, `borrowing`, `collateral`, `staking`, `holding`, `other`.

`--token` matches the asset you **deposit**, and `--reward-token` matches the asset you're **paid in**. `collateral` covers campaigns that reward posting collateral (e.g. "Deposit USDe as collateral on USDe/USDC"). These are kept out of `lending`, and `--token` matches only their collateral asset, so the example appears under USDe, not USDC.

`trading` means rewards for swapping or buying (Merkl `SWAP` campaigns). Deposits into perp or DEX vaults (GLP/GLV/HLP style) count as `lp`, because you earn by supplying liquidity, not by trading.
Sort keys: `score`, `reward_apr`, `total_apr`, `tvl`, `daily_rewards`.

API responses are cached in `~/.cache/incentive-analyzer` for 10 minutes. Change this with `--cache-ttl 0`, `--cache-dir`, or the `INCENTIVES_CACHE_DIR` environment variable.

## How results are computed

**Columns**
- **Base%**: organic yield (trading fees or supply interest). For borrow markets it is the negative borrow rate, so **Total%** is your net carry.
- **Reward%**: yield from incentives only.
- **Rewards/day**: USD emitted per day. This is the source's figure when available (Merkl), otherwise TVL × Reward% / 365.
- DefiLlama reports APY and Merkl reports APR. Both are shown as reported.

**Risk flags**

| Flag | Meaning |
|---|---|
| `low_tvl` | TVL under $100k |
| `apr_outlier` | Total over 500% or flagged as an outlier by DefiLlama |
| `reward_dependent` | Over 90% of yield is incentives, so it disappears when the campaign ends |
| `il_risk` | Impermanent-loss exposure |
| `apr_spike` | Current APR is over 2× its 30-day mean |
| `net_negative` | Borrow rewards don't cover the interest |
| `multi_source` | Merged from DefiLlama and Merkl, so the figures are cross-checked |
| `reward_mismatch` | The two sources' reward APRs differ by more than 25%; the higher one is shown |
| `unverified` | Merkl marks the campaign `[UNVERIFIED]` |
| `stable` | Stablecoin market |

**Score.** The score is meant to read as "APR you can trust". Its APR input is capped at 150% and weighted by market depth on a log scale ($1k TVL → 0.05×, $1M → 0.62×, $100M+ → 1×). It is also discounted by how far current APR is from its 30-day mean. Then each flag applies a multiplier: outlier 0.3, low TVL 0.5, unverified 0.5, IL 0.85, spike 0.8, net-negative 0. Volume campaigns with no APR score 2·log10(USD per day).

## Development

```bash
python -m unittest discover -s tests -v
```

The tests run offline against fixtures shaped like the real API responses. To also run a smoke test against the live APIs:

```bash
INCENTIVES_LIVE=1 python -m unittest tests.test_analyzer.LiveSmokeTests -v
```

## Disclaimer

The data comes from third-party aggregators and can be stale or wrong. Verify every market on the protocol itself before depositing. This is not financial advice.
