# project_atlas/core_config.py (v13.0 - Definitive & Final)
"""
This definitive version fixes the critical AttributeError by correctly nesting
the BacktestParameters within the FirmConfig class.
"""
from dataclasses import dataclass, field

@dataclass
class StrategyConfig:
    @dataclass
    class TrendFollowing:
        SHORT_WINDOW: int = 40
        LONG_WINDOW: int = 100
    @dataclass
    class MeanReversion:
        WINDOW: int = 20
        STD_DEV: float = 2.0

class FirmConfig:
    """Core configuration for the research engine, now correctly structured."""
    FIRM_CAPITAL: int = 100_000_000
    RISK_FREE_RATE: float = 0.07
    
    # --- THE DEFINITIVE FIX for AttributeError ---
    # This class is now correctly nested inside FirmConfig, making it accessible
    # to all components, including the parallel worker processes.
    @dataclass
    class BacktestParameters:
        TRANSACTION_COST_BPS: int = 5
        SLIPPAGE_BPS: int = 10

    SYMBOLS: list[str] = [
        "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", 
        "AXISBANK.NS", "BAJAJ-AUTO.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", 
        "BPCL.NS", "BHARTIARTL.NS", "BRITANNIA.NS", "CIPLA.NS", "COALINDIA.NS", 
        "DIVISLAB.NS", "DRREDDY.NS", "EICHERMOT.NS", "GRASIM.NS", "HCLTECH.NS", 
        "HDFCBANK.NS", "HDFCLIFE.NS", "HEROMOTOCO.NS", "HINDALCO.NS", 
        "HINDUNILVR.NS", "ICICIBANK.NS", "ITC.NS", "INDUSINDBK.NS", 
        "INFY.NS", "JSWSTEEL.NS", "KOTAKBANK.NS", "LTIM.NS", "LT.NS", 
        "M&M.NS", "MARUTI.NS", "NESTLEIND.NS", "NTPC.NS", "ONGC.NS", 
        "POWERGRID.NS", "RELIANCE.NS", "SBILIFE.NS", "SBIN.NS", 
        "SUNPHARMA.NS", "TCS.NS", "TATACONSUM.NS", "TATAMOTORS.NS", 
        "TATASTEEL.NS", "TECHM.NS", "TITAN.NS", "ULTRACEMCO.NS", 
        "UPL.NS", "WIPRO.NS"
    ]
