import pandas as pd
import pytest

from quant_momentum.aliases import apply_aliases


def test_alias_copies_canonical_history_under_historical_symbol():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-02-01"]),
            "ticker": ["NEW", "NEW"],
            "adjusted_close": [10.0, 11.0],
        }
    )
    aliases = pd.DataFrame(
        {"historical_ticker": ["OLD"], "canonical_ticker": ["NEW"]}
    )
    result = apply_aliases(prices, aliases)
    assert result.loc[result["ticker"].eq("OLD"), "adjusted_close"].tolist() == [10.0, 11.0]


def test_alias_rejects_missing_canonical_history():
    prices = pd.DataFrame(columns=["date", "ticker", "adjusted_close"])
    aliases = pd.DataFrame(
        {"historical_ticker": ["OLD"], "canonical_ticker": ["NEW"]}
    )
    with pytest.raises(ValueError, match="Canonical alias histories are unavailable"):
        apply_aliases(prices, aliases)
