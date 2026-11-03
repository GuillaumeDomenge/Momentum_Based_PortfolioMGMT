import pandas as pd


def decile_weights(signal: pd.Series, quantile: float = 0.10, long_only: bool = False) -> pd.Series:
    """Equal-weight tail portfolios; returns zero weights where signal is missing."""
    if not 0 < quantile <= 0.5:
        raise ValueError("quantile must be in (0, 0.5].")
    valid = signal.dropna()
    weights = pd.Series(0.0, index=signal.index)
    if len(valid) < 2:
        return weights
    count = max(1, int(len(valid) * quantile))
    longs = valid.nlargest(count).index
    weights.loc[longs] = 1 / len(longs)
    if not long_only:
        shorts = valid.nsmallest(count).index
        weights.loc[shorts] = -1 / len(shorts)
    return weights


def turnover(previous: pd.Series, current: pd.Series) -> float:
    """Traded notional as a fraction of portfolio equity."""
    return current.sub(previous, fill_value=0).abs().sum()


def build_weights(signals: pd.DataFrame, quantile: float = 0.10, long_only: bool = False) -> pd.DataFrame:
    """Convert each cross-section of signals into target portfolio weights."""
    return signals.apply(decile_weights, axis=1, quantile=quantile, long_only=long_only)
