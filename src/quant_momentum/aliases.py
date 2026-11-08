from pathlib import Path

import pandas as pd


def load_aliases(path: str | Path) -> pd.DataFrame:
    """Load and validate explicitly researched same-security ticker aliases."""
    aliases = pd.read_csv(path, dtype={"cik": str})
    required = {"historical_ticker", "canonical_ticker", "cik", "evidence"}
    if not required.issubset(aliases.columns):
        raise ValueError(f"Alias file must contain {sorted(required)}.")
    if aliases["historical_ticker"].duplicated().any():
        raise ValueError("Alias file contains duplicate historical tickers.")
    if (aliases["historical_ticker"] == aliases["canonical_ticker"]).any():
        raise ValueError("Historical and canonical tickers must differ.")
    return aliases


def apply_aliases(prices: pd.DataFrame, aliases: pd.DataFrame) -> pd.DataFrame:
    """Copy complete canonical histories under verified historical ticker names."""
    frames = [prices.loc[~prices["ticker"].isin(aliases["historical_ticker"])] ]
    available = set(prices["ticker"].unique())
    missing = sorted(set(aliases["canonical_ticker"]).difference(available))
    if missing:
        raise ValueError(f"Canonical alias histories are unavailable: {missing}")
    for row in aliases.itertuples(index=False):
        history = prices.loc[prices["ticker"].eq(row.canonical_ticker)].copy()
        history["ticker"] = row.historical_ticker
        frames.append(history)
    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(["date", "ticker"], keep="last")
        .sort_values(["date", "ticker"])
        .reset_index(drop=True)
    )


def alias_source_rows(prices: pd.DataFrame, aliases: pd.DataFrame) -> pd.DataFrame:
    """Create provenance rows for aliased histories."""
    rows = []
    for row in aliases.itertuples(index=False):
        history = prices.loc[prices["ticker"].eq(row.historical_ticker)]
        rows.append(
            {
                "ticker": row.historical_ticker,
                "source": f"alias:{row.canonical_ticker}",
                "first_observation": history["date"].min(),
                "last_observation": history["date"].max(),
                "observations": len(history),
            }
        )
    return pd.DataFrame(rows)
