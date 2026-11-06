# Transaction-Cost-Aware Equity Momentum Research

Research and backtesting project for a monthly cross-sectional equity momentum strategy.

## Research question

Does a diversified portfolio of stocks with strong 12-month returns (excluding the most recent month) earn risk-adjusted returns after conservative trading costs?

## Strategy v0

- **Universe:** for calendar year `Y`, the final available S&P 500 snapshot from year `Y-1`, frozen for the year.
- **Signal:** cumulative return from month `t-12` through `t-2` (12-1 momentum).
- **Rebalance:** monthly, using only data available at the rebalance date.
- **Portfolio:** equal-weight top decile long and bottom decile short, capped at 30 total positions (15 per side); configurable long-only mode.
- **Frictions:** one-way transaction cost and optional short borrow cost.
- **Evaluation:** CAGR, volatility, Sharpe ratio, max drawdown, turnover, benchmark beta/alpha, and robustness checks.

## Non-negotiable research safeguards

1. Never use a price or membership record unavailable at the trading decision timestamp.
2. State whether delisted stocks and historical index constituents are included; absence creates survivorship bias.
3. Apply costs to actual portfolio turnover, not just assumed annual costs.
4. Separate exploratory parameter selection from the final holdout period.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

Place a price panel at `data/raw/prices.csv` with columns `date,ticker,adjusted_close`. The first milestone is to validate the data, build the signal, and run the baseline configuration in `config.yaml`.

Fetch the configured prototype universe, then run the baseline:

```powershell
momentum-fetch --config config.yaml
momentum-fill-tiingo --config config.yaml --dry-run
momentum-backtest --config config.yaml --output reports/baseline
momentum-optimize --config config.yaml --output reports/optimization
```

The price pipeline requests the expanded 2000–2026 historical universe from Yahoo first. Symbols for which Yahoo returns no history are eligible for a Tiingo fallback. Tiingo downloads are resumable and capped at 45 symbols per run to remain below the free plan's 50-request hourly limit. Set the API token only in the local environment:

```powershell
$env:TIINGO_API_TOKEN = Read-Host "Tiingo API token"
momentum-fill-tiingo --config config.yaml
```

Repeat the fill command after the provider's hourly quota resets. Each Tiingo history replaces that ticker's Yahoo history completely, avoiding mixed adjustment conventions within a security. Raw vendor data and tokens are never committed.

The optimizer evaluates a declared parameter grid over the same February 2015–December 2022 training window, selects by net Sharpe, and then reports the untouched later holdout period separately. Earlier prices initialize longer signals but do not enter candidate scores. The test runs from January 2023 onward. Transaction-cost assumptions are fixed rather than optimized.

The fetcher uses `yfinance` with explicitly auto-adjusted prices and writes a provenance manifest beside the ignored raw CSV. Historical membership is reconstructed from the community-maintained `fja05680/sp500` dataset. Yahoo lacks many former and delisted symbols, so `data/processed/membership_coverage.csv` must accompany every prototype result; this is not yet an institutional-quality point-in-time backtest. The backtest writes monthly gross/net returns, the actual number of ranked securities and positions, cost reconciliation, target weights, and a performance summary. It stops if a held security has no return rather than silently treating it as zero.

## Layout

- `src/quant_momentum/`: reusable research code
- `notebooks/`: narrative, exploratory analysis only
- `docs/`: public methodology and research definitions
- `reports/`: final figures and short investment-research report
- `data/`: local data only (excluded from Git)

See `.projects/quant-equity-momentum/` for project decisions, sources to assess, and research operating notes.
