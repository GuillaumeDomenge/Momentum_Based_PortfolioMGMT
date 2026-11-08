# Baseline methodology

## Objective

Test whether recent relative winners outperform recent relative losers after conservative implementation costs. This baseline is an empirical research exercise, not an investable recommendation.

## Timeline and signal

At each month-end `t`, rank eligible securities by the adjusted-price return ending one month before portfolio formation. With the default settings, the calculation uses `price[t-1] / price[t-12] - 1`. This prevents the return earned during the newest month from entering both the signal and the same holding period.

The target formed at `t` is held from `t` to `t+1`. Code enforces this with a one-period weight lag.

## Portfolio

- Freeze each year's eligible universe from the last membership snapshot in the previous calendar year.
- Long the highest-signal decile and short the lowest-signal decile.
- Cap the long-short portfolio at 30 names: at most 15 longs and 15 shorts.
- Equal weight within each side.
- Target gross exposure is 200% and target net exposure is 0%.
- A configurable long-only variant supports settings where shorting assumptions cannot be defended.

## Costs

Trading cost equals the configured one-way basis-point assumption multiplied by total traded notional. Traded notional compares the new target with prior weights after they drift with security returns. Short borrow cost is applied monthly to short gross exposure.

## Data policy

Adjusted prices must be positive and unique by date/security. A held security with a missing return stops the run. Before publishing results, the dataset decision must document:

- historical universe membership and survivorship treatment;
- split, dividend, merger, and delisting adjustments;
- point-in-time availability and revision policy;
- licensing and reproducibility constraints.

Yahoo is the primary prototype price source. Tiingo is used only for historical members with no Yahoo observations. A security uses one vendor for its complete history; prices are never spliced between vendors. Vendor-specific raw files remain local, while ticker-level provenance and aggregate coverage are recorded separately.

Historical ticker aliases are applied only when the replacement represents a documented continuation and its adjusted history covers the former symbol's membership period. Acquirers are not substituted for acquired securities. Bankruptcy and OTC-terminal symbols remain unresolved unless an appropriate terminal return is sourced.

## Evaluation protocol

Choose the final holdout period before robustness testing. Report gross and net results, turnover, CAGR, annualized volatility, Sharpe ratio, and maximum drawdown. Add benchmark/factor regressions only after the return pipeline is independently reconciled.

Parameter grids are robustness checks, not a search for the best-looking backtest. Every tested variation should be reported or mechanically summarized.

## Parameter training and holdout

The declared grid varies momentum lookback (6, 9, or 12 months), total position cap (10, 20, or 30), and rebalance interval (monthly or quarterly). It holds the one-month skip, 10% tail rule, and cost assumptions fixed. Every candidate is ranked by net Sharpe over the identical February 2015–December 2022 window. Earlier prices initialize signals only. The selected configuration is subsequently evaluated from January 2023 onward; holdout metrics never participate in selection.

Selection means “best under the declared objective,” not necessarily profitable. The report explicitly counts candidates with positive training CAGR and warns when there are none.
