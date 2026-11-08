import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from dotenv import load_dotenv

from quant_momentum.aliases import alias_source_rows, apply_aliases, load_aliases
from quant_momentum.config import load_config


def download_tiingo_prices(
    ticker: str,
    start: str,
    end: str,
    token: str,
    *,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Download one complete adjusted-close history from Tiingo."""
    client = session or requests.Session()
    response = client.get(
        f"https://api.tiingo.com/tiingo/daily/{quote(ticker, safe='')}/prices",
        params={"startDate": start, "endDate": end, "resampleFreq": "daily"},
        headers={"Authorization": f"Token {token}", "Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload:
        return pd.DataFrame(columns=["date", "ticker", "adjusted_close"])
    prices = pd.DataFrame(payload)
    required = {"date", "adjClose"}
    if not required.issubset(prices.columns):
        raise ValueError(f"Tiingo response for {ticker} lacks {sorted(required)}.")
    result = pd.DataFrame(
        {
            "date": pd.to_datetime(prices["date"], utc=True).dt.tz_localize(None),
            "ticker": ticker,
            "adjusted_close": pd.to_numeric(prices["adjClose"], errors="coerce"),
        }
    ).dropna()
    return result.sort_values("date").reset_index(drop=True)


def missing_tickers(membership: pd.DataFrame, yahoo_prices: pd.DataFrame) -> list[str]:
    """Return historical members for which Yahoo supplied no observations."""
    requested = set(membership["ticker"].unique())
    available = set(yahoo_prices["ticker"].unique())
    return sorted(requested.difference(available))


def merge_price_sources(
    yahoo_prices: pd.DataFrame, tiingo_prices: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use one vendor per ticker, replacing Yahoo completely when Tiingo is available."""
    tiingo_tickers = set(tiingo_prices["ticker"].unique()) if not tiingo_prices.empty else set()
    yahoo_kept = yahoo_prices.loc[~yahoo_prices["ticker"].isin(tiingo_tickers)]
    combined = (
        pd.concat([yahoo_kept, tiingo_prices], ignore_index=True)
        .drop_duplicates(["date", "ticker"], keep="last")
        .sort_values(["date", "ticker"])
        .reset_index(drop=True)
    )
    source_rows = []
    for ticker, group in combined.groupby("ticker"):
        source_rows.append(
            {
                "ticker": ticker,
                "source": "tiingo" if ticker in tiingo_tickers else "yfinance",
                "first_observation": group["date"].min(),
                "last_observation": group["date"].max(),
                "observations": len(group),
            }
        )
    return combined, pd.DataFrame(source_rows).sort_values("ticker").reset_index(drop=True)


def _safe_cache_name(ticker: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", ticker) + ".csv"


def _load_tiingo_cache(cache_directory: Path) -> pd.DataFrame:
    files = sorted(cache_directory.glob("*.csv"))
    if not files:
        return pd.DataFrame(columns=["date", "ticker", "adjusted_close"])
    return pd.concat(
        [pd.read_csv(path, parse_dates=["date"]) for path in files], ignore_index=True
    )


def write_remaining_queue(
    candidates: list[str],
    cached_tickers: set[str],
    attempts: dict,
    output: str | Path,
) -> pd.DataFrame:
    """Persist every unresolved ticker and whether it has already failed once."""
    rows = []
    for ticker in candidates:
        if ticker in cached_tickers:
            continue
        attempt = attempts.get(ticker, {})
        rows.append(
            {
                "ticker": ticker,
                "status": "failed" if attempt.get("status") == "failed" else "unattempted",
                "last_attempt_utc": attempt.get("attempted_at_utc", ""),
            }
        )
    queue = pd.DataFrame(rows, columns=["ticker", "status", "last_attempt_utc"])
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(destination, index=False)
    return queue


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Fill missing Yahoo histories with Tiingo.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration.")
    parser.add_argument(
        "--max-symbols",
        type=int,
        default=None,
        help="Maximum API requests this run; defaults to the configured safe hourly amount.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report work without API calls.")
    parser.add_argument("--merge-only", action="store_true", help="Merge caches and aliases without API calls.")
    parser.add_argument("--retry-failed", action="store_true", help="Retry prior failed symbols.")
    args = parser.parse_args()

    config = load_config(args.config)
    data_config = config["data"]
    tiingo_config = data_config["tiingo"]
    membership = pd.read_csv(data_config["membership_file"])
    yahoo_prices = pd.read_csv(data_config["yahoo_price_file"], parse_dates=["date"])
    alias_price_path = Path(data_config["alias_canonical_price_file"])
    if alias_price_path.exists():
        alias_prices = pd.read_csv(alias_price_path, parse_dates=["date"])
        yahoo_prices = (
            pd.concat([yahoo_prices, alias_prices], ignore_index=True)
            .drop_duplicates(["date", "ticker"], keep="last")
        )
    aliases = load_aliases(data_config["ticker_alias_file"])
    mapped_tickers = set(aliases["historical_ticker"])
    candidates = [
        ticker
        for ticker in missing_tickers(membership, yahoo_prices)
        if ticker not in mapped_tickers
    ]

    cache_directory = Path(data_config["tiingo_cache_dir"])
    cache_directory.mkdir(parents=True, exist_ok=True)
    attempts_path = cache_directory / "attempts.json"
    attempts = json.loads(attempts_path.read_text(encoding="utf-8")) if attempts_path.exists() else {}
    cached_prices = _load_tiingo_cache(cache_directory)
    cached_tickers = set(cached_prices["ticker"].unique())
    write_remaining_queue(
        candidates,
        cached_tickers,
        attempts,
        data_config["tiingo_remaining_file"],
    )
    pending = [ticker for ticker in candidates if ticker not in cached_tickers]
    if not args.retry_failed:
        pending = [ticker for ticker in pending if attempts.get(ticker, {}).get("status") != "failed"]

    limit = args.max_symbols or int(tiingo_config.get("max_symbols_per_run", 45))
    if limit < 1 or limit > 50:
        raise ValueError("max-symbols must be between 1 and 50.")
    selected = [] if args.merge_only else pending[:limit]
    print(
        f"Tiingo fallback: {len(candidates)} Yahoo-missing tickers; "
        f"{len(cached_tickers)} cached; {len(pending)} pending; {len(selected)} selected."
    )
    if args.dry_run:
        return

    token_variable = tiingo_config["token_environment_variable"]
    token = os.getenv(token_variable)
    if selected and not token:
        raise ValueError(f"Set the {token_variable} environment variable before fetching Tiingo data.")

    for ticker in selected:
        try:
            prices = download_tiingo_prices(
                ticker, data_config["start"], data_config["end"], token
            )
            if prices.empty:
                raise ValueError("Tiingo returned no observations.")
            prices.to_csv(cache_directory / _safe_cache_name(ticker), index=False)
            attempts[ticker] = {
                "status": "ok",
                "observations": len(prices),
                "attempted_at_utc": datetime.now(UTC).isoformat(),
            }
        except (requests.RequestException, ValueError) as error:
            attempts[ticker] = {
                "status": "failed",
                "error": str(error)[:500],
                "attempted_at_utc": datetime.now(UTC).isoformat(),
            }
        attempts_path.write_text(json.dumps(attempts, indent=2) + "\n", encoding="utf-8")

    cached_prices = _load_tiingo_cache(cache_directory)
    cached_tickers = set(cached_prices["ticker"].unique())
    write_remaining_queue(
        candidates,
        cached_tickers,
        attempts,
        data_config["tiingo_remaining_file"],
    )
    combined, sources = merge_price_sources(yahoo_prices, cached_prices)
    combined = apply_aliases(combined, aliases)
    sources = pd.concat(
        [
            sources.loc[~sources["ticker"].isin(mapped_tickers)],
            alias_source_rows(combined, aliases),
        ],
        ignore_index=True,
    ).sort_values("ticker").reset_index(drop=True)
    output = Path(data_config["price_file"])
    output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(output, index=False)
    source_output = Path(data_config["price_source_file"])
    source_output.parent.mkdir(parents=True, exist_ok=True)
    sources.to_csv(source_output, index=False)

    resolved = set(cached_prices["ticker"].unique())
    unresolved = sorted(set(candidates).difference(resolved))
    available = set(combined["ticker"].unique())
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
    coverage.to_csv(data_config["membership_coverage_file"], index=False)
    manifest = {
        "sources": ["yfinance/Yahoo Finance", "Tiingo EOD"],
        "merge_policy": "one vendor per ticker; Tiingo replaces the full Yahoo history",
        "requested_start": data_config["start"],
        "requested_end_exclusive": data_config["end"],
        "yahoo_tickers": int((sources["source"] == "yfinance").sum()),
        "tiingo_tickers": int((sources["source"] == "tiingo").sum()),
        "alias_tickers": len(aliases),
        "unresolved_tickers": unresolved,
        "annual_membership_coverage": coverage.to_dict(orient="records"),
        "rows": len(combined),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "license_warning": "Raw vendor data is for local research and is excluded from Git.",
    }
    output.with_suffix(".manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Merged {sources['ticker'].nunique()} tickers: {len(resolved)} from Tiingo; "
        f"{len(unresolved)} Yahoo-missing tickers remain unresolved."
    )


if __name__ == "__main__":
    main()
