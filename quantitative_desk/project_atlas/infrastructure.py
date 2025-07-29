import os
import logging
import pandas as pd
import yfinance as yf
import collections

from .core_config import FirmConfig
from .strategy_library import STRATEGY_REGISTRY, Signal

# ADDED: A new class to handle realistic and detailed transaction cost calculations.
class TransactionCostCalculator:
    """
    Calculates realistic transaction costs for Indian equity delivery trades.
    Rates are illustrative and can be adjusted.
    """
    BROKERAGE_PCT = 0.0003      # Example: 0.03%
    STT_PCT = 0.001             # 0.1% on both buy and sell
    EXCHANGE_TXN_PCT = 0.0000345 # NSE Transaction Charge
    GST_PCT = 0.18              # 18% on Brokerage and Transaction Charges
    SEBI_FEES_PCT = 0.000001    # 10 INR per crore
    STAMP_DUTY_PCT = 0.00015    # 0.015% on the buy side

    def calculate(self, trade_value: float, side: str) -> float:
        brokerage = trade_value * self.BROKERAGE_PCT
        stt = trade_value * self.STT_PCT
        exchange_txn_charge = trade_value * self.EXCHANGE_TXN_PCT
        gst = (brokerage + exchange_txn_charge) * self.GST_PCT
        sebi_fees = trade_value * self.SEBI_FEES_PCT
        stamp_duty = trade_value * self.STAMP_DUTY_PCT if side == 'buy' else 0
        total_cost = brokerage + stt + exchange_txn_charge + gst + sebi_fees + stamp_duty
        return total_cost

class DataLoader:
    def __init__(self, symbols: list[str]):
        self.symbols = symbols
        self.logger = logging.getLogger("DataLoader")

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_cache_dir = os.path.join(project_root, 'data_cache')
        os.makedirs(self.data_cache_dir, exist_ok=True)
        self.logger.debug(f"Data cache directory: {self.data_cache_dir}")

        self.marketdata_dir = os.path.join(project_root, 'marketdata')
        os.makedirs(self.marketdata_dir, exist_ok=True)
        self.logger.debug(f"Market data storage directory: {self.marketdata_dir}")

    def get_data(self) -> dict:
        all_data = {}
        for symbol in self.symbols:
            self.logger.debug(f"Attempting to load data for {symbol}")
            data = self._load(symbol)
            if data is not None and not data.empty:
                all_data[symbol] = data
                self.logger.debug(f"Successfully loaded data for {symbol} ({len(data)} rows)")
            else:
                self.logger.error(f"Failed to load or data is empty for {symbol}. Skipping.")
        return all_data

    def _load(self, symbol: str) -> pd.DataFrame:
        cache_path = os.path.join(self.data_cache_dir, f"{symbol.lower()}.csv")
        if os.path.exists(cache_path):
            self.logger.debug(f"Loading {symbol} from cache: {cache_path}")
            loaded_data = pd.read_csv(cache_path, index_col='Date', parse_dates=True)
            return loaded_data
        else:
            self.logger.debug(f"Cache not found for {symbol}. Fetching from YFinance.")
            return self._fetch(symbol)

    def _fetch(self, symbol: str) -> pd.DataFrame | None:
        cache_path = os.path.join(self.data_cache_dir, f"{symbol.lower()}.csv")
        marketdata_filepath = os.path.join(self.marketdata_dir, f"{symbol.lower()}_historical.csv")

        try:
            # Fetch full OHLCV data
            data = yf.Ticker(symbol).history(period="10y")
            if not data.empty:
                data.to_csv(cache_path)
                self.logger.info(f"Successfully fetched and cached {symbol} data.")
                data.to_csv(marketdata_filepath)
                self.logger.info(f"Saved {symbol} historical data to {self.marketdata_dir}")
                return data
            else:
                self.logger.warning(f"Fetched data for {symbol} is empty. Not caching.")
                return None
        except Exception as e:
            self.logger.error(f"Error fetching {symbol}: {e}")
            return None

