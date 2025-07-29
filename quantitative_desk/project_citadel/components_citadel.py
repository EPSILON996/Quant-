import logging
import yfinance as yf
import numpy as np
import pandas as pd
import collections
import json
import os
from datetime import datetime, time as dt_time, date, timedelta


# Import from project_atlas (using relative import from main perspective)
from project_atlas.strategy_library import STRATEGY_REGISTRY, Signal


# Import from current project (project_citadel)
from .strategies_citadel import LiveStrategy


class Alerter:
    def __init__(self):
        self.logger = logging.getLogger("Alerter")


    def send(self, subject: str, message: str):
        self.logger.critical(f"[ALERT] {subject}: {message}")


class RiskManager:
    def __init__(self, risk_parameters, alerter: Alerter):
        self.params = risk_parameters
        self.alerter = alerter
        self.peak_equity = 0.0
        self.is_drawdown_breached = False
        self.logger = logging.getLogger("RiskManager")


    def assess_new_day(self, value: float):
        self.peak_equity = value
        self.is_drawdown_breached = False
        self.logger.info(f"New day assessment. Peak equity set to {self.peak_equity:,.2f}.")


    def is_trade_allowed(self, side: str, quantity: int, price: float, portfolio_context) -> bool:
        order_value = quantity * price
        if order_value > self.params.MAX_ORDER_VALUE:
            self.logger.warning(f"Trade for {quantity} shares @ {price:,.2f} ({order_value:,.2f}) exceeds MAX_ORDER_VALUE ({self.params.MAX_ORDER_VALUE:,.2f}). Denying trade.")
            self.alerter.send("RISK VIOLATION", f"Order value {order_value:,.2f} exceeds limit.")
            return False
        
        # More sophisticated risk checks could go here (e.g., daily drawdown, sector exposure)
        self.logger.debug(f"Trade for {quantity} shares @ {price:,.2f} ({order_value:,.2f}) allowed by RiskManager.")
        return True


