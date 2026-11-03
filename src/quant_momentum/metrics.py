import numpy as np
import pandas as pd


def performance_summary(
    returns: pd.Series,
    periods_per_year: int = 12,
    risk_free_annual_rate: float = 0.0,
) -> pd.Series:
    """Core annualised performance metrics for periodic strategy returns."""
    returns = returns.dropna()
    years = len(returns) / periods_per_year
    wealth = (1 + returns).prod()
    cagr = wealth ** (1 / years) - 1 if years > 0 else np.nan
    volatility = returns.std(ddof=1) * np.sqrt(periods_per_year)
    periodic_risk_free = (1 + risk_free_annual_rate) ** (1 / periods_per_year) - 1
    excess = returns - periodic_risk_free
    sharpe = (excess.mean() / excess.std(ddof=1)) * np.sqrt(periods_per_year)
    drawdown = (1 + returns).cumprod().div((1 + returns).cumprod().cummax()).sub(1)
    return pd.Series(
        {
            "observations": len(returns),
            "cagr": cagr,
            "volatility": volatility,
            "sharpe": sharpe,
            "max_drawdown": drawdown.min(),
        }
    )
