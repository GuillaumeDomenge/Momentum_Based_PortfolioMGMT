import argparse
from pathlib import Path

import pandas as pd

from quant_momentum.backtest import run_backtest
from quant_momentum.config import load_config
from quant_momentum.data import load_price_panel, to_monthly_prices
from quant_momentum.metrics import performance_summary
from quant_momentum.universe import eligibility_panel


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the baseline equity momentum backtest.")
    parser.add_argument("--config", default="config.yaml", help="Path to YAML configuration.")
    parser.add_argument("--output", default="reports/baseline", help="Output directory.")
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
    result = run_backtest(
        monthly_prices,
        eligibility=eligibility,
        lookback_months=config["strategy"]["lookback_months"],
        skip_months=config["strategy"]["skip_months"],
        quantile=config["strategy"]["quantile"],
        max_positions=config["strategy"].get("max_positions"),
        long_only=config["strategy"]["long_only"],
        one_way_bps=config["costs"]["one_way_bps"],
        annual_short_borrow_bps=config["costs"]["annual_short_borrow_bps"],
    )
    gross_summary = performance_summary(
        result.returns["gross_return"],
        periods_per_year=config["evaluation"]["annualization_factor"],
        risk_free_annual_rate=config["evaluation"]["risk_free_annual_rate"],
    ).add_prefix("gross_")
    net_summary = performance_summary(
        result.returns["net_return"],
        periods_per_year=config["evaluation"]["annualization_factor"],
        risk_free_annual_rate=config["evaluation"]["risk_free_annual_rate"],
    ).add_prefix("net_")
    implementation_summary = {
        "average_monthly_traded_notional": result.returns["traded_notional"].mean(),
        "annualized_average_trading_cost": (
            result.returns["trading_cost"].mean()
            * config["evaluation"]["annualization_factor"]
        ),
        "annualized_average_borrow_cost": (
            result.returns["borrow_cost"].mean()
            * config["evaluation"]["annualization_factor"]
        ),
    }
    summary = pd.concat(
        [gross_summary, net_summary, pd.Series(implementation_summary, dtype=float)]
    )

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result.returns.to_csv(output / "monthly_returns.csv", index_label="date")
    result.target_weights.to_csv(output / "target_weights.csv", index_label="date")
    summary.rename("value").to_csv(output / "summary.csv", header=True)
    print(summary.to_string())


if __name__ == "__main__":
    main()
