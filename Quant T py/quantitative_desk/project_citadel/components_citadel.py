# project_citadel/3_components_citadel.py (v13.0 - Definitive & Final)
""" The definitive version with stop-loss enforcement for the live engine. """
import logging, yfinance as yf, numpy as np, pandas as pd, collections
from datetime import datetime, time as dt_time
from project_atlas.strategy_library import STRATEGY_REGISTRY, Signal
from .strategies_citadel import LiveStrategy

class Alerter:
    def send(self, s: str, m: str): logging.critical(f"[ALERT] SUBJECT: {s} | BODY: {m}")
class RiskManager:
    def __init__(self, risk_parameters, alerter: Alerter):
        self.params = risk_parameters; self.alerter = alerter; self.peak_equity = 0.0; self.is_drawdown_breached = False
    def assess_new_day(self, v: float): self.peak_equity = v; self.is_drawdown_breached = False
    def is_trade_allowed(self, side: str, qty: int, price: float, portfolio) -> bool:
        dd = (self.peak_equity - portfolio.current_value) / self.peak_equity if self.peak_equity > 0 else 0
        if dd > self.params.DAILY_DRAWDOWN_LIMIT and not self.is_drawdown_breached:
            self.is_drawdown_breached = True; self.alerter.send("RISK BREACH", f"DD Limit of {self.params.DAILY_DRAWDOWN_LIMIT:.2%} hit.")
        if self.is_drawdown_breached and side == 'buy': logging.warning("[RISK] REJECTED (DD)"); return False
        if qty * price > self.params.MAX_ORDER_VALUE: logging.warning(f"[RISK] REJECTED (Order Value)"); return False
        return True
class ChiefInvestmentOfficer:
    def __init__(self, config, risk_manager: RiskManager, alerter: Alerter):
        self.config=config; self.risk_manager = risk_manager; self.initial_capital = config.INITIAL_CAPITAL
        self.symbols = config.SYMBOLS_TO_TRADE; self.current_value = self.initial_capital
        self.last_known_prices: dict[str, float] = {s: 0 for s in self.symbols}; self.trade_count = 0; self.strategies: dict[str, LiveStrategy] = {}
        for name, details in STRATEGY_REGISTRY.items():
            LiveClass = details["citadel_class"]; param_class = getattr(config.StrategyParameters, name)
            self.strategies[name] = LiveClass(name, param_class)
        self.risk_manager.assess_new_day(self.current_value); self._rebalance_capital()
    def _rebalance_capital(self):
        total_equity = self.get_total_equity(); weights = {name: 1.0 / len(self.strategies) for name in self.strategies}
        for name, s in self.strategies.items(): s.set_capital(total_equity * weights[name])
    def get_total_equity(self) -> float:
        equity = sum(s.get_equity(self.last_known_prices) for s in self.strategies.values())
        return self.initial_capital if equity == 0 and sum(sum(s.positions.values()) for s in self.strategies.values()) == 0 else equity
    def on_market_data(self, ticks: dict, sim_time: datetime):
        for symbol, tick in ticks.items():
            if tick: self.last_known_prices[symbol] = tick['price']
        self.current_value = self.get_total_equity(); self.risk_manager.peak_equity = max(self.risk_manager.peak_equity, self.current_value)
        for symbol, tick in ticks.items():
            if not (tick and tick.get('history')): continue
            current_price = float(tick['price'])
            for strat in self.strategies.values():
                if strat.positions[symbol] > 0 and current_price <= strat.stop_losses[symbol]:
                    logging.warning(f"[{strat.id}] STOP-LOSS HIT for {symbol} at {current_price:,.2f} (Stop was {strat.stop_losses[symbol]:,.2f})")
                    self.submit_order(strat.id, symbol, 'sell', strat.positions[symbol], sim_time); strat.stop_losses[symbol] = 0.0; continue
                signal = strat.decide_action(symbol, tick)
                if signal == Signal.BUY:
                    trade_capital = strat.cash * strat.risk_per_trade; qty = int(trade_capital / current_price) if current_price > 0 else 0
                    self.submit_order(strat.id, symbol, 'buy', qty, sim_time)
                elif signal == Signal.SELL:
                    qty = strat.positions.get(symbol, 0); self.submit_order(strat.id, symbol, 'sell', qty, sim_time)
    def submit_order(self, strat_id: str, symbol: str, side: str, qty: int, sim_time: datetime):
        price = self.last_known_prices.get(symbol)
        if qty > 0 and price and self.risk_manager.is_trade_allowed(side, qty, price, self):
            strat = self.strategies[strat_id]; trade_val = qty * price
            if (side == 'buy' and strat.cash >= trade_val) or (side == 'sell' and strat.positions.get(symbol, 0) >= qty):
                self.trade_count += 1; strat.positions[symbol] += qty if side == 'buy' else -qty
                strat.cash -= trade_val if side == 'buy' else -trade_val; logging.info(f"[{strat_id}] EXECUTED: {side.upper()} {qty} {symbol} @ {price:,.2f}")
class YFinanceBroker:
    def __init__(self, symbols:list[str]): self.symbols=symbols; self.tickers={s:yf.Ticker(s) for s in symbols}
    def get_live_ticks(self) -> dict:
        ticks={};
        for s,t in self.tickers.items():
            data=t.history(period="1d",interval="1m"); ticks[s] = {'price':data['Close'].iloc[-1],'history':data['Close']} if not data.empty else None
        return ticks
class MockBroker:
    def __init__(self, symbols:list[str], initial_prices:dict):
        self.symbols=symbols; self.prices=initial_prices
        self.history={s:collections.deque(np.random.normal(p,2,500).tolist(),maxlen=500) for s,p in initial_prices.items()}
    def get_live_ticks(self) -> dict:
        ticks={};
        for s in self.symbols:
            self.prices[s] += self.prices[s]*np.random.normal(0.0,0.0005)
            self.history[s].append(self.prices[s]); ticks[s]={'price':self.prices[s],'history':self.history[s]}
        return ticks
