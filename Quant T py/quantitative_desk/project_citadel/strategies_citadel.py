# project_citadel/4_strategies_citadel.py (v13.0 - Definitive & Final)
""" The definitive version with the stop-loss mechanism. """
import numpy as np
import collections
from abc import ABC, abstractmethod
from project_atlas.strategy_library import Signal, STRATEGY_REGISTRY

class LiveStrategy(ABC):
    def __init__(self, strategy_id: str, config):
        self.id = strategy_id; self.config = config; self.cash: float = 0.0
        self.positions: dict[str, int] = collections.defaultdict(int); self.risk_per_trade = 0.02
        self.stop_loss_pct = 0.02; self.stop_losses: dict[str, float] = collections.defaultdict(float)
    def set_capital(self, capital: float): self.cash = capital
    def get_equity(self, last_known_prices: dict) -> float:
        return self.cash + sum(qty * last_known_prices.get(s, 0) for s, qty in self.positions.items())
    @abstractmethod
    def decide_action(self, symbol: str, tick: dict) -> Signal: pass
class LiveTrendFollowing(LiveStrategy):
    def decide_action(self, symbol: str, tick: dict) -> Signal:
        history=tick.get('history'); current_price=float(tick['price'])
        if not history or len(history) < self.config.LONG_WINDOW: return Signal.HOLD
        short_ma=np.mean(list(history)[-self.config.SHORT_WINDOW:]); long_ma=np.mean(list(history)[-self.config.LONG_WINDOW:])
        if short_ma > long_ma and self.positions[symbol] == 0:
            self.stop_losses[symbol] = current_price * (1 - self.stop_loss_pct); return Signal.BUY
        elif short_ma < long_ma and self.positions[symbol] > 0:
            self.stop_losses[symbol] = 0.0; return Signal.SELL
        else: return Signal.HOLD
class LiveMeanReversion(LiveStrategy):
    def decide_action(self, symbol: str, tick: dict) -> Signal:
        history=tick.get('history'); current_price=float(tick['price'])
        if not history or len(history) < self.config.WINDOW: return Signal.HOLD
        prices=np.array(list(history)[-self.config.WINDOW:]); ma=prices.mean(); std=prices.std()
        if std == 0: return Signal.HOLD
        if current_price < (ma - self.config.STD_DEV * std) and self.positions[symbol] == 0:
            self.stop_losses[symbol] = current_price * (1 - self.stop_loss_pct); return Signal.BUY
        elif current_price > (ma + self.config.STD_DEV * std) and self.positions[symbol] > 0:
            self.stop_losses[symbol] = 0.0; return Signal.SELL
        else: return Signal.HOLD
STRATEGY_REGISTRY["Trend"]["citadel_class"] = LiveTrendFollowing
STRATEGY_REGISTRY["MeanReversion"]["citadel_class"] = LiveMeanReversion
