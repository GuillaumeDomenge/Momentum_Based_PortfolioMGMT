import pandas as pd

from quant_momentum.signals import momentum_12_1


def test_momentum_excludes_latest_month():
    dates = pd.date_range("2020-01-31", periods=5, freq="ME")
    prices = pd.DataFrame({"A": [100, 110, 121, 133.1, 146.41]}, index=dates)
    result = momentum_12_1(prices, lookback=3, skip=1)
    assert round(result.iloc[-1, 0], 4) == 0.21
