import logging
from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class Signal:
    BUY = 1
    SELL = -1
    HOLD = 0


class AtlasStrategy(ABC):
    def __init__(self, id: str, firm_config, strategy_config):
        self.id = id
        self.firm_config = firm_config
        self.config = strategy_config
        self.cash: float = 0.0
        self.shares: int = 0
        self.risk_per_trade = 0.02
        self.stop_loss_price = 0.0
        self.take_profit_price = 0.0
        self.logger = logging.getLogger(f"Strategy.{id}")

    def get_equity(self, current_price: float) -> float:
        return self.cash + (self.shares * current_price)

    def set_capital(self, capital: float):
        self.cash = capital
        self.shares = 0

    def _clear_exit_prices(self):
        self.stop_loss_price = 0.0
        self.take_profit_price = 0.0

    def _calculate_atr(self, history_df: pd.DataFrame, period: int = 14) -> float:
        if len(history_df) < period or not all(col in history_df.columns for col in ['High', 'Low', 'Close']):
            return 0.0
        high, low, close = history_df['High'], history_df['Low'], history_df['Close']
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.ewm(alpha=1/period, adjust=False).mean()
        return atr.iloc[-1] if not atr.empty and pd.notna(atr.iloc[-1]) else 0.0

    @abstractmethod
    def decide_action(self, market_simulator) -> tuple[int, int]:
        pass


class AtlasTrendFollowing(AtlasStrategy):
    def decide_action(self, market_simulator) -> tuple[int, int]:
        history_data = pd.DataFrame(list(market_simulator.history))
        if len(history_data) < self.config.LONG_WINDOW:
            return Signal.HOLD, 0

        short_sma = history_data['Close'].rolling(window=self.config.SHORT_WINDOW).mean().iloc[-1]
        long_sma = history_data['Close'].rolling(window=self.config.LONG_WINDOW).mean().iloc[-1]

        if self.shares == 0:
            # Compute RSI approximately
            rsi = pd.Series(np.gradient(history_data['Close'])).rolling(window=self.config.RSI_WINDOW).apply(
                lambda x: np.sum(x[x > 0]) / (np.sum(np.abs(x[x < 0])) + 1e-9), raw=True).iloc[-1] * 100

            if short_sma > long_sma and rsi > self.config.RSI_BULLISH_THRESHOLD:
                atr = self._calculate_atr(history_data, period=14)
                if atr > 0:
                    quantity = int((self.cash * self.risk_per_trade) / atr)
                    self.stop_loss_price = market_simulator.price * (1 - self.config.STOP_LOSS_PCT)
                    self.take_profit_price = market_simulator.price * (1 + self.config.TAKE_PROFIT_PCT)
                    return Signal.BUY, quantity
        else:
            if short_sma < long_sma:
                self._clear_exit_prices()
                return Signal.SELL, 0

        return Signal.HOLD, 0


class AtlasMeanReversion(AtlasStrategy):
    def decide_action(self, market_simulator) -> tuple[int, int]:
        history_data = pd.DataFrame(list(market_simulator.history))
        if len(history_data) < self.config.WINDOW:
            return Signal.HOLD, 0

        sma = history_data['Close'].rolling(window=self.config.WINDOW).mean().iloc[-1]
        std_dev = history_data['Close'].rolling(window=self.config.WINDOW).std().iloc[-1]
        lower_band = sma - (self.config.STD_DEV * std_dev)

        if self.shares == 0:
            rsi = pd.Series(np.gradient(history_data['Close'])).rolling(window=self.config.RSI_WINDOW).apply(
                lambda x: np.sum(x[x > 0]) / (np.sum(np.abs(x[x < 0])) + 1e-9), raw=True).iloc[-1] * 100

            if market_simulator.price < lower_band and rsi < self.config.RSI_OVERSOLD_THRESHOLD:
                atr = self._calculate_atr(history_data, period=14)
                if atr > 0:
                    quantity = int((self.cash * self.risk_per_trade) / atr)
                    self.stop_loss_price = market_simulator.price * (1 - self.config.STOP_LOSS_PCT)
                    self.take_profit_price = market_simulator.price * (1 + self.config.TAKE_PROFIT_PCT)
                    return Signal.BUY, quantity
        else:
            if market_simulator.price > sma:
                self._clear_exit_prices()
                return Signal.SELL, 0

        return Signal.HOLD, 0


# This is the base registry. Your strategies_citadel.py file will add the "citadel_class" key to it.
STRATEGY_REGISTRY = {
    "Trend": {"atlas_class": AtlasTrendFollowing},
    "MeanReversion": {"atlas_class": AtlasMeanReversion}
}