class ChiefInvestmentOfficer:
    def __init__(self, config, risk_manager: RiskManager, alerter: Alerter):
        self.config = config
        self.risk_manager = risk_manager
        self.alerter = alerter
        self.initial_capital = config.INITIAL_CAPITAL
        self.symbols = config.SYMBOLS_TO_TRADE
        self.last_known_prices: dict[str, float] = {s: 0 for s in self.symbols}
        self.trade_count = 0
        self.logger = logging.getLogger("CIO")


        # Initialize strategies
        self.strategies: dict[str, LiveStrategy] = {}
        for name, details in STRATEGY_REGISTRY.items():
            if details.get("citadel_class"):
                param_class = getattr(config.StrategyParameters, name, None)
                if param_class:
                    self.strategies[name] = details["citadel_class"](name, param_class)
                    self.logger.info(f"Initialized live strategy: {name}")


        self.portfolio_file = 'live_portfolio.json'
        self._load_portfolio_from_disk()


        self.current_value = self.get_total_equity()
        self.risk_manager.assess_new_day(self.current_value)
        self.logger.info(f"CIO initialized with {self.initial_capital:,.2f} capital. Current equity: {self.current_value:,.2f}")
        self._rebalance_capital() # This allocates the initial capital to live strategies.


    def _save_portfolio_to_disk(self):
        """Saves all non-zero positions to the JSON ledger."""
        full_portfolio = {strat_id: {symbol: qty for symbol, qty in strategy.positions.items() if qty > 0}
                          for strat_id, strategy in self.strategies.items()}
        try:
            with open(self.portfolio_file, 'w') as f:
                json.dump(full_portfolio, f, indent=4)
            self.logger.debug(f"Portfolio saved to {self.portfolio_file}. Total positions: {sum(len(p) for p in full_portfolio.values())}")
        except Exception as e:
            self.logger.error(f"Failed to save portfolio to disk: {e}")


    def _load_portfolio_from_disk(self):
        """Loads positions from the JSON ledger if it exists."""
        if not os.path.exists(self.portfolio_file):
            self.logger.info(f"No existing portfolio file found at {self.portfolio_file}. Starting fresh.")
            return


        try:
            with open(self.portfolio_file, 'r') as f:
                loaded_portfolio = json.load(f)
            self.logger.warning(f"Found existing portfolio file '{self.portfolio_file}'. Loading positions.")
            for strat_id, positions in loaded_portfolio.items():
                if strat_id in self.strategies:
                    self.strategies[strat_id].positions.update(positions)
                    self.logger.debug(f"Loaded {len(positions)} positions for strategy '{strat_id}'.")
        except Exception as e:
            self.logger.error(f"Failed to load portfolio from disk. Starting with a clean slate. Error: {e}")


    def _rebalance_capital(self):
        """Rebalances capital among active strategies based on initial capital."""
        if not self.strategies:
            self.logger.warning("No live strategies defined to rebalance capital for.")
            return
        capital_per_strategy = self.initial_capital / len(self.strategies)
        self.logger.info(f"Rebalancing initial capital: {self.initial_capital:,.2f} among {len(self.strategies)} live strategies. Each gets {capital_per_strategy:,.2f}")
        for strategy in self.strategies.values():
            strategy.set_capital(capital_per_strategy)


    def get_total_equity(self) -> float:
        """Calculates the current total equity (cash + market value of positions)."""
        total_equity = sum(strategy.get_equity(self.last_known_prices) for strategy in self.strategies.values())
        return total_equity


    def on_market_data(self, ticks: dict, current_time: datetime):
        # Update last known prices for all symbols received in this tick
        for symbol, tick_data in ticks.items():
            if tick_data and tick_data.get('price') is not None:
                self.last_known_prices[symbol] = tick_data['price']


        # Loop through each symbol to process signals and manage trades
        for symbol, tick_data in ticks.items():
            if not (tick_data and 'history' in tick_data and tick_data['history'] is not None and not tick_data['history'].empty):
                self.logger.debug(f"Skipping {symbol}: Invalid or empty history in tick data.")
                continue
            
            current_price = float(tick_data['price'])
            
            for strategy in self.strategies.values():
                # Active trade management (sell side) - checking stop-loss and take-profit
                if strategy.positions.get(symbol, 0) > 0:
                    self.logger.debug(f"Strategy {strategy.id} (Symbol {symbol}): Has {strategy.positions.get(symbol,0)} shares. Price: {current_price:,.2f}. SL: {strategy.stop_loss_prices.get(symbol,0):,.2f}, TP: {strategy.take_profit_prices.get(symbol,0):,.2f}")
                    # Check Stop-Loss
                    if strategy.stop_loss_prices.get(symbol, 0) > 0 and current_price <= strategy.stop_loss_prices[symbol]:
                        self.logger.warning(f"Strategy {strategy.id}: STOP LOSS for {symbol}. Price {current_price:,.2f} <= SL {strategy.stop_loss_prices[symbol]:,.2f}. Selling {strategy.positions[symbol]} shares.")
                        self.submit_order(strategy.id, symbol, 'sell', strategy.positions[symbol], current_time)
                        strategy._clear_exit_prices(symbol)
                        continue 
                    
                    # Check Take-Profit
                    if strategy.take_profit_prices.get(symbol, 0) > 0 and current_price >= strategy.take_profit_prices[symbol]:
                        self.logger.warning(f"Strategy {strategy.id}: TAKE PROFIT for {symbol}. Price {current_price:,.2f} >= TP {strategy.take_profit_prices[symbol]:,.2f}. Selling {strategy.positions[symbol]} shares.")
                        self.submit_order(strategy.id, symbol, 'sell', strategy.positions[symbol], current_time)
                        strategy._clear_exit_prices(symbol)
                        continue
                
                # Entry/Exit signal logic from the strategy itself
                signal = strategy.decide_action(symbol, tick_data)
                self.logger.debug(f"Strategy {strategy.id} (Symbol {symbol}): Signal is {signal.name if hasattr(signal, 'name') else signal}.")


                if signal == Signal.BUY:
                    quantity = int((strategy.cash * strategy.risk_per_trade) / current_price) if current_price > 0 else 0
                    self.logger.info(f"Strategy {strategy.id}: BUY signal for {symbol}. Calculated quantity: {quantity}. Price: {current_price:,.2f}. Strat Cash: {strategy.cash:,.2f}")
                    if quantity > 0:
                        self.submit_order(strategy.id, symbol, 'buy', quantity, current_time)
                    else:
                        self.logger.warning(f"Strategy {strategy.id}: BUY for {symbol}, but calculated quantity is 0. Not submitting order.")
                elif signal == Signal.SELL:
                    quantity = strategy.positions.get(symbol, 0)
                    if quantity > 0:
                        self.logger.info(f"Strategy {strategy.id}: SELL signal for {symbol}. Selling {quantity} shares. Price: {current_price:,.2f}. Strat Cash: {strategy.cash:,.2f}")
                        self.submit_order(strategy.id, symbol, 'sell', quantity, current_time)
                        strategy._clear_exit_prices(symbol)
                    else:
                        self.logger.warning(f"Strategy {strategy.id}: SELL for {symbol}, but no shares to sell. Not submitting order.")


    def submit_order(self, strategy_id: str, symbol: str, side: str, quantity: int, current_time: datetime):
        price = self.last_known_prices.get(symbol)
        
        if price is None or price <= 0:
            self.logger.error(f"Cannot submit order for {symbol}: Invalid price {price}.")
            return


        if quantity <= 0:
            self.logger.warning(f"Attempted to submit order with non-positive quantity {quantity} for {symbol}.")
            return


        if self.risk_manager.is_trade_allowed(side, quantity, price, self):
            strategy = self.strategies[strategy_id]
            trade_value = quantity * price


            if (side == 'buy' and strategy.cash >= trade_value) or \
               (side == 'sell' and strategy.positions.get(symbol, 0) >= quantity):
                
                self.trade_count += 1
                
                # Update positions and cash
                strategy.positions[symbol] = strategy.positions.get(symbol, 0) + (quantity if side == 'buy' else -quantity)
                strategy.cash -= trade_value if side == 'buy' else -trade_value
                
                # Log the trade
                log_message = f"[{current_time.strftime('%H:%M:%S')}] [{strategy_id}] EXEC: {side.upper()} {quantity} {symbol} @ {price:,.2f} | Strat Cash: {strategy.cash:,.2f} | Pos: {strategy.positions[symbol]}"
                logging.info(log_message)
                
                # --- FIXED: This block writes the executed trade to a log file for the dashboard ---
                try:
                    with open('live_trades.log', 'a') as f:
                        f.write(log_message + '\n')
                except Exception as e:
                    self.logger.error(f"Failed to write to trade log file: {e}")
                # --- END OF FIX ---
                
                self._save_portfolio_to_disk()
            else:
                self.logger.warning(f"Order for {symbol} ({side} {quantity}) failed internal checks. Insufficient funds/shares. Strat Cash: {strategy.cash:,.2f}, Strat Shares: {strategy.positions.get(symbol,0)}.")
        else:
            self.logger.warning(f"Order for {symbol} ({side} {quantity}) denied by RiskManager.")


    def log_status(self):
        """Logs the current portfolio status, equity, and P&L."""
        logger = logging.getLogger('main_workflow')
        
        current_equity = self.get_total_equity()
        profit_loss = current_equity - self.initial_capital
        profit_loss_percent = (profit_loss / self.initial_capital) * 100 if self.initial_capital > 0 else 0


        status_message = (
            f"STATUS | Equity: {current_equity:,.2f} | P&L: {profit_loss:,.2f} ({profit_loss_percent:.2f}%) | Trades: {self.trade_count}"
        )
        logger.warning(status_message)


