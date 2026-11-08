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

The price pipeline requests the expanded 2000–2026 historical universe from Yahoo first. Symbols for which Yahoo returns no history are eligible for a Tiingo fallback. Tiingo downloads are resumable and capped at 50 symbols per hourly batch. Add the token to the local, Git-ignored `.env` file:

```dotenv
TIINGO_API_TOKEN=your_token_here
```

Then run:

```powershell
momentum-fill-tiingo --config config.yaml
```

The guarded batch script refreshes `data/processed/tiingo_remaining.csv`, checks that no requests were made in the preceding hour, and attempts up to 50 previously unattempted symbols:

```powershell
.\scripts\fetch-tiingo-batch.ps1
```

Repeat it after the provider's hourly quota resets. Each Tiingo history replaces that ticker's Yahoo history completely, avoiding mixed adjustment conventions within a security. Raw vendor data and tokens are never committed.

Verified same-company ticker changes are maintained in `data/processed/ticker_aliases.csv`. Aliases require stable company-identity evidence and a canonical adjusted-price history covering the old membership period. Acquisitions and bankruptcies are not mapped to successor companies. `data/processed/unresolved_ticker_audit.csv` records the identity and resolution status of every remaining failure.

The optimizer evaluates a declared parameter grid over the same February 2015–December 2022 training window, selects by net Sharpe, and then reports the untouched later holdout period separately. Earlier prices initialize longer signals but do not enter candidate scores. The test runs from January 2023 onward. Transaction-cost assumptions are fixed rather than optimized.

The fetcher uses `yfinance` with explicitly auto-adjusted prices and writes a provenance manifest beside the ignored raw CSV. Historical membership is reconstructed from the community-maintained `fja05680/sp500` dataset. Yahoo lacks many former and delisted symbols, so `data/processed/membership_coverage.csv` must accompany every prototype result; this is not yet an institutional-quality point-in-time backtest. The backtest writes monthly gross/net returns, the actual number of ranked securities and positions, cost reconciliation, target weights, terminal-liquidation events, and a performance summary. A held security with no later observation is liquidated at its final available adjusted close, with trading costs charged and proceeds retained as cash. A temporary price gap still stops the run rather than being silently treated as a zero return.

Unidentified historical symbols can be sent to OpenFIGI's free delisted-equity mapping endpoint:

```powershell
momentum-resolve-legacy --config config.yaml
```

The command writes `data/processed/legacy_ticker_candidates.csv`. It combines OpenFIGI's delisted-equity search with the public CRSP-derived S&P membership tables published by WRDS, using membership-date overlap to reject recycled tickers. Evidence-backed exceptions live in `data/processed/legacy_identity_overrides.csv`. Verified identities are promoted in the unresolved audit, but they are not automatic price aliases and do not change the investable universe.

## Layout

- `src/quant_momentum/`: reusable research code
- `notebooks/`: narrative, exploratory analysis only
- `docs/`: public methodology and research definitions
- `reports/`: final figures and short investment-research report
- `data/`: local data only (excluded from Git)

See `.projects/quant-equity-momentum/` for project decisions, sources to assess, and research operating notes.