class PortfolioManager:
    def __init__(self, firm_config: FirmConfig, strategy_configs: dict):
        self.initial_capital = firm_config.FIRM_CAPITAL
        self.strategies = {}
        for name, details in STRATEGY_REGISTRY.items():
            if name in strategy_configs:
                self.strategies[name] = details["atlas_class"](name, firm_config, strategy_configs[name])
        self.logger = logging.getLogger("PortfolioManager")
        self._rebalance_capital()

    def get_total_equity(self, price: float) -> float:
        return sum(strategy.get_equity(price) for strategy in self.strategies.values())

    def _rebalance_capital(self):
        if not self.strategies:
            self.logger.warning("No strategies to rebalance capital for.")
            return
        capital_per_strategy = self.initial_capital / len(self.strategies)
        self.logger.info(f"Rebalancing initial capital: {self.initial_capital:,.2f} among {len(self.strategies)} strategies. Each gets {capital_per_strategy:,.2f}")
        for strategy in self.strategies.values():
            strategy.set_capital(capital_per_strategy)

    def run_daily_operations(self, market_simulator):
        for strategy in self.strategies.values():
            if strategy.shares > 0:
                self.logger.debug(f"Strategy {strategy.id} holds {strategy.shares} shares. Checking for exit signals.")
                if strategy.stop_loss_price > 0 and market_simulator.price <= strategy.stop_loss_price:
                    self.logger.info(f"Strategy {strategy.id}: STOP LOSS triggered for {strategy.shares} shares.")
                    market_simulator.submit_order(strategy.id, 'sell', strategy.shares)
                    strategy._clear_exit_prices()
                    continue
                if strategy.take_profit_price > 0 and market_simulator.price >= strategy.take_profit_price:
                    self.logger.info(f"Strategy {strategy.id}: TAKE PROFIT triggered for {strategy.shares} shares.")
                    market_simulator.submit_order(strategy.id, 'sell', strategy.shares)
                    strategy._clear_exit_prices()
                    continue

            self.logger.debug(f"Strategy {strategy.id}: Deciding action for new trade. Shares: {strategy.shares}, Cash: {strategy.cash:,.2f}")
            
            # CHANGED: Delegate position sizing to the strategy. The strategy now returns the signal AND the quantity.
            signal, quantity = strategy.decide_action(market_simulator)

            if signal == Signal.BUY and quantity > 0:
                self.logger.info(f"Strategy {strategy.id}: BUY signal. Calculated quantity: {quantity} at {market_simulator.price:,.2f}.")
                market_simulator.submit_order(strategy.id, 'buy', quantity)
            elif signal == Signal.SELL and strategy.shares > 0:
                self.logger.info(f"Strategy {strategy.id}: SELL signal. Selling all {strategy.shares} shares.")
                market_simulator.submit_order(strategy.id, 'sell', strategy.shares)
            elif signal == Signal.HOLD:
                self.logger.debug(f"Strategy {strategy.id}: HOLD signal.")

