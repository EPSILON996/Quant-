import pandas as pd
import pandas_ta as ta
import collections
from abc import ABC, abstractmethod
from project_atlas.strategy_library import Signal, STRATEGY_REGISTRY
import logging

class LiveStrategy(ABC):
    def __init__(self, strategy_id: str, config):
        self.id = strategy_id
        self.config = config
        self.cash: float = 0.0
        self.positions: dict[str, int] = collections.defaultdict(int)
        self.risk_per_trade = 0.02
        self.stop_loss_prices: dict[str, float] = collections.defaultdict(float)
        self.take_profit_prices: dict[str, float] = collections.defaultdict(float)
        self.logger = logging.getLogger(f"LiveStrategy.{id}")


    def set_capital(self, capital: float):
        self.cash = capital
        self.logger.debug(f"Live capital set to {self.cash:,.2f}")

    def get_equity(self, last_known_prices: dict) -> float:
        return self.cash + sum(qty * last_known_prices.get(symbol, 0) for symbol, qty in self.positions.items())

    def _set_exit_prices(self, symbol: str, entry_price: float):
        self.stop_loss_prices[symbol] = entry_price * (1 - self.config.STOP_LOSS_PCT)
        self.take_profit_prices[symbol] = entry_price * (1 + self.config.TAKE_PROFIT_PCT)
        self.logger.debug(f"Live Set exit prices for {symbol}: SL={self.stop_loss_prices[symbol]:,.2f}, TP={self.take_profit_prices[symbol]:,.2f}")


    def _clear_exit_prices(self, symbol: str):
        self.stop_loss_prices[symbol] = 0.0
        self.take_profit_prices[symbol] = 0.0
        self.logger.debug(f"Live Cleared exit prices for {symbol}.")


    @abstractmethod
    def decide_action(self, symbol: str, tick: dict) -> Signal:
        pass

class LiveTrendFollowing(LiveStrategy):
    def decide_action(self, symbol: str, tick: dict) -> Signal:
        history = tick.get('history')
        current_price = float(tick['price'])
        self.logger.debug(f"Live Trend: Deciding for {symbol}. Price: {current_price:,.2f}, History length: {len(history) if history is not None else 0}")

        # Check for sufficient history
        if history is None or history.empty or len(history) < self.config.LONG_WINDOW:
            self.logger.debug(f"Live Trend: Insufficient history for {symbol}. HOLD.")
            return Signal.HOLD
        
        # Ensure history is a Series for pandas_ta compatibility and .tail()
        history_series = pd.Series(history)

        rsi = ta.rsi(history_series, length=self.config.RSI_WINDOW)
        
        if rsi is None or rsi.empty:
            self.logger.debug(f"Live Trend: RSI calculation failed for {symbol}. HOLD.")
            return Signal.HOLD
        
        short_ma = history_series.tail(self.config.SHORT_WINDOW).mean()
        long_ma = history_series.tail(self.config.LONG_WINDOW).mean()
        current_rsi = rsi.iloc[-1]

        self.logger.debug(f"Live Trend: {symbol} SMV: {short_ma:,.2f}, LMV: {long_ma:,.2f}, RSI: {current_rsi:,.2f}, Shares: {self.positions.get(symbol, 0)}")


        if short_ma > long_ma and current_rsi > self.config.RSI_BULLISH_THRESHOLD and self.positions.get(symbol, 0) == 0:
            self.logger.info(f"Live Trend: BUY signal for {symbol}.")
            self._set_exit_prices(symbol, current_price)
            return Signal.BUY
        elif short_ma < long_ma and self.positions.get(symbol, 0) > 0:
            self.logger.info(f"Live Trend: SELL signal for {symbol}.")
            return Signal.SELL
        else:
            self.logger.debug(f"Live Trend: No signal for {symbol}. HOLD.")
            return Signal.HOLD

class LiveMeanReversion(LiveStrategy):
    def decide_action(self, symbol: str, tick: dict) -> Signal:
        history = tick.get('history')
        current_price = float(tick['price'])
        self.logger.debug(f"Live MR: Deciding for {symbol}. Price: {current_price:,.2f}, History length: {len(history) if history is not None else 0}")


        # Check for sufficient history
        if history is None or history.empty or len(history) < self.config.WINDOW:
            self.logger.debug(f"Live MR: Insufficient history for {symbol}. HOLD.")
            return Signal.HOLD
        
        # Ensure history is a Series for pandas_ta compatibility and .tail()
        history_series = pd.Series(history)

        rsi = ta.rsi(history_series, length=self.config.RSI_WINDOW)
        
        if rsi is None or rsi.empty:
            self.logger.debug(f"Live MR: RSI calculation failed for {symbol}. HOLD.")
            return Signal.HOLD

        prices_for_bands = history_series.tail(self.config.WINDOW)
        ma = prices_for_bands.mean()
        std = prices_for_bands.std()
        
        if std == 0:
            self.logger.debug(f"Live MR: Standard deviation is zero for {symbol}. HOLD.")
            return Signal.HOLD
        
        lower_band = ma - self.config.STD_DEV * std
        upper_band = ma + self.config.STD_DEV * std
        current_rsi = rsi.iloc[-1]

        self.logger.debug(f"Live MR: {symbol} MA: {ma:,.2f}, StdDev: {std:,.2f}, LB: {lower_band:,.2f}, UB: {upper_band:,.2f}, RSI: {current_rsi:,.2f}, Shares: {self.positions.get(symbol, 0)}")


        if current_price < lower_band and current_rsi < self.config.RSI_OVERSOLD_THRESHOLD and self.positions.get(symbol, 0) == 0:
            self.logger.info(f"Live MR: BUY signal for {symbol}.")
            self._set_exit_prices(symbol, current_price)
            return Signal.BUY
        elif current_price > upper_band and self.positions.get(symbol, 0) > 0:
            self.logger.info(f"Live MR: SELL signal for {symbol}.")
            return Signal.SELL
        else:
            self.logger.debug(f"Live MR: No signal for {symbol}. HOLD.")
            return Signal.HOLD

# Register Citadel classes in the global registry
STRATEGY_REGISTRY["Trend"]["citadel_class"] = LiveTrendFollowing
STRATEGY_REGISTRY["MeanReversion"]["citadel_class"] = LiveMeanReversion
