import itertools
import logging
import pandas as pd
import numpy as np
import random
import matplotlib.pyplot as plt
import os

from tqdm import tqdm
from collections import defaultdict, deque

from .strategy_library import STRATEGY_REGISTRY, Signal
from .core_config import FirmConfig, StrategyConfig
from .infrastructure import PortfolioManager, MarketSimulator

class TradeAnalyzer:
    def __init__(self, raw_trades: list[dict]):
        self.raw_trades = raw_trades

    def calculate_round_trip_pnl(self) -> list[float]:
        pnl_list = []
        open_buys = defaultdict(deque)

        for trade in self.raw_trades:
            if trade['side'] == 'buy':
                open_buys[trade['id']].append(trade)
            elif trade['side'] == 'sell':
                if not open_buys[trade['id']]:
                    continue

                sell_qty = trade['qty']
                sell_price = trade['price']
                rt_pnl = 0.0

                while sell_qty > 0 and open_buys[trade['id']]:
                    buy_trade = open_buys[trade['id']][0]
                    match_qty = min(sell_qty, buy_trade['qty'])
                    rt_pnl += (sell_price - buy_trade['price']) * match_qty
                    buy_trade['qty'] -= match_qty
                    sell_qty -= match_qty
                    if buy_trade['qty'] <= 1e-6:
                        open_buys[trade['id']].popleft()

                if rt_pnl != 0.0:
                    pnl_list.append(rt_pnl)
        return pnl_list

class PerformanceAnalyzer:
    # CHANGED: The constructor now accepts optional benchmark_data.
    def __init__(self, equity_curve: pd.Series, trades: list, market_data: pd.DataFrame, risk_free_rate: float, benchmark_data: pd.DataFrame = None):
        self.equity_curve = equity_curve
        self.returns = equity_curve.pct_change().dropna()
        self.trades = trades
        self.market_data = market_data
        self.risk_free_rate = risk_free_rate
        # ADDED: Store the benchmark data.
        self.benchmark_data = benchmark_data

    def calculate_metrics(self) -> dict:
        if self.returns.empty or len(self.returns) < 2:
            # MODIFIED: Return zero for all metrics, including the new alpha and beta.
            return {k: 0 for k in ['sharpe', 'sortino', 'calmar', 'max_drawdown', 'alpha', 'beta', 'equity_curve', 'benchmark_data']}
        
        annualized_returns = self.returns.mean() * 252
        annualized_volatility = self.returns.std() * np.sqrt(252)
        sharpe_ratio = (annualized_returns - self.risk_free_rate) / annualized_volatility if annualized_volatility > 0 else 0

        downside_returns = self.returns[self.returns < 0]
        downside_deviation = downside_returns.std() * np.sqrt(252) if not downside_returns.empty else 0
        sortino_ratio = (annualized_returns - self.risk_free_rate) / downside_deviation if downside_deviation > 0 else 0

        cumulative_returns = (1 + self.returns).cumprod()
        peak_equity = cumulative_returns.expanding(min_periods=1).max()
        drawdown = (cumulative_returns - peak_equity) / peak_equity
        max_drawdown = drawdown.min()
        calmar_ratio = annualized_returns / abs(max_drawdown) if max_drawdown < 0 else 0

        # --- ADDED: Alpha and Beta Calculation ---
        alpha, beta = 0, 0
        if self.benchmark_data is not None and not self.benchmark_data.empty:
            # Align strategy and benchmark returns by their date index to ensure they match up.
            benchmark_returns = self.benchmark_data['Close'].pct_change().dropna()
            aligned_data = pd.DataFrame({'strategy': self.returns, 'benchmark': benchmark_returns}).dropna()
            
            if len(aligned_data) > 2:
                # Calculate covariance and benchmark variance on an annualized basis.
                covariance = aligned_data['strategy'].cov(aligned_data['benchmark']) * 252
                benchmark_variance = aligned_data['benchmark'].var() * 252
                
                # Calculate Beta.
                beta = covariance / benchmark_variance if benchmark_variance > 0 else 0
                
                # Calculate Alpha using the Capital Asset Pricing Model (CAPM).
                benchmark_annualized_returns = aligned_data['benchmark'].mean() * 252
                expected_return = self.risk_free_rate + beta * (benchmark_annualized_returns - self.risk_free_rate)
                alpha = annualized_returns - expected_return
        # --- END: Alpha and Beta Calculation ---

        # MODIFIED: Return dictionary now includes alpha, beta, and benchmark_data.
        return {
            'sharpe': sharpe_ratio, 'sortino': sortino_ratio, 'calmar': calmar_ratio,
            'max_drawdown': max_drawdown, 'alpha': alpha, 'beta': beta,
            'equity_curve': self.equity_curve,
            'benchmark_data': self.benchmark_data # Pass benchmark data through for plotting.
        }

