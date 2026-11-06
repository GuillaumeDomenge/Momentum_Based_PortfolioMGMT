import argparse
import itertools
import json
from pathlib import Path

import pandas as pd

from quant_momentum.backtest import BacktestResult, run_backtest
from quant_momentum.config import load_config
from quant_momentum.data import load_price_panel, to_monthly_prices
from quant_momentum.reporting import strategy_summary
from quant_momentum.universe import eligibility_panel

PARAMETER_NAMES = (
    "lookback_months",
    "skip_months",
    "max_positions",
    "rebalance_months",
)


def parameter_grid(grid: dict) -> list[dict]:
    """Expand a deterministic Cartesian parameter grid."""
    missing = set(PARAMETER_NAMES).difference(grid)
    if missing:
        raise ValueError(f"Optimization grid missing parameters: {sorted(missing)}")
    values = [grid[name] for name in PARAMETER_NAMES]
    return [dict(zip(PARAMETER_NAMES, combination)) for combination in itertools.product(*values)]


def select_best_candidate(results: pd.DataFrame, objective: str) -> pd.Series:
    """Select using training metrics only, with deterministic tie-breakers."""
    valid = results.loc[results["status"].eq("ok") & results[objective].notna()].copy()
    if valid.empty:
        raise ValueError("No valid optimization candidates.")
    return valid.sort_values(
        [objective, "net_cagr", "average_monthly_traded_notional"],
        ascending=[False, False, True],
    ).iloc[0]


def optimize_training_period(
    monthly_prices: pd.DataFrame,
    eligibility: pd.DataFrame | None,
    *,
    train_start: str,
    train_end: str,
    grid: dict,
    strategy: dict,
    costs: dict,
    evaluation: dict,
    objective: str,
) -> tuple[pd.DataFrame, dict]:
    """Fit parameters solely on observations at or before train_end."""
    start = pd.Timestamp(train_start)
    cutoff = pd.Timestamp(train_end)
    if start > cutoff:
        raise ValueError("train_start must not be after train_end.")
    train_prices = monthly_prices.loc[:cutoff]
    train_eligibility = eligibility.loc[:cutoff] if eligibility is not None else None
    rows = []
    for candidate_id, parameters in enumerate(parameter_grid(grid), start=1):
        row = {"candidate_id": candidate_id, **parameters, "status": "ok", "error": ""}
        try:
            result = run_backtest(
                train_prices,
                eligibility=train_eligibility,
                quantile=strategy["quantile"],
                long_only=strategy["long_only"],
                one_way_bps=costs["one_way_bps"],
                annual_short_borrow_bps=costs["annual_short_borrow_bps"],
                **parameters,
            )
            evaluation_returns = result.returns.loc[
                (result.returns.index >= start) & (result.returns.index <= cutoff)
            ]
            if evaluation_returns.empty:
                raise ValueError("Candidate has no returns in the common training window.")
            summary = strategy_summary(
                evaluation_returns,
                periods_per_year=evaluation["annualization_factor"],
                risk_free_annual_rate=evaluation["risk_free_annual_rate"],
            )
            row.update(summary.to_dict())
        except ValueError as error:
            row.update({"status": "invalid", "error": str(error)})
        rows.append(row)
    results = pd.DataFrame(rows)
    selected = select_best_candidate(results, objective)
    parameters = {name: int(selected[name]) for name in PARAMETER_NAMES}
    return results.sort_values(objective, ascending=False, na_position="last"), parameters


def split_result(
    result: BacktestResult, train_start: str, train_end: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split returns chronologically without randomization."""
    start = pd.Timestamp(train_start)
    cutoff = pd.Timestamp(train_end)
    train = result.returns.loc[
        (result.returns.index >= start) & (result.returns.index <= cutoff)
    ]
    test = result.returns.loc[result.returns.index > cutoff]
    if train.empty or test.empty:
        raise ValueError("Both training and test periods must contain returns.")
    return train, test


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and test momentum parameters.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration.")
    parser.add_argument("--output", default="reports/optimization", help="Output directory.")
    args = parser.parse_args()

    config = load_config(args.config)
    prices = load_price_panel(config["data"]["price_file"])
    monthly_prices = to_monthly_prices(prices)
    eligibility = None
    if config["data"].get("universe_mode") == "annual_lagged_sp500":
        membership = pd.read_csv(
            config["data"]["membership_file"], parse_dates=["membership_date"]
        )
        eligibility = eligibility_panel(monthly_prices, membership)

    optimization = config["optimization"]
    grid_results, selected = optimize_training_period(
        monthly_prices,
        eligibility,
        train_start=optimization["train_start"],
        train_end=optimization["train_end"],
        grid=optimization["grid"],
        strategy=config["strategy"],
        costs=config["costs"],
        evaluation=config["evaluation"],
        objective=optimization["objective"],
    )
    final_result = run_backtest(
        monthly_prices,
        eligibility=eligibility,
        quantile=config["strategy"]["quantile"],
        long_only=config["strategy"]["long_only"],
        one_way_bps=config["costs"]["one_way_bps"],
        annual_short_borrow_bps=config["costs"]["annual_short_borrow_bps"],
        **selected,
    )
    train_returns, test_returns = split_result(
        final_result, optimization["train_start"], optimization["train_end"]
    )
    summary_arguments = {
        "periods_per_year": config["evaluation"]["annualization_factor"],
        "risk_free_annual_rate": config["evaluation"]["risk_free_annual_rate"],
    }
    train_summary = strategy_summary(train_returns, **summary_arguments)
    test_summary = strategy_summary(test_returns, **summary_arguments)
    profitable_training_candidates = int(
        (grid_results["status"].eq("ok") & grid_results["net_cagr"].gt(0)).sum()
    )

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    grid_results.to_csv(output / "training_grid.csv", index=False)
    final_result.returns.to_csv(output / "selected_monthly_returns.csv", index_label="date")
    final_result.target_weights.to_csv(output / "selected_target_weights.csv", index_label="date")
    train_summary.rename("value").to_csv(output / "train_summary.csv", header=True)
    test_summary.rename("value").to_csv(output / "test_summary.csv", header=True)
    selection_record = {
        "selected_parameters": selected,
        "objective": optimization["objective"],
        "train_start_inclusive": optimization["train_start"],
        "train_end_inclusive": optimization["train_end"],
        "test_start_exclusive_of_train_end": True,
        "candidate_count": len(grid_results),
        "profitable_training_candidate_count": profitable_training_candidates,
        "selected_training_net_cagr": float(train_summary["net_cagr"]),
        "selected_training_net_sharpe": float(train_summary["net_sharpe"]),
    }
    (output / "selection.json").write_text(
        json.dumps(selection_record, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Selected on training data: {selected}")
    if profitable_training_candidates == 0:
        print("WARNING: no candidate produced a positive net CAGR in the training window.")
    print("\nTRAIN")
    print(train_summary.to_string())
    print("\nTEST (untouched during selection)")
    print(test_summary.to_string())


if __name__ == "__main__":
    main()
