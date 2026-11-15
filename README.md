# Cross-Chain Incentive Analyzer

A command-line tool that finds **incentivized DeFi markets** (LP pools, trading/volume campaigns, lending, borrowing, staking and holding rewards) across every chain and protocol covered by its data sources. It normalizes them into one schema, flags risks, ranks them with a risk-adjusted score, and exports tables, JSON, CSV, Markdown or a standalone HTML dashboard.

It uses only the Python standard library (3.10+), and none of the APIs it calls need a key.

## Data sources

| Source | What it covers | Endpoint |
|---|---|---|
| `defillama` | ~15k+ yield pools across 400+ protocols and 100+ chains. Supply-side `apyReward`, plus borrow-side `apyRewardBorrow` from lending markets. Protocol categories come from `api.llama.fi/protocols`. | `yields.llama.fi/pools`, `/lendBorrow` |
| `merkl` | All live Merkl campaigns (used by Uniswap, Aerodrome, Morpho, Euler, Pendle, Curve, Balancer, Ekubo and others on 40+ chains): LP, lend, borrow, hold and swap/trading rewards, with USD/day per reward token. | `api.merkl.xyz/v4/opportunities` |

If one source fails, the scan continues with the others and prints a warning.

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

# Anything paying rewards on USDC, ranked by USD emitted per day
incentives scan --token USDC --sort daily_rewards -n 100

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

Types (`-t`): `lp`, `trading`, `lending`, `borrowing`, `staking`, `holding`, `other`.
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
| `multi_source` | The same market appears in both sources, which helps cross-check figures |
| `stable` | Stablecoin market |

**Score.** The score is meant to read as "APR you can trust". Its APR input is capped at 200% and weighted by market depth on a log scale ($10k TVL → 0.25×, $100M+ → 1×). It is also discounted by how far current APR is from its 30-day mean. Then each flag applies a multiplier: outlier 0.3, low TVL 0.6, IL 0.85, spike 0.8, net-negative 0. Volume campaigns with no APR score 2·log10(USD per day).

## Development

```bash
python -m unittest discover -s tests -v
```

The tests run offline against fixtures shaped like the real API responses.

## Disclaimer

The data comes from third-party aggregators and can be stale or wrong. Verify every market on the protocol itself before depositing. This is not financial advice.