class ParameterOptimizer:
    # CHANGED: The constructor now accepts optional benchmark_data.
    def __init__(self, firm_config: FirmConfig, data: pd.DataFrame, benchmark_data: pd.DataFrame = None):
        self.config = firm_config
        self.data = data
        # ADDED: Store the benchmark data.
        self.benchmark_data = benchmark_data
        self.results = []
        self.logger = logging.getLogger("Optimizer")

    def run(self) -> pd.DataFrame:
        grids = {
            "Trend": list(itertools.product([20, 40], [50, 100], [14], [55], [0.05, 0.07], [0.02, 0.03])),
            "MeanReversion": list(itertools.product([20, 30], [2.0, 2.5], [14], [40], [0.03, 0.04], [0.015, 0.02]))
        }
        all_combos = list(itertools.product(grids["Trend"], grids["MeanReversion"]))
        num_trials = self.config.BacktestParameters.OPTIMIZATION_TRIALS
        combos_to_test = random.sample(all_combos, min(num_trials, len(all_combos)))
        
        self.logger.info(f"Running Randomized Search with {len(combos_to_test)} trials for {self.data.attrs.get('symbol', '...')}")

        for trend_params, mr_params in tqdm(combos_to_test, desc=f"Optimizing {self.data.attrs.get('symbol', '...')}", leave=False, ncols=80):
            cfgs = {
                "Trend": StrategyConfig.TrendFollowing(*trend_params),
                "MeanReversion": StrategyConfig.MeanReversion(*mr_params)
            }
            firm_portfolio_manager = PortfolioManager(self.config, cfgs)
            market_simulator = MarketSimulator(self.config, self.data, firm_portfolio_manager)
            equity_curve, trades = market_simulator.run()
            
            # CHANGED: Pass the benchmark_data to the PerformanceAnalyzer.
            metrics = PerformanceAnalyzer(equity_curve, trades, self.data, self.config.RISK_FREE_RATE, self.benchmark_data).calculate_metrics()
            
            res = {
                'trend_sw': trend_params[0], 'trend_lw': trend_params[1], 'trend_tp': trend_params[4], 'trend_sl': trend_params[5],
                'mr_w': mr_params[0], 'mr_std': mr_params[1], 'mr_tp': mr_params[4], 'mr_sl': mr_params[5],
                'final_equity': equity_curve.iloc[-1] if not equity_curve.empty else 0
            }
            res.update(metrics)
            self.results.append(res)
        return pd.DataFrame(self.results)

class ReportGenerator:
    def __init__(self, symbol: str, results: pd.DataFrame):
        self.symbol = symbol
        self.results = results
        self.logger = logging.getLogger("ReportGenerator")
        
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.curve_storage_dir = os.path.join(project_root, 'curve_storage')
        os.makedirs(self.curve_storage_dir, exist_ok=True)
        self.logger.debug(f"Curve storage directory: {self.curve_storage_dir}")

    def get_best_params(self) -> pd.Series | None:
        if self.results.empty or 'sharpe' not in self.results.columns or self.results['sharpe'].isnull().all():
            self.logger.warning(f"No valid Sharpe ratio found for {self.symbol}.")
            return None
        return self.results.loc[self.results['sharpe'].idxmax()]

    def generate(self, show_plots: bool = False):
        best_params = self.get_best_params()
        if best_params is None:
            self.logger.info(f"Analysis for {self.symbol} failed: No valid parameters found.")
        else:
            # ADDED: Log the new Alpha and Beta metrics.
            self.logger.info(
                f"Analysis for {self.symbol} complete. "
                f"Best Sharpe: {best_params['sharpe']:.2f}, "
                f"Alpha: {best_params['alpha']:.3f}, Beta: {best_params['beta']:.3f}"
            )
            # CHANGED: Drop non-serializable objects (equity_curve AND benchmark_data) before logging.
            self.logger.info(f"Best Parameters: {best_params.drop(['equity_curve', 'benchmark_data']).to_dict()}")

            if show_plots and 'equity_curve' in best_params and not best_params['equity_curve'].empty:
                equity_curve = best_params['equity_curve']
                
                plt.figure(figsize=(14, 7))
                plt.plot(equity_curve, label='Strategy Equity', color='blue')
                
                # --- ADDED: Logic to plot the benchmark performance ---
                if 'benchmark_data' in best_params and best_params['benchmark_data'] is not None:
                    benchmark_data = best_params['benchmark_data']
                    # Align benchmark data with the equity curve's start date.
                    benchmark_data_aligned = benchmark_data[benchmark_data.index >= equity_curve.index[0]]
                    if not benchmark_data_aligned.empty:
                        # Normalize benchmark to start at the same initial capital as the strategy for comparison.
                        initial_capital = equity_curve.iloc[0]
                        benchmark_normalized = (benchmark_data_aligned['Close'] / benchmark_data_aligned['Close'].iloc[0]) * initial_capital
                        plt.plot(benchmark_normalized, label='Benchmark (NIFTY 50)', color='grey', linestyle='--')
                # --- END: Benchmark plotting logic ---
                
                plt.title(f'Equity Curve vs. Benchmark for {self.symbol}')
                plt.xlabel('Date')
                plt.ylabel('Portfolio Value (INR)')
                plt.legend()
                plt.grid(True)
                plt.tight_layout()
                
                plot_filename = os.path.join(self.curve_storage_dir, f"equity_curve_{self.symbol}.png")
                plt.savefig(plot_filename)
                self.logger.info(f"Equity curve plot saved to {plot_filename}")
                plt.close()
            else:
                self.logger.info(f"No equity curve to plot for {self.symbol} or show_plots is False.")
