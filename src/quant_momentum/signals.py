import pandas as pd


def momentum_12_1(monthly_prices: pd.DataFrame, lookback: int = 12, skip: int = 1) -> pd.DataFrame:
    """Compute trailing momentum excluding the latest `skip` monthly returns.

    Signal at month t is formed only from prices observed through t-skip.
    """
    if lookback <= skip:
        raise ValueError("lookback must exceed skip.")
    return monthly_prices.shift(skip).pct_change(lookback - skip, fill_method=None)
