import pandas as pd

from quant_momentum.legacy import (
    apply_identity_overrides,
    candidate_table,
    match_wrds_identities,
    membership_windows,
    openfigi_jobs,
    update_unresolved_audit,
)


def test_membership_windows_preserve_source_notation():
    history = pd.DataFrame(
        {
            "date": pd.to_datetime(["2000-01-01", "2000-02-01", "2000-03-01"]),
            "tickers": ["A,OLD.A", "OLD.A,B", "B,C"],
        }
    )

    windows = membership_windows(history, {"OLD-A", "MISSING"}).set_index("ticker")

    assert windows.loc["OLD-A", "source_ticker"] == "OLD.A"
    assert windows.loc["OLD-A", "first_membership_date"] == pd.Timestamp("2000-01-01")
    assert windows.loc["OLD-A", "last_membership_date"] == pd.Timestamp("2000-02-01")
    assert pd.isna(windows.loc["MISSING", "first_membership_date"])


def test_candidate_table_keeps_matches_as_unverified_candidates():
    windows = pd.DataFrame(
        {
            "ticker": ["OLD", "NONE"],
            "source_ticker": ["OLD", "NONE"],
            "first_membership_date": pd.to_datetime(["2000-01-01", "2000-01-01"]),
            "last_membership_date": pd.to_datetime(["2005-01-01", "2005-01-01"]),
        }
    )
    results = [
        {
            "data": [
                {
                    "name": "OLD COMPANY",
                    "ticker": "OLD",
                    "figi": "FIGI1",
                    "compositeFIGI": "COMP1",
                    "shareClassFIGI": "SHARE1",
                    "exchCode": "US",
                    "securityType2": "Common Stock",
                }
            ]
        },
        {"error": "No identifier found."},
    ]

    candidates = candidate_table(windows, results).set_index("ticker")

    assert candidates.loc["OLD", "candidate_status"] == "single_identity_candidate"
    assert candidates.loc["OLD", "openfigi_name"] == "OLD COMPANY"
    assert candidates.loc["NONE", "candidate_status"] == "no_exact_us_common_stock_match"
    assert openfigi_jobs(windows)[0]["includeUnlistedEquities"] is True


def test_wrds_identity_match_requires_ticker_and_membership_date_overlap():
    windows = pd.DataFrame(
        {
            "ticker": ["OLD", "REUSE"],
            "source_ticker": ["OLD", "REUSE"],
            "first_membership_date": pd.to_datetime(["2000-01-01", "2000-01-01"]),
            "last_membership_date": pd.to_datetime(["2005-01-01", "2005-01-01"]),
        }
    )
    records = pd.DataFrame(
        {
            "permno": ["10001", "10002", "10003"],
            "wrds_company": ["OLD COMPANY", "NEW REUSE", "HISTORICAL REUSE"],
            "wrds_tickers": ["FIRST, OLD", "REUSE", "REUSE"],
            "wrds_start": pd.to_datetime(["1999-01-01", "2020-01-01", "1998-01-01"]),
            "wrds_end": pd.to_datetime(["2006-01-01", "2025-01-01", "2004-01-01"]),
        }
    )

    matches = match_wrds_identities(windows, records).set_index("ticker")

    assert matches.loc["OLD", "permno"] == "10001"
    assert matches.loc["REUSE", "permno"] == "10003"
    assert (matches["wrds_identity_status"] == "single_date_matched_wrds_identity").all()


def test_wrds_identity_match_clips_predecessors_before_research_start():
    windows = pd.DataFrame(
        {
            "ticker": ["SAME"],
            "source_ticker": ["SAME"],
            "first_membership_date": pd.to_datetime(["1996-01-01"]),
            "last_membership_date": pd.to_datetime(["2005-01-01"]),
        }
    )
    records = pd.DataFrame(
        {
            "permno": ["10001", "10002"],
            "wrds_company": ["PREDECESSOR", "RELEVANT COMPANY"],
            "wrds_tickers": ["SAME", "SAME"],
            "wrds_start": pd.to_datetime(["1996-01-01", "1999-01-01"]),
            "wrds_end": pd.to_datetime(["1998-12-31", "2005-01-01"]),
        }
    )

    matches = match_wrds_identities(
        windows, records, research_start=pd.Timestamp("1999-01-01")
    ).set_index("ticker")

    assert matches.loc["SAME", "permno"] == "10002"
    assert matches.loc["SAME", "wrds_company"] == "RELEVANT COMPANY"


def test_identity_overrides_and_audit_do_not_create_price_aliases():
    candidates = pd.DataFrame(
        {
            "ticker": ["WRDS", "MANUAL"],
            "wrds_identity_status": [
                "single_date_matched_wrds_identity",
                "no_date_matched_wrds_identity",
            ],
            "wrds_company": ["WRDS COMPANY", ""],
        }
    )
    overrides = pd.DataFrame(
        {
            "ticker": ["MANUAL"],
            "name": ["MANUAL COMPANY"],
            "cik": ["0000000001"],
            "evidence": ["SEC filing"],
        }
    )
    resolved = apply_identity_overrides(candidates, overrides)
    audit = pd.DataFrame(
        {
            "ticker": ["WRDS", "MANUAL"],
            "resolution_status": ["unidentified_legacy_symbol"] * 2,
            "cik": ["", ""],
            "name": ["", ""],
            "identity_source": ["", ""],
        }
    )

    updated = update_unresolved_audit(audit, resolved).set_index("ticker")

    assert updated.loc["WRDS", "name"] == "WRDS COMPANY"
    assert updated.loc["MANUAL", "name"] == "MANUAL COMPANY"
    assert updated.loc["MANUAL", "cik"] == "0000000001"
    assert (updated["resolution_status"] == "identified_no_safe_price_alias").all()
