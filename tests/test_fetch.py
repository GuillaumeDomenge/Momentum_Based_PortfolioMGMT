import pandas as pd

from quant_momentum.fetch import _close_panel


def test_close_panel_extracts_multiindex_close():
    columns = pd.MultiIndex.from_product([["Close", "Volume"], ["A", "B"]])
    raw = pd.DataFrame([[10.0, 20.0, 100, 200]], columns=columns)
    result = _close_panel(raw)
    assert list(result.columns) == ["A", "B"]
    assert result.iloc[0].to_dict() == {"A": 10.0, "B": 20.0}
