import pandas as pd


def to_yahoo_symbol(symbol: str) -> str:
    """Translate the common dot class-share notation to Yahoo's dash notation."""
    return symbol.strip().replace(".", "-")


def build_annual_lagged_membership(
    history: pd.DataFrame, start_year: int, end_year: int
) -> pd.DataFrame:
    """Use the final available prior-year S&P 500 snapshot for each portfolio year."""
    required = {"date", "tickers"}
    if not required.issubset(history.columns):
        raise ValueError(f"Membership history must contain {sorted(required)}.")
    history = history.copy()
    history["date"] = pd.to_datetime(history["date"])
    history = history.sort_values("date")

    records: list[dict] = []
    for portfolio_year in range(start_year, end_year + 1):
        cutoff = pd.Timestamp(portfolio_year - 1, 12, 31)
        eligible_snapshots = history.loc[history["date"] <= cutoff]
        if eligible_snapshots.empty:
            raise ValueError(f"No S&P 500 snapshot available by {cutoff.date()}.")
        snapshot = eligible_snapshots.iloc[-1]
        source_symbols = sorted(set(snapshot["tickers"].split(",")))
        records.extend(
            {
                "portfolio_year": portfolio_year,
                "membership_date": snapshot["date"],
                "ticker": to_yahoo_symbol(symbol),
                "source_ticker": symbol,
            }
            for symbol in source_symbols
        )
    return pd.DataFrame.from_records(records).sort_values(
        ["portfolio_year", "ticker"]
    ).reset_index(drop=True)


def eligibility_panel(
    monthly_prices: pd.DataFrame, membership: pd.DataFrame
) -> pd.DataFrame:
    """Align annual membership records with a monthly price matrix."""
    required = {"portfolio_year", "ticker"}
    if not required.issubset(membership.columns):
        raise ValueError(f"Membership data must contain {sorted(required)}.")
    eligible = pd.DataFrame(False, index=monthly_prices.index, columns=monthly_prices.columns)
    for year, group in membership.groupby("portfolio_year"):
        rows = eligible.index.year == int(year)
        columns = eligible.columns.intersection(group["ticker"])
        eligible.loc[rows, columns] = True
    return eligible
