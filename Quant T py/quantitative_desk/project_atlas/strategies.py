# project_atlas/strategies.py
"""
Project Atlas: Strategy Library (v4.1 - Definitive & Corrected)
================================================================
This is the definitive, corrected version of the backtesting strategies.
The logic has been fixed to correctly access all parameters from the
'self.config' object, resolving the AttributeError for good.
"""
import numpy as np
from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    def __init__(self, strategy_id: str, firm_config, strategy_config):
        self.id = strategy_id
        self.firm_config = firm_config
        self.config = strategy_config
        self.cash: float = 0.0
        self.shares: int = 0
    def set_capital(self, capital: float): self.cash = capital
    def get_equity(self, price: float) -> float: return self.cash + self.shares * price
    def execute_trade(self, side: str, quantity: int, price: float):
        trade_value = quantity * price
        if side == 'buy' and self.cash >= trade_value:
            self.shares += quantity; self.cash -= trade_value
        elif side == 'sell' and self.shares >= quantity:
            self.shares -= quantity; self.cash += trade_value
    @abstractmethod
    def decide_action(self, market_data): pass

class TrendFollowing(BaseStrategy):
    def decide_action(self, market_data):
        price_history = market_data.history
        if len(price_history) < self.config.LONG_WINDOW: return
        short_ma = np.mean(price_history[-self.config.SHORT_WINDOW:])
        long_ma = np.mean(price_history[-self.config.LONG_WINDOW:])
        if short_ma > long_ma and self.shares == 0:
            qty = int(self.cash / market_data.price) if market_data.price > 0 else 0
            market_data.submit_order(self.id, 'buy', qty)
        elif short_ma < long_ma and self.shares > 0:
            market_data.submit_order(self.id, 'sell', self.shares)

class MeanReversion(BaseStrategy):
    def decide_action(self, market_data):
        price_history = market_data.history
        if len(price_history) < self.config.WINDOW: return
        prices = np.array(price_history[-self.config.WINDOW:])
        ma = prices.mean(); std = prices.std()
        if std == 0: return
        upper_band = ma + self.config.STD_DEV * std
        lower_band = ma - self.config.STD_DEV * std
        if market_data.price < lower_band and self.shares == 0:
            qty = int((self.cash * 0.5) / market_data.price) if market_data.price > 0 else 0
            market_data.submit_order(self.id, 'buy', qty)
        elif market_data.price > upper_band and self.shares > 0:
            market_data.submit_order(self.id, 'sell', self.shares)
