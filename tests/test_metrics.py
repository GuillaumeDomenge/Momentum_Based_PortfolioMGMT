import numpy as np
import pandas as pd

from quant_momentum.metrics import performance_summary


def test_performance_summary_reconciles_constant_compounding():
    returns = pd.Series(np.repeat(0.01, 12))
    summary = performance_summary(returns)
    assert summary["observations"] == 12
    assert np.isclose(summary["cagr"], 1.01**12 - 1)
    assert summary["max_drawdown"] == 0
