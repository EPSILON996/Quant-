from dataclasses import dataclass


@dataclass
class LiveStrategyParameters:
    """Defines the parameter structure for live strategies."""
    @dataclass
    class Trend:
        SHORT_WINDOW: int = 20
        LONG_WINDOW: int = 50
        RSI_WINDOW: int = 14
        RSI_BULLISH_THRESHOLD: int = 55
        TAKE_PROFIT_PCT: float = 0.05
        STOP_LOSS_PCT: float = 0.02
        RISK_PER_TRADE: float = 0.05  # 2% risk per trade

    @dataclass
    class MeanReversion:
        WINDOW: int = 20
        STD_DEV: float = 2.0
        RSI_WINDOW: int = 14
        RSI_OVERSOLD_THRESHOLD: int = 40
        TAKE_PROFIT_PCT: float = 0.03
        STOP_LOSS_PCT: float = 0.015
        RISK_PER_TRADE: float = 0.05


@dataclass
class LiveRiskParameters:
    """Defines the risk parameters for the live engine."""
    MAX_ORDER_VALUE: int = 200_000  # e.g., 20% of capital or adjust as you prefer
    DAILY_DRAWDOWN_LIMIT: float = 0.05


class LiveConfig:
    """Main configuration class for the live trading engine (Project Citadel)."""
    INITIAL_CAPITAL: int = 1_000_000  # 10 lakh
    
    # Using the full list of NIFTY 50 stocks as requested.
    SYMBOLS_TO_TRADE: list[str] = [
        "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "AXISBANK.NS", "BAJAJ-AUTO.NS",
        "BAJFINANCE.NS", "BAJAJFINSV.NS", "BPCL.NS", "BHARTIARTL.NS", "BRITANNIA.NS", "CIPLA.NS",
        "COALINDIA.NS", "DIVISLAB.NS", "DRREDDY.NS", "EICHERMOT.NS", "GRASIM.NS", "HCLTECH.NS",
        "HDFCBANK.NS", "HDFCLIFE.NS", "HEROMOTOCO.NS", "HINDALCO.NS", "HINDUNILVR.NS", "ICICIBANK.NS",
        "ITC.NS", "INDUSINDBK.NS", "INFY.NS", "JSWSTEEL.NS", "KOTAKBANK.NS", "LTIM.NS",
        "LT.NS", "M&M.NS", "MARUTI.NS", "NTPC.NS", "NESTLEIND.NS", "ONGC.NS",
        "POWERGRID.NS", "RELIANCE.NS", "SBILIFE.NS", "SBIN.NS", "SUNPHARMA.NS", "TATAMOTORS.NS",
        "TCS.NS", "TATACONSUM.NS", "TATASTEEL.NS", "TECHM.NS", "TITAN.NS", "ULTRACEMCO.NS",
        "WIPRO.NS", "UPL.NS"
    ]
    
    # Instantiating the parameter classes so they can be accessed by the CIO and RiskManager.
    StrategyParameters: LiveStrategyParameters = LiveStrategyParameters()
    RiskParameters: LiveRiskParameters = LiveRiskParameters()
