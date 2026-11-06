import numpy as np
import pandas as pd

from quant_momentum.backtest import BacktestResult
from quant_momentum.optimize import (
    optimize_training_period,
    parameter_grid,
    select_best_candidate,
    split_result,
)


def test_parameter_grid_expands_all_combinations():
    grid = {
        "lookback_months": [6, 12],
        "skip_months": [1],
        "max_positions": [10, 30],
        "rebalance_months": [1, 3],
    }
    assert len(parameter_grid(grid)) == 8


def test_selection_uses_requested_training_objective():
    results = pd.DataFrame(
        {
            "status": ["ok", "ok"],
            "net_sharpe": [0.2, 0.5],
            "net_cagr": [0.3, 0.1],
            "average_monthly_traded_notional": [1.0, 2.0],
        }
    )
    assert select_best_candidate(results, "net_sharpe").name == 1


def test_result_split_is_strictly_chronological():
    dates = pd.to_datetime(["2022-12-31", "2023-01-31"])
    returns = pd.DataFrame({"net_return": [0.1, 0.2]}, index=dates)
    result = BacktestResult(returns, pd.DataFrame(), pd.DataFrame())
    train, test = split_result(result, "2022-01-01", "2022-12-31")
    assert list(train.index) == [dates[0]]
    assert list(test.index) == [dates[1]]


def test_post_cutoff_prices_cannot_change_selected_parameters():
    dates = pd.date_range("2020-01-31", periods=30, freq="ME")
    prices = pd.DataFrame(
        {
            "A": 100 * np.cumprod(np.repeat(1.03, len(dates))),
            "B": 100 * np.cumprod(np.repeat(1.01, len(dates))),
            "C": 100 * np.cumprod(np.repeat(0.99, len(dates))),
            "D": 100 * np.cumprod(np.repeat(0.97, len(dates))),
        },
        index=dates,
    )
    altered = prices.copy()
    altered.loc[dates[20]:, "A"] *= 100
    arguments = {
        "eligibility": None,
        "train_start": str(dates[5].date()),
        "train_end": str(dates[19].date()),
        "grid": {
            "lookback_months": [3, 4],
            "skip_months": [1],
            "max_positions": [2],
            "rebalance_months": [1],
        },
        "strategy": {"quantile": 0.25, "long_only": False},
        "costs": {"one_way_bps": 10, "annual_short_borrow_bps": 30},
        "evaluation": {"annualization_factor": 12, "risk_free_annual_rate": 0.0},
        "objective": "net_sharpe",
    }
    _, selected = optimize_training_period(prices, **arguments)
    _, altered_selected = optimize_training_period(altered, **arguments)
    assert selected == altered_selected
