from dataclasses import dataclass

import pandas as pd

from quant_momentum.portfolio import build_weights
from quant_momentum.signals import momentum_12_1


@dataclass(frozen=True)
class BacktestResult:
    """Auditable monthly outputs from a strategy run."""

    returns: pd.DataFrame
    target_weights: pd.DataFrame
    signals: pd.DataFrame


def run_backtest(
    monthly_prices: pd.DataFrame,
    *,
    eligibility: pd.DataFrame | None = None,
    lookback_months: int = 12,
    skip_months: int = 1,
    quantile: float = 0.10,
    max_positions: int | None = None,
    long_only: bool = False,
    rebalance_months: int = 1,
    one_way_bps: float = 10.0,
    annual_short_borrow_bps: float = 30.0,
) -> BacktestResult:
    """Run a monthly close-to-close backtest with lagged weights and explicit costs.

    A target formed at month-end t earns the return from t to t+1. Trading costs
    for that rebalance are charged to the same subsequent holding period.
    """
    if monthly_prices.empty:
        raise ValueError("monthly_prices must not be empty.")
    if one_way_bps < 0 or annual_short_borrow_bps < 0:
        raise ValueError("Cost assumptions must be non-negative.")
    if rebalance_months < 1 or 12 % rebalance_months != 0:
        raise ValueError("rebalance_months must be a positive divisor of 12.")

    signals = momentum_12_1(monthly_prices, lookback_months, skip_months)
    if eligibility is not None:
        eligibility = eligibility.reindex_like(signals).fillna(False).astype(bool)
        signals = signals.where(eligibility)
    proposed_weights = build_weights(
        signals,
        quantile=quantile,
        long_only=long_only,
        max_positions=max_positions,
    )
    asset_returns = monthly_prices.pct_change(fill_method=None)
    scheduled = (monthly_prices.index.month - 1) % rebalance_months == 0
    target_weights = pd.DataFrame(0.0, index=monthly_prices.index, columns=monthly_prices.columns)
    held_weights = target_weights.copy()
    gross_return = pd.Series(0.0, index=monthly_prices.index)
    formation_traded_notional = pd.Series(0.0, index=monthly_prices.index)
    previous_weights = pd.Series(0.0, index=monthly_prices.columns)

    for position, date in enumerate(monthly_prices.index):
        held_weights.loc[date] = previous_weights
        period_returns = asset_returns.loc[date]
        missing = previous_weights.ne(0) & period_returns.isna()
        if missing.any():
            first_ticker = missing.loc[missing].index[0]
            raise ValueError(
                f"Missing return for held security {first_ticker} at {date}. "
                "Resolve listings, delistings, and data gaps before backtesting."
            )
        safe_returns = period_returns.where(previous_weights.ne(0), 0.0)
        period_gross_return = (previous_weights * safe_returns).sum()
        gross_return.loc[date] = period_gross_return
        drifted_weights = previous_weights * (1 + safe_returns) / (1 + period_gross_return)
        current_weights = proposed_weights.loc[date] if scheduled[position] else drifted_weights
        formation_traded_notional.loc[date] = current_weights.sub(drifted_weights).abs().sum()
        target_weights.loc[date] = current_weights
        previous_weights = current_weights

    charged_traded_notional = formation_traded_notional.shift(1).fillna(0.0)
    trading_cost = charged_traded_notional * one_way_bps / 10_000
    short_exposure = held_weights.clip(upper=0).abs().sum(axis=1)
    borrow_cost = short_exposure * annual_short_borrow_bps / 10_000 / 12
    net_return = gross_return - trading_cost - borrow_cost

    returns = pd.DataFrame(
        {
            "gross_return": gross_return,
            "ranked_securities": signals.notna().sum(axis=1).shift(1).fillna(0).astype(int),
            "long_positions": held_weights.gt(0).sum(axis=1),
            "short_positions": held_weights.lt(0).sum(axis=1),
            "traded_notional": charged_traded_notional,
            "trading_cost": trading_cost,
            "borrow_cost": borrow_cost,
            "net_return": net_return,
        }
    )
    active = held_weights.abs().sum(axis=1).gt(0)
    returns = returns.loc[active]
    return BacktestResult(returns=returns, target_weights=target_weights, signals=signals)
