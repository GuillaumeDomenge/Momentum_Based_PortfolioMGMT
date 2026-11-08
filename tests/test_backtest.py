import numpy as np
import pandas as pd
import pytest

from quant_momentum.backtest import run_backtest


def test_backtest_lags_weights_and_reconciles_costs():
    dates = pd.date_range("2018-01-31", periods=24, freq="ME")
    monthly_growth = np.array([1.02, 1.01, 1.00, 0.99])
    prices = pd.DataFrame(
        {f"S{i}": 100 * np.cumprod(np.repeat(growth, len(dates))) for i, growth in enumerate(monthly_growth)},
        index=dates,
    )
    result = run_backtest(
        prices,
        lookback_months=4,
        skip_months=1,
        quantile=0.25,
        one_way_bps=10,
        annual_short_borrow_bps=0,
    )

    assert not result.returns.empty
    assert (result.returns["gross_return"] > 0).all()
    expected_net = result.returns["gross_return"] - result.returns["trading_cost"]
    pd.testing.assert_series_equal(result.returns["net_return"], expected_net, check_names=False)


def test_backtest_rejects_internal_gap_for_held_security():
    dates = pd.date_range("2018-01-31", periods=12, freq="ME")
    prices = pd.DataFrame(
        {
            "A": 100 * np.cumprod(np.repeat(1.02, len(dates))),
            "B": 100 * np.cumprod(np.repeat(1.01, len(dates))),
            "C": 100 * np.cumprod(np.repeat(1.00, len(dates))),
            "D": 100 * np.cumprod(np.repeat(0.99, len(dates))),
        },
        index=dates,
    )
    prices.loc[dates[-2], "A"] = np.nan

    with pytest.raises(ValueError, match="Missing return for held security A"):
        run_backtest(prices, lookback_months=4, skip_months=1, quantile=0.25)


def test_backtest_liquidates_terminal_listing_at_last_price():
    dates = pd.date_range("2018-01-31", periods=12, freq="ME")
    prices = pd.DataFrame(
        {
            "A": 100 * np.cumprod(np.repeat(1.02, len(dates))),
            "B": 100 * np.cumprod(np.repeat(1.01, len(dates))),
            "C": 100 * np.cumprod(np.repeat(1.00, len(dates))),
            "D": 100 * np.cumprod(np.repeat(0.99, len(dates))),
        },
        index=dates,
    )
    last_price = prices.loc[dates[-2], "A"]
    prices.loc[dates[-1], "A"] = np.nan

    result = run_backtest(
        prices,
        lookback_months=4,
        skip_months=1,
        quantile=0.25,
        one_way_bps=10,
        annual_short_borrow_bps=0,
    )

    event = result.terminal_liquidations.iloc[0]
    assert event["ticker"] == "A"
    assert event["liquidation_date"] == dates[-1]
    assert event["last_price_date"] == dates[-2]
    assert event["liquidation_price"] == pytest.approx(last_price)
    assert result.returns.loc[dates[-1], "terminal_liquidations"] == 1
    assert result.returns.loc[dates[-1], "terminal_liquidation_notional"] == pytest.approx(
        abs(event["starting_weight"])
    )
    assert result.target_weights.loc[dates[-1], "A"] == 0
    assert result.returns.loc[dates[-1], "traded_notional"] > 0


def test_quarterly_rebalance_has_no_intermediate_trades():
    dates = pd.date_range("2018-01-31", periods=18, freq="ME")
    prices = pd.DataFrame(
        {
            "A": 100 * np.cumprod(np.repeat(1.03, len(dates))),
            "B": 100 * np.cumprod(np.repeat(1.01, len(dates))),
            "C": 100 * np.cumprod(np.repeat(0.99, len(dates))),
            "D": 100 * np.cumprod(np.repeat(0.97, len(dates))),
        },
        index=dates,
    )
    result = run_backtest(
        prices,
        lookback_months=4,
        skip_months=1,
        quantile=0.25,
        rebalance_months=3,
    )
    charged_rebalance_months = result.returns.index.month.isin([2, 5, 8, 11])
    assert result.returns.loc[~charged_rebalance_months, "traded_notional"].eq(0).all()
