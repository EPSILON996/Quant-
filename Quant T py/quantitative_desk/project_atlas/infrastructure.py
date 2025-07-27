# project_atlas/infrastructure.py (v13.0 - Definitive & Final)
""" The definitive version with the stop-loss enforcement and UnboundLocalError fix. """
import os, logging, pandas as pd, yfinance as yf
from .core_config import FirmConfig
from .strategy_library import STRATEGY_REGISTRY, Signal

class DataLoader:
    def __init__(self, symbols: list[str]): self.symbols = symbols
    def get_data(self) -> dict[str, pd.DataFrame]:
        all_data = {}; logging.info(f"--- Data Loader starting for {len(self.symbols)} symbols. ---")
        for symbol in self.symbols:
            cache_path = f"{symbol.lower()}_data.csv"
            if os.path.exists(cache_path):
                logging.info(f"Loading data for {symbol} from cache."); all_data[symbol] = pd.read_csv(cache_path, index_col='Date', parse_dates=True)
            else:
                logging.info(f"Fetching new data for {symbol}."); new_data = self._fetch_from_yfinance(symbol)
                if new_data is not None: all_data[symbol] = new_data
        logging.info("--- Data Loading Complete. ---"); return all_data
    def _fetch_from_yfinance(self, symbol: str) -> pd.DataFrame | None:
        try: data = yf.Ticker(symbol).history(period="10y"); data.to_csv(f"{symbol.lower()}_data.csv"); return data
        except Exception as e: logging.error(f"Fetch failed for {symbol}: {e}"); return None
class PortfolioManager:
    def __init__(self, firm_config: FirmConfig, strategy_configs: dict):
        self.initial_capital = firm_config.FIRM_CAPITAL; self.strategies = {}
        for name, details in STRATEGY_REGISTRY.items():
            if name in strategy_configs: self.strategies[name] = details["atlas_class"](name, firm_config, strategy_configs[name])
        self._rebalance_capital()
    def get_total_equity(self, price: float) -> float: return sum(s.get_equity(price) for s in self.strategies.values())
    def _rebalance_capital(self):
        capital = self.initial_capital / len(self.strategies) if self.strategies else 0
        for s in self.strategies.values(): s.set_capital(capital)
    def run_daily_operations(self, market):
        for s in self.strategies.values():
            if s.shares > 0 and market.price <= s.stop_loss_price:
                market.submit_order(s.id, 'sell', s.shares); s.stop_loss_price = 0.0; continue
            signal = s.decide_action(market)
            if signal == Signal.BUY:
                trade_capital = s.get_equity(market.price) * s.risk_per_trade
                qty_to_buy = int(trade_capital / market.price) if market.price > 0 else 0
                market.submit_order(s.id, 'buy', qty_to_buy)
            elif signal == Signal.SELL: market.submit_order(s.id, 'sell', s.shares)
class MarketSimulator:
    def __init__(self, firm_config, historical_data, portfolio_manager):
        self.config=firm_config; self.data=historical_data; self.firm=portfolio_manager; self.price: float = 0.0
        self.history = []; self.order_queue = []; self.trade_log = []
        self.cost_bps=self.config.BacktestParameters.TRANSACTION_COST_BPS/10000; self.slippage_bps=self.config.BacktestParameters.SLIPPAGE_BPS/10000
    def submit_order(self, id: str, side: str, qty: int):
        if qty > 0: self.order_queue.append({'id': id, 'side': side, 'qty': qty})
    def execute_orders(self):
        for order in self.order_queue:
            strategy = self.firm.strategies[order['id']]; exec_price = self.price * (1 + self.slippage_bps if order['side'] == 'buy' else 1 - self.slippage_bps)
            trade_value = order['qty'] * exec_price; transaction_cost = trade_value * self.cost_bps
            if order['side'] == 'buy' and strategy.cash >= (trade_value + transaction_cost):
                strategy.shares += order['qty']; strategy.cash -= (trade_value + transaction_cost)
                self.trade_log.append({'id': order['id'], 'side': 'buy', 'qty': order['qty'], 'price': exec_price})
            elif order['side'] == 'sell' and strategy.shares >= order['qty']:
                strategy.shares -= order['qty']; strategy.cash += (trade_value - transaction_cost)
                self.trade_log.append({'id': order['id'], 'side': 'sell', 'qty': order['qty'], 'price': exec_price})
        self.order_queue.clear()
    def run(self) -> tuple[pd.Series, list]:
        equity_curve = [];
        for _, row in self.data.iterrows():
            self.price = row['Close']; self.history.append(self.price); self.firm.run_daily_operations(self); self.execute_orders()
            equity_curve.append(self.firm.get_total_equity(self.price))
        return pd.Series(equity_curve, index=self.data.index), self.trade_log