class MarketSimulator:
    def __init__(self, firm_config, historical_data, portfolio_manager):
        self.config = firm_config
        self.data = historical_data
        self.firm = portfolio_manager
        self.order_queue = []
        self.trade_log = []
        
        # CHANGED: Replace simple cost_bps with the new detailed cost calculator.
        self.cost_calculator = TransactionCostCalculator()
        self.slippage_bps = firm_config.BacktestParameters.SLIPPAGE_BPS / 10000

        # CHANGED: The history deque will now store entire data rows for ATR calculation, not just the close price.
        self.history = collections.deque()
        self.price: float = 0.0
        self.logger = logging.getLogger("MarketSimulator")

    def submit_order(self, strategy_id: str, side: str, quantity: int):
        if quantity > 0:
            self.logger.debug(f"Order submitted: {side.upper()} {quantity} for strategy {strategy_id}. Current queue size: {len(self.order_queue) + 1}")
            self.order_queue.append({'id': strategy_id, 'side': side, 'qty': quantity})
        else:
            self.logger.warning(f"Attempted to submit order with quantity 0 for strategy {strategy_id}.")

    def execute_orders(self):
        if not self.order_queue:
            self.logger.debug("No orders in queue to execute.")
            return

        self.logger.debug(f"Executing {len(self.order_queue)} orders.")
        orders_to_process = list(self.order_queue)
        self.order_queue.clear()

        for order in orders_to_process:
            strategy = self.firm.strategies[order['id']]
            execution_price = self.price * (1 + self.slippage_bps if order['side'] == 'buy' else 1 - self.slippage_bps)
            trade_value = order['qty'] * execution_price

            # CHANGED: Use the new calculator for realistic costs.
            transaction_cost = self.cost_calculator.calculate(trade_value, order['side'])

            if order['side'] == 'buy':
                required_funds = trade_value + transaction_cost
                if strategy.cash >= required_funds:
                    strategy.shares += order['qty']
                    strategy.cash -= required_funds
                    # ADDED: Include the calculated cost in the trade log.
                    self.trade_log.append({'id': order['id'], 'side': 'buy', 'qty': order['qty'], 'price': execution_price, 'cost': transaction_cost})
                    self.logger.info(f"Executed BUY {order['qty']} for {order['id']} @ {execution_price:,.2f}. Cost: {transaction_cost:,.2f}. Strategy cash now: {strategy.cash:,.2f}")
                else:
                    self.logger.warning(f"Failed to execute BUY {order['qty']} for {order['id']}: Insufficient cash ({strategy.cash:,.2f} < {required_funds:,.2f})")
            elif order['side'] == 'sell':
                if strategy.shares >= order['qty']:
                    strategy.shares -= order['qty']
                    strategy.cash += (trade_value - transaction_cost)
                    # ADDED: Include the calculated cost in the trade log.
                    self.trade_log.append({'id': order['id'], 'side': 'sell', 'qty': order['qty'], 'price': execution_price, 'cost': transaction_cost})
                    self.logger.info(f"Executed SELL {order['qty']} for {order['id']} @ {execution_price:,.2f}. Net received: {trade_value - transaction_cost:,.2f}. Strategy cash now: {strategy.cash:,.2f}")
                else:
                    self.logger.warning(f"Failed to execute SELL {order['qty']} for {order['id']}: Insufficient shares ({strategy.shares} < {order['qty']})")

    def run(self) -> tuple[pd.Series, list]:
        equity_curve_values = []
        equity_curve_dates = []

        max_warmup_window = 0
        for strategy_name in self.firm.strategies:
            cfg = self.firm.strategies[strategy_name].config
            if hasattr(cfg, 'LONG_WINDOW'): max_warmup_window = max(max_warmup_window, cfg.LONG_WINDOW)
            if hasattr(cfg, 'WINDOW'): max_warmup_window = max(max_warmup_window, cfg.WINDOW)
            if hasattr(cfg, 'RSI_WINDOW'): max_warmup_window = max(max_warmup_window, cfg.RSI_WINDOW)

        # ADDED: Ensure a minimum warmup window for ATR calculation stability.
        max_warmup_window = max(20, max_warmup_window)

        self.logger.info(f"Max strategy lookback window: {max_warmup_window}. Warming up simulation.")
        
        actual_equity_recorded_dates = []
        
        for i, (date_index, row) in enumerate(self.data.iterrows()):
            self.price = row['Close']
            
            # CHANGED: Append the entire row (a pandas Series) to history for ATR calculation.
            self.history.append(row)

            if len(self.history) > max_warmup_window + 50:
                self.history.popleft()

            if i >= max_warmup_window - 1:
                self.firm.run_daily_operations(self)
                self.execute_orders()
                equity_curve_values.append(self.firm.get_total_equity(self.price))
                actual_equity_recorded_dates.append(date_index)

        self.logger.info(f"Simulation finished. Total trades executed: {len(self.trade_log)}")

        if not equity_curve_values:
            return pd.Series(dtype=float), []

        if len(equity_curve_values) != len(actual_equity_recorded_dates):
            self.logger.error(f"Critical Mismatch: equity_curve_values length ({len(equity_curve_values)}) != actual_equity_recorded_dates length ({len(actual_equity_recorded_dates)})")
            return pd.Series(equity_curve_values, dtype='float64'), self.trade_log
        else:
            return pd.Series(equity_curve_values, index=actual_equity_recorded_dates), self.trade_log
