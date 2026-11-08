import argparse
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from quant_momentum.config import load_config

OPENFIGI_MAPPING_URL = "https://api.openfigi.com/v3/mapping"
OPENFIGI_BATCH_SIZE = 10
WRDS_MEMBERSHIP_URL = "https://wrds-www.wharton.upenn.edu/classroom/sp500-introduction/over-time/"
UNIDENTIFIED_STATUS = "unidentified_legacy_symbol"


def membership_windows(history: pd.DataFrame, tickers: set[str]) -> pd.DataFrame:
    """Return the first and last S&P snapshot containing each legacy ticker."""
    required = {"date", "tickers"}
    if not required.issubset(history.columns):
        raise ValueError(f"Membership history must contain {sorted(required)}.")

    dates: dict[str, list[pd.Timestamp]] = {ticker: [] for ticker in tickers}
    source_symbols: dict[str, str] = {}
    for row in history.itertuples(index=False):
        date = pd.Timestamp(row.date)
        for source_symbol in str(row.tickers).split(","):
            normalized = source_symbol.strip().replace(".", "-")
            if normalized in dates:
                dates[normalized].append(date)
                source_symbols.setdefault(normalized, source_symbol.strip())

    rows = []
    for ticker in sorted(tickers):
        observed = dates[ticker]
        rows.append(
            {
                "ticker": ticker,
                "source_ticker": source_symbols.get(ticker, ticker),
                "first_membership_date": min(observed) if observed else pd.NaT,
                "last_membership_date": max(observed) if observed else pd.NaT,
            }
        )
    return pd.DataFrame(rows)


def openfigi_jobs(windows: pd.DataFrame) -> list[dict[str, object]]:
    """Build exact U.S. ticker jobs, retaining source notation for share classes."""
    jobs = []
    for row in windows.itertuples(index=False):
        jobs.append(
            {
                "idType": "TICKER",
                "idValue": row.source_ticker,
                "exchCode": "US",
                "marketSecDes": "Equity",
                "includeUnlistedEquities": True,
            }
        )
    return jobs


def query_openfigi(
    jobs: list[dict[str, object]],
    *,
    session: requests.Session | None = None,
    api_key: str | None = None,
) -> list[dict]:
    """Query OpenFIGI in anonymous-limit batches and return one result per job."""
    client = session or requests.Session()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-OPENFIGI-APIKEY"] = api_key

    results: list[dict] = []
    batch_size = 100 if api_key else OPENFIGI_BATCH_SIZE
    for start in range(0, len(jobs), batch_size):
        response = client.post(
            OPENFIGI_MAPPING_URL,
            json=jobs[start : start + batch_size],
            headers=headers,
            timeout=30,
        )
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "60"))
            time.sleep(retry_after)
            response = client.post(
                OPENFIGI_MAPPING_URL,
                json=jobs[start : start + batch_size],
                headers=headers,
                timeout=30,
            )
        response.raise_for_status()
        batch_results = response.json()
        if len(batch_results) != len(jobs[start : start + batch_size]):
            raise ValueError("OpenFIGI returned a different number of results than jobs.")
        results.extend(batch_results)
    return results


def candidate_table(windows: pd.DataFrame, results: list[dict]) -> pd.DataFrame:
    """Flatten OpenFIGI results without promoting candidates to verified aliases."""
    if len(windows) != len(results):
        raise ValueError("Each legacy ticker must have exactly one OpenFIGI result.")

    rows = []
    for window, result in zip(windows.itertuples(index=False), results, strict=True):
        matches = [
            match
            for match in result.get("data", [])
            if match.get("securityType2") == "Common Stock"
        ]
        if not matches:
            rows.append(
                {
                    **window._asdict(),
                    "candidate_status": "no_exact_us_common_stock_match",
                    "openfigi_name": "",
                    "openfigi_ticker": "",
                    "figi": "",
                    "composite_figi": "",
                    "share_class_figi": "",
                    "exchange": "",
                }
            )
            continue

        identities = {match.get("shareClassFIGI") or match.get("compositeFIGI") for match in matches}
        status = "single_identity_candidate" if len(identities) == 1 else "ambiguous_candidates"
        for match in matches:
            rows.append(
                {
                    **window._asdict(),
                    "candidate_status": status,
                    "openfigi_name": match.get("name", ""),
                    "openfigi_ticker": match.get("ticker", ""),
                    "figi": match.get("figi", ""),
                    "composite_figi": match.get("compositeFIGI", ""),
                    "share_class_figi": match.get("shareClassFIGI", ""),
                    "exchange": match.get("exchCode", ""),
                }
            )
    return pd.DataFrame(rows)


