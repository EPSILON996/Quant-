# project_atlas/1_strategy_library.py (v13.0 - Definitive & Final)
""" The definitive version with the stop-loss mechanism. """
import pandas as pd
from abc import ABC, abstractmethod
from enum import Enum, auto

class Signal(Enum): BUY = auto(); SELL = auto(); HOLD = auto()
class AtlasStrategy(ABC):
    def __init__(self, id: str, firm_config, strategy_config):
        self.id = id; self.firm_config = firm_config; self.config = strategy_config
        self.cash = 0.0; self.shares = 0; self.risk_per_trade = 0.02
        self.stop_loss_pct = 0.02; self.stop_loss_price = 0.0
    def set_capital(self, capital: float): self.cash = capital
    def get_equity(self, price: float) -> float: return self.cash + self.shares * price
    @abstractmethod
    def decide_action(self, market_simulator) -> Signal: pass
class AtlasTrendFollowing(AtlasStrategy):
    def decide_action(self, market) -> Signal:
        if len(market.history) < self.config.LONG_WINDOW: return Signal.HOLD
        short_ma=pd.Series(market.history).tail(self.config.SHORT_WINDOW).mean()
        long_ma=pd.Series(market.history).tail(self.config.LONG_WINDOW).mean()
        if short_ma > long_ma and self.shares == 0:
            self.stop_loss_price = market.price * (1 - self.stop_loss_pct); return Signal.BUY
        elif short_ma < long_ma and self.shares > 0:
            self.stop_loss_price = 0.0; return Signal.SELL
        else: return Signal.HOLD
class AtlasMeanReversion(AtlasStrategy):
    def decide_action(self, market) -> Signal:
        if len(market.history) < self.config.WINDOW: return Signal.HOLD
        prices=pd.Series(market.history).tail(self.config.WINDOW); ma=prices.mean(); std=prices.std()
        if std == 0: return Signal.HOLD
        if market.price < (ma - self.config.STD_DEV * std) and self.shares == 0:
            self.stop_loss_price = market.price * (1 - self.stop_loss_pct); return Signal.BUY
        elif market.price > (ma + self.config.STD_DEV * std) and self.shares > 0:
            self.stop_loss_price = 0.0; return Signal.SELL
        else: return Signal.HOLD
STRATEGY_REGISTRY = {"Trend": {"atlas_class": AtlasTrendFollowing, "citadel_class": None},"MeanReversion": {"atlas_class": AtlasMeanReversion, "citadel_class": None}}
