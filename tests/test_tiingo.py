import pandas as pd

from quant_momentum.tiingo import (
    download_tiingo_prices,
    merge_price_sources,
    missing_tickers,
)


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return [{"date": "2020-01-02T00:00:00.000Z", "adjClose": 12.5}]


class FakeSession:
    def get(self, *args, **kwargs):
        return FakeResponse()


def test_tiingo_response_is_normalized_to_project_schema():
    result = download_tiingo_prices(
        "OLD", "2020-01-01", "2021-01-01", "secret", session=FakeSession()
    )
    assert result.iloc[0].to_dict() == {
        "date": pd.Timestamp("2020-01-02"),
        "ticker": "OLD",
        "adjusted_close": 12.5,
    }


def test_missing_tickers_compares_membership_with_yahoo_history():
    membership = pd.DataFrame({"ticker": ["A", "B", "C"]})
    yahoo = pd.DataFrame({"ticker": ["A", "C"]})
    assert missing_tickers(membership, yahoo) == ["B"]


def test_tiingo_history_replaces_yahoo_for_same_ticker():
    yahoo = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-01"]),
            "ticker": ["A", "B"],
            "adjusted_close": [10.0, 20.0],
        }
    )
    tiingo = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01"]),
            "ticker": ["B"],
            "adjusted_close": [21.0],
        }
    )
    combined, sources = merge_price_sources(yahoo, tiingo)
    assert combined.loc[combined["ticker"] == "B", "adjusted_close"].item() == 21.0
    assert sources.set_index("ticker").loc["B", "source"] == "tiingo"
