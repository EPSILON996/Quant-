from dataclasses import dataclass

@dataclass
class StrategyConfig:
    @dataclass
    class TrendFollowing:
        SHORT_WINDOW: int = 20
        LONG_WINDOW: int = 50
        RSI_WINDOW: int = 14
        RSI_BULLISH_THRESHOLD: int = 55
        TAKE_PROFIT_PCT: float = 0.05
        STOP_LOSS_PCT: float = 0.02

    @dataclass
    class MeanReversion:
        WINDOW: int = 20
        STD_DEV: float = 2.0
        RSI_WINDOW: int = 14
        RSI_OVERSOLD_THRESHOLD: int = 40
        TAKE_PROFIT_PCT: float = 0.03
        STOP_LOSS_PCT: float = 0.015

class FirmConfig:
    FIRM_CAPITAL: int = 1_000_000  # 10 lakh INR, updated capital
    RISK_FREE_RATE: float = 0.07
    BENCHMARK_SYMBOL: str = "^NSEI"  # NIFTY 50 index symbol for benchmarking

    @dataclass
    class BacktestParameters:
        TRANSACTION_COST_BPS: int = 5     # 5 basis points transaction cost
        SLIPPAGE_BPS: int = 10            # 10 basis points slippage
        OPTIMIZATION_TRIALS: int = 24     # Number of random trials in optimization

    SYMBOLS: list[str] = [
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
