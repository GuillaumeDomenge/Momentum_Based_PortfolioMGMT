import pandas as pd

from quant_momentum.universe import build_annual_lagged_membership, eligibility_panel


def test_annual_membership_uses_last_snapshot_from_prior_year():
    history = pd.DataFrame(
        {
            "date": ["2023-12-20", "2024-06-01", "2024-12-20"],
            "tickers": ["A,B", "A,C", "C,D"],
        }
    )
    membership = build_annual_lagged_membership(history, 2024, 2025)
    assert set(membership.loc[membership["portfolio_year"] == 2024, "ticker"]) == {"A", "B"}
    assert set(membership.loc[membership["portfolio_year"] == 2025, "ticker"]) == {"C", "D"}


def test_eligibility_panel_changes_only_at_calendar_year_boundary():
    index = pd.to_datetime(["2024-12-31", "2025-01-31"])
    prices = pd.DataFrame(1.0, index=index, columns=["A", "B"])
    membership = pd.DataFrame(
        {"portfolio_year": [2024, 2025], "ticker": ["A", "B"]}
    )
    result = eligibility_panel(prices, membership)
    assert result.loc[index[0]].to_dict() == {"A": True, "B": False}
    assert result.loc[index[1]].to_dict() == {"A": False, "B": True}
