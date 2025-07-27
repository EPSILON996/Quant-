# project_citadel/core_config_citadel.py (v13.0 - Definitive & Final)
"""
This definitive version expands the live trading universe to the full NIFTY 50.
"""
from dataclasses import dataclass, field

class LiveConfig:
    INITIAL_CAPITAL: int = 100_000_000
    SYMBOLS_TO_TRADE: list[str] = [
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
    @dataclass
    class StrategyParameters:
        @dataclass
        class Trend: SHORT_WINDOW: int = 20; LONG_WINDOW: int = 50
        @dataclass
        class MeanReversion: WINDOW: int = 20; STD_DEV: float = 2.0
    @dataclass
    class RiskParameters:
        MAX_ORDER_VALUE: int = 1_000_000; DAILY_DRAWDOWN_LIMIT: float = 0.05
