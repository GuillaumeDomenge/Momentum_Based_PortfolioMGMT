import pandas as pd

from quant_momentum.metrics import performance_summary


def strategy_summary(
    returns: pd.DataFrame,
    *,
    periods_per_year: int = 12,
    risk_free_annual_rate: float = 0.0,
) -> pd.Series:
    """Summarize gross, net, turnover, and cost results for one evaluation period."""
    gross = performance_summary(
        returns["gross_return"], periods_per_year, risk_free_annual_rate
    ).add_prefix("gross_")
    net = performance_summary(
        returns["net_return"], periods_per_year, risk_free_annual_rate
    ).add_prefix("net_")
    implementation = pd.Series(
        {
            "average_monthly_traded_notional": returns["traded_notional"].mean(),
            "annualized_average_trading_cost": (
                returns["trading_cost"].mean() * periods_per_year
            ),
            "annualized_average_borrow_cost": (
                returns["borrow_cost"].mean() * periods_per_year
            ),
        },
        dtype=float,
    )
    return pd.concat([gross, net, implementation])
