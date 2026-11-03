import pandas as pd

from quant_momentum.portfolio import decile_weights, turnover


def test_empty_signal_produces_zero_weights():
    weights = decile_weights(pd.Series({"A": float("nan"), "B": float("nan")}))
    assert weights.eq(0).all()


def test_long_short_weights_have_unit_exposure_on_each_side():
    signal = pd.Series({f"S{i}": float(i) for i in range(20)})
    weights = decile_weights(signal, quantile=0.10)
    assert weights.clip(lower=0).sum() == 1
    assert weights.clip(upper=0).sum() == -1


def test_turnover_measures_total_traded_notional():
    previous = pd.Series({"A": 0.5, "B": -0.5})
    current = pd.Series({"A": 0.0, "B": 0.0})
    assert turnover(previous, current) == 1.0