class YFinanceBroker:
    def __init__(self, symbols: list[str]):
        self.symbols = symbols
        self.logger = logging.getLogger("YFBroker")


    def get_live_ticks(self) -> dict:
        """Fetches latest 1-minute candle data for all symbols from Yahoo Finance."""
        ticks = {symbol: None for symbol in self.symbols}
        
        # --- FIXED: Removed the obsolete 'show_errors=False' argument ---
        data = yf.download(tickers=self.symbols, period="1d", interval="1m", progress=False)
        # --- END FIX ---


        if data.empty:
            self.logger.warning("No data fetched from YFinance. Returning empty ticks.")
            return ticks


        latest_time = data.index.max()


        if len(self.symbols) > 1 and isinstance(data.columns, pd.MultiIndex):
            for symbol in self.symbols:
                self._process_multi_index_tick(symbol, data, latest_time, ticks)
        elif len(self.symbols) == 1:
            price = data.loc[latest_time]['Close']
            if pd.notna(price):
                ticks[self.symbols[0]] = {'price': float(price), 'history': data['Close'].dropna()}
                self.logger.debug(f"Fetched tick for {self.symbols[0]}: {price:,.2f}")
            else:
                self.logger.warning(f"No valid price for {self.symbols[0]} in last tick.")
        return ticks


    def _process_multi_index_tick(self, symbol: str, data: pd.DataFrame, latest_time: pd.Timestamp, ticks_dict: dict):
        if ('Close', symbol) in data.columns:
            price = data.loc[latest_time][('Close', symbol)]
            if pd.notna(price):
                ticks_dict[symbol] = {'price': float(price), 'history': data[('Close', symbol)].dropna()}
                self.logger.debug(f"Fetched tick for {symbol}: {price:,.2f}")
            else:
                self.logger.warning(f"No valid price for {symbol} in last tick.")


class MockBroker:
    def __init__(self, symbols: list[str], initial_prices: dict[str, float]):
        self.symbols = symbols
        self.prices = initial_prices
        self.history_deques = {symbol: collections.deque(np.random.normal(price, 2, 500).tolist(), maxlen=500)
                               for symbol, price in initial_prices.items()}
        self.logger = logging.getLogger("MockBroker")
        self.logger.info(f"MockBroker initialized for {len(symbols)} symbols. Initial prices: {initial_prices}")


    def get_live_ticks(self) -> dict:
        """Generates mock live ticks with simulated price movement."""
        ticks = {}
        for symbol in self.symbols:
            self._generate_mock_tick(symbol, ticks)
        return ticks


    def _generate_mock_tick(self, symbol: str, ticks_dict: dict):
        # Simulate price movement
        self.prices[symbol] *= (1 + np.random.normal(0, 0.0005))
        
        # Update history deque
        self.history_deques[symbol].append(self.prices[symbol])
        
        ticks_dict[symbol] = {
            'price': self.prices[symbol],
            'history': pd.Series(list(self.history_deques[symbol])) # Convert deque to Series for strategy
        }
