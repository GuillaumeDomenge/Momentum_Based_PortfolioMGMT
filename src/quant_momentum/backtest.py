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

    signals = momentum_12_1(monthly_prices, lookback_months, skip_months)
    if eligibility is not None:
        eligibility = eligibility.reindex_like(signals).fillna(False).astype(bool)
        signals = signals.where(eligibility)
    target_weights = build_weights(
        signals,
        quantile=quantile,
        long_only=long_only,
        max_positions=max_positions,
    )
    held_weights = target_weights.shift(1).fillna(0.0)
    asset_returns = monthly_prices.pct_change(fill_method=None)

    missing_held_returns = held_weights.ne(0) & asset_returns.isna()
    if missing_held_returns.any().any():
        first_date, first_ticker = missing_held_returns.stack().loc[lambda x: x].index[0]
        raise ValueError(
            f"Missing return for held security {first_ticker} at {first_date}. "
            "Resolve listings, delistings, and data gaps before backtesting."
        )

    gross_return = (held_weights * asset_returns).sum(axis=1, min_count=1).fillna(0.0)
    safe_asset_returns = asset_returns.where(held_weights.ne(0), 0.0)
    drifted_weights = held_weights.mul(1 + safe_asset_returns).div(1 + gross_return, axis=0)
    formation_traded_notional = target_weights.sub(drifted_weights).abs().sum(axis=1)
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
