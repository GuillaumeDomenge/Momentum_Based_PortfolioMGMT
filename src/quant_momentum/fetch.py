import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from quant_momentum.config import load_config
from quant_momentum.universe import build_annual_lagged_membership


def _close_panel(download: pd.DataFrame) -> pd.DataFrame:
    """Extract auto-adjusted closes from yfinance's stable MultiIndex shape."""
    if download.empty:
        raise ValueError("yfinance returned no price data.")
    if not isinstance(download.columns, pd.MultiIndex):
        if "Close" not in download:
            raise ValueError("yfinance response has no Close field.")
        return download[["Close"]]
    if "Close" not in download.columns.get_level_values(0):
        raise ValueError("yfinance response has no Close field.")
    return download["Close"]


def download_yfinance_prices(
    tickers: list[str], start: str, end: str, *, strict: bool = True
) -> pd.DataFrame:
    """Download daily total-return-adjusted closes in the project's long schema."""
    if not tickers:
        raise ValueError("At least one ticker is required.")
    raw = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=True,
        repair=True,
        keepna=True,
        actions=False,
        threads=True,
        group_by="column",
        progress=False,
        multi_level_index=True,
    )
    closes = _close_panel(raw)
    if len(tickers) == 1:
        closes.columns = [tickers[0]]
    closes.columns = closes.columns.astype(str)

    missing = sorted(set(tickers).difference(closes.columns))
    empty = sorted(ticker for ticker in tickers if ticker in closes and closes[ticker].isna().all())
    if strict and (missing or empty):
        raise ValueError(f"No usable yfinance history for: {sorted(set(missing + empty))}")

    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    prices = (
        closes.rename_axis(index="date", columns="ticker")
        .stack(future_stack=True)
        .dropna()
        .rename("adjusted_close")
        .reset_index()
    )
    return prices.sort_values(["date", "ticker"]).reset_index(drop=True)


def download_in_batches(
    tickers: list[str], start: str, end: str, batch_size: int = 100
) -> tuple[pd.DataFrame, list[str]]:
    """Download a broad historical universe while retaining a coverage audit."""
    batches = []
    for offset in range(0, len(tickers), batch_size):
        batch = tickers[offset : offset + batch_size]
        try:
            prices = download_yfinance_prices(batch, start, end, strict=False)
        except ValueError:
            continue
        batches.append(prices)
    if not batches:
        raise ValueError("yfinance returned no usable data for the requested universe.")
    combined = pd.concat(batches, ignore_index=True).drop_duplicates(["date", "ticker"])
    available = set(combined["ticker"].unique())
    unavailable = sorted(set(tickers).difference(available))
    return combined.sort_values(["date", "ticker"]).reset_index(drop=True), unavailable


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch adjusted daily closes from yfinance.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration.")
    args = parser.parse_args()

    config = load_config(args.config)
    data_config = config["data"]
    if data_config.get("source") not in {"yfinance", "yfinance_tiingo"}:
        raise ValueError("This fetcher requires a yfinance-based data source.")

    if data_config.get("universe_mode") != "annual_lagged_sp500":
        raise ValueError("Expected data.universe_mode: annual_lagged_sp500.")
    history = pd.read_csv(data_config["membership_history_url"], parse_dates=["date"])
    history_output = Path(data_config["membership_history_file"])
    history_output.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(history_output, index=False)
    start_year = int(data_config.get("portfolio_start_year", pd.Timestamp(data_config["start"]).year))
    end_year = pd.Timestamp(data_config["end"]).year
    membership = build_annual_lagged_membership(history, start_year, end_year)
    membership_output = Path(data_config["membership_file"])
    membership_output.parent.mkdir(parents=True, exist_ok=True)
    membership.to_csv(membership_output, index=False)
    tickers = sorted(membership["ticker"].unique())

    prices, unavailable = download_in_batches(
        tickers=tickers, start=data_config["start"], end=data_config["end"]
    )
    available = set(prices["ticker"].unique())
    coverage = (
        membership.assign(price_history_available=membership["ticker"].isin(available))
        .groupby("portfolio_year")
        .agg(
            requested_tickers=("ticker", "size"),
            available_tickers=("price_history_available", "sum"),
        )
        .reset_index()
    )
    coverage["coverage_ratio"] = (
        coverage["available_tickers"] / coverage["requested_tickers"]
    )
    coverage_output = Path(data_config["membership_coverage_file"])
    coverage_output.parent.mkdir(parents=True, exist_ok=True)
    coverage.to_csv(coverage_output, index=False)
    yahoo_output = Path(data_config.get("yahoo_price_file", data_config["price_file"]))
    yahoo_output.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(yahoo_output, index=False)
    canonical_output = Path(data_config["price_file"])
    canonical_output.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(canonical_output, index=False)

    manifest = {
        "source": "yfinance/Yahoo Finance",
        "yfinance_version": yf.__version__,
        "auto_adjust": True,
        "repair": True,
        "requested_start": data_config["start"],
        "requested_end_exclusive": data_config["end"],
        "universe_method": "final prior-calendar-year S&P 500 snapshot",
        "membership_source": data_config["membership_history_url"],
        "requested_tickers": len(tickers),
        "available_tickers": prices["ticker"].nunique(),
        "unavailable_tickers": unavailable,
        "annual_membership_coverage": coverage.to_dict(orient="records"),
        "rows": len(prices),
        "first_observation": prices["date"].min().date().isoformat(),
        "last_observation": prices["date"].max().date().isoformat(),
        "fetched_at_utc": datetime.now(UTC).isoformat(),
        "research_warning": (
            "Open-source reconstructed membership and Yahoo price coverage are incomplete; "
            "unavailable and delisted symbols require institutional data for final research."
        ),
    }
    manifest_text = json.dumps(manifest, indent=2) + "\n"
    yahoo_output.with_suffix(".manifest.json").write_text(manifest_text, encoding="utf-8")
    canonical_output.with_suffix(".manifest.json").write_text(manifest_text, encoding="utf-8")
    print(
        f"Wrote {len(prices):,} observations for {prices['ticker'].nunique()} of "
        f"{len(tickers)} requested tickers to {yahoo_output}; {len(unavailable)} unavailable."
    )


if __name__ == "__main__":
    main()
