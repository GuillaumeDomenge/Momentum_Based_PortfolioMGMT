import pandas as pd

REQUIRED_PRICE_COLUMNS = {"date", "ticker", "adjusted_close"}


def load_price_panel(path: str) -> pd.DataFrame:
    """Load and validate a long-form adjusted-close panel."""
    prices = pd.read_csv(path, parse_dates=["date"])
    missing = REQUIRED_PRICE_COLUMNS.difference(prices.columns)
    if missing:
        raise ValueError(f"Price data missing required columns: {sorted(missing)}")
    if prices.duplicated(["date", "ticker"]).any():
        raise ValueError("Price data has duplicate date/ticker observations.")
    if (prices["adjusted_close"] <= 0).any():
        raise ValueError("Adjusted prices must be positive.")
    return prices.sort_values(["date", "ticker"]).reset_index(drop=True)


def to_monthly_prices(prices: pd.DataFrame) -> pd.DataFrame:
    """Return month-end prices indexed by date with tickers as columns."""
    return (
        prices.set_index("date")
        .groupby("ticker")["adjusted_close"]
        .resample("ME")
        .last()
        .unstack("ticker")
        .sort_index()
    )