def fetch_wrds_membership(*, session: requests.Session | None = None) -> pd.DataFrame:
    """Read the public CRSP-derived S&P membership tables published by WRDS."""
    client = session or requests.Session()
    response = client.get(
        WRDS_MEMBERSHIP_URL,
        headers={"User-Agent": "quant-equity-momentum/0.1 identity research"},
        timeout=30,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        for html_row in table.find_all("tr")[1:]:
            cells = [cell.get_text(" ", strip=True) for cell in html_row.find_all(["th", "td"])]
            if len(cells) != 6 or not cells[1].isdigit():
                continue
            rows.append(
                {
                    "permno": cells[1],
                    "wrds_company": cells[2],
                    "wrds_tickers": cells[3],
                    "wrds_start": pd.to_datetime(cells[4], errors="coerce"),
                    "wrds_end": pd.to_datetime(cells[5], errors="coerce"),
                }
            )
    if not rows:
        raise ValueError("No membership records found on the WRDS public page.")
    return pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)


def match_wrds_identities(
    windows: pd.DataFrame,
    records: pd.DataFrame,
    *,
    research_start: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Date-match legacy tickers to stable CRSP PERMNO security identities."""
    rows = []
    for window in windows.itertuples(index=False):
        relevant_start = window.first_membership_date
        if research_start is not None:
            relevant_start = max(relevant_start, research_start)
        record_rows = list(records.itertuples(index=False))

        def matching_records(
            ticker: str,
            record_rows: list = record_rows,
            last_membership_date: pd.Timestamp = window.last_membership_date,
            relevant_start: pd.Timestamp = relevant_start,
        ) -> list:
            matches = []
            for record in record_rows:
                record_tickers = {
                    symbol.strip().replace(".", "-")
                    for symbol in str(record.wrds_tickers).split(",")
                }
                record_end = record.wrds_end if pd.notna(record.wrds_end) else pd.Timestamp.max
                if (
                    ticker in record_tickers
                    and record.wrds_start <= last_membership_date
                    and record_end >= relevant_start
                ):
                    matches.append(record)
            return matches

        match_method = "exact_ticker"
        matches = matching_records(window.ticker)
        if not matches and "." in window.source_ticker:
            matches = matching_records(window.source_ticker.split(".", maxsplit=1)[0])
            match_method = "share_class_base_ticker"

        status = "no_date_matched_wrds_identity"
        if len(matches) == 1:
            status = "single_date_matched_wrds_identity"
        elif len(matches) > 1:
            status = "ambiguous_wrds_identities"
        if not matches:
            rows.append(
                {
                    "ticker": window.ticker,
                    "wrds_identity_status": status,
                    "wrds_match_method": "",
                    "permno": "",
                    "wrds_company": "",
                    "wrds_tickers": "",
                    "wrds_start": pd.NaT,
                    "wrds_end": pd.NaT,
                }
            )
        for match in matches:
            rows.append(
                {
                    "ticker": window.ticker,
                    "wrds_identity_status": status,
                    "wrds_match_method": match_method,
                    **match._asdict(),
                }
            )
    return pd.DataFrame(rows)


def apply_identity_overrides(
    candidates: pd.DataFrame, overrides: pd.DataFrame
) -> pd.DataFrame:
    """Combine date-matched identities with a small, evidence-backed override table."""
    required = {"ticker", "name", "cik", "evidence"}
    if not required.issubset(overrides.columns):
        raise ValueError(f"Identity overrides must contain {sorted(required)}.")
    if overrides["ticker"].duplicated().any():
        raise ValueError("Identity overrides contain duplicate tickers.")

    merged = candidates.merge(overrides, on="ticker", how="left")
    wrds_verified = merged["wrds_identity_status"].eq("single_date_matched_wrds_identity")
    manually_verified = merged["name"].notna()
    merged["resolved_name"] = merged["wrds_company"].where(wrds_verified, "")
    merged["identity_status"] = "unresolved_identity"
    merged.loc[wrds_verified, "identity_status"] = "date_verified_wrds_identity"
    merged.loc[wrds_verified, "identity_evidence"] = WRDS_MEMBERSHIP_URL
    merged.loc[manually_verified, "resolved_name"] = merged.loc[manually_verified, "name"]
    merged.loc[manually_verified, "identity_status"] = "manually_verified_identity"
    merged.loc[manually_verified, "identity_evidence"] = merged.loc[
        manually_verified, "evidence"
    ]
    merged["resolved_cik"] = merged["cik"].fillna("")
    return merged.drop(columns=["name", "cik", "evidence"])


def update_unresolved_audit(audit: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    """Promote verified identities while leaving price-alias decisions unresolved."""
    verified = candidates.loc[candidates["identity_status"].ne("unresolved_identity")].copy()
    if verified["ticker"].duplicated().any():
        raise ValueError("Verified identity table must contain one row per ticker.")
    verified = verified.set_index("ticker")
    updated = audit.copy()
    for index, row in updated.iterrows():
        if row["ticker"] not in verified.index:
            continue
        identity = verified.loc[row["ticker"]]
        updated.at[index, "resolution_status"] = "identified_no_safe_price_alias"
        updated.at[index, "name"] = identity["resolved_name"]
        if identity["resolved_cik"]:
            updated.at[index, "cik"] = identity["resolved_cik"]
        updated.at[index, "identity_source"] = identity["identity_evidence"]
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Find identities for unresolved legacy tickers.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration.")
    parser.add_argument(
        "--output",
        default="data/processed/legacy_ticker_candidates.csv",
        help="Candidate audit output.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    data_config = config["data"]
    audit_path = Path(data_config["unresolved_ticker_audit_file"])
    audit = pd.read_csv(audit_path, dtype={"cik": str})
    unresolved = set(
        audit.loc[audit["resolution_status"].eq(UNIDENTIFIED_STATUS), "ticker"]
    )
    history = pd.read_csv(data_config["membership_history_file"], parse_dates=["date"])
    windows = membership_windows(history, unresolved)
    results = query_openfigi(openfigi_jobs(windows))
    candidates = candidate_table(windows, results)
    wrds_matches = match_wrds_identities(
        windows,
        fetch_wrds_membership(),
        research_start=pd.Timestamp(data_config["start"]),
    )
    candidates = candidates.merge(wrds_matches, on="ticker", how="left")
    overrides = pd.read_csv(data_config["legacy_identity_override_file"], dtype={"cik": str})
    candidates = apply_identity_overrides(candidates, overrides)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(output, index=False)
    update_unresolved_audit(audit, candidates).to_csv(audit_path, index=False)
    matched = candidates.loc[candidates["candidate_status"].ne("no_exact_us_common_stock_match")]
    identified = candidates.loc[candidates["identity_status"].ne("unresolved_identity")]
    print(
        f"OpenFIGI returned candidates for {matched['ticker'].nunique()} of "
        f"{len(unresolved)} legacy tickers; {identified['ticker'].nunique()} identities were "
        f"verified. Review {output} before changing aliases."
    )


if __name__ == "__main__":
    main()
