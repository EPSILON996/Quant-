# project_atlas/analysis.py (v13.0 - Definitive & Final)
""" The definitive version with strategy-aware analytics and daily alpha analysis. """
import itertools, logging, pandas as pd, numpy as np, seaborn as sns, matplotlib.pyplot as plt, matplotlib.gridspec as gridspec
from tqdm import tqdm
from collections import defaultdict, deque
from .strategy_library import STRATEGY_REGISTRY, Signal
from .core_config import FirmConfig, StrategyConfig
from .infrastructure import PortfolioManager, MarketSimulator

class TradeAnalyzer:
    def __init__(self, raw_trades: list[dict]): self.raw_trades = raw_trades
    def calculate_round_trip_pnl(self) -> list[float]:
        pnl_list = []; open_buys = defaultdict(deque)
        for trade in self.raw_trades:
            strategy_id = trade['id']
            if trade['side'] == 'buy': open_buys[strategy_id].append(trade)
            elif trade['side'] == 'sell':
                sell_qty_rem = trade['qty']; sell_price = trade['price']
                if not open_buys[strategy_id]: continue
                rt_pnl = 0.0
                while sell_qty_rem > 0 and open_buys[strategy_id]:
                    buy_trade = open_buys[strategy_id][0]
                    qty_match = min(sell_qty_rem, buy_trade['qty'])
                    rt_pnl += (sell_price - buy_trade['price']) * qty_match
                    buy_trade['qty'] -= qty_match; sell_qty_rem -= qty_match
                    if buy_trade['qty'] <= 1e-6: open_buys[strategy_id].popleft()
                if rt_pnl != 0.0: pnl_list.append(rt_pnl)
        return pnl_list
class PerformanceAnalyzer:
    def __init__(self, equity: pd.Series, trades: list, market_data: pd.DataFrame, rfr: float):
        self.eq = equity; self.ret = equity.pct_change().dropna(); self.trades = trades
        self.market = market_data['Close'].pct_change().dropna(); self.rfr = rfr
    def calculate_metrics(self) -> dict:
        if self.ret.empty or len(self.ret) < 2: return {k: 0 for k in ['sharpe','sortino','calmar','max_drawdown','win_rate','profit_factor','total_trades','avg_ret_up_days','avg_ret_down_days']}
        analyzer = TradeAnalyzer(self.trades); round_trip_pnl = analyzer.calculate_round_trip_pnl()
        ann_ret = self.ret.mean()*252; ann_vol = self.ret.std()*np.sqrt(252); sharpe = (ann_ret - self.rfr) / ann_vol if ann_vol > 0 else 0
        down_ret = self.ret[self.ret < 0]; down_std = down_ret.std()*np.sqrt(252) if not down_ret.empty else 0; sortino = (ann_ret - self.rfr) / down_std if down_std > 0 else 0
        cum = (1 + self.ret).cumprod(); peak = cum.expanding(min_periods=1).max(); dd = (cum - peak)/peak; mdd = dd.min(); calmar = ann_ret / abs(mdd) if mdd < 0 else 0
        total_trades = len(round_trip_pnl)
        if total_trades > 0:
            wins = [p for p in round_trip_pnl if p > 0]; losses = [p for p in round_trip_pnl if p < 0]
            win_rate = len(wins) / total_trades if total_trades > 0 else 0
            profit_factor = sum(wins) / abs(sum(losses)) if sum(losses) < 0 else float('inf')
        else: win_rate, profit_factor = 0, 0
        aligned_ret = pd.DataFrame({'strat': self.ret, 'market': self.market}).dropna()
        up_market_days = aligned_ret[aligned_ret['market'] > 0]; down_market_days = aligned_ret[aligned_ret['market'] <= 0]
        avg_ret_up_days = up_market_days['strat'].mean() if not up_market_days.empty else 0
        avg_ret_down_days = down_market_days['strat'].mean() if not down_market_days.empty else 0
        return {'sharpe':sharpe, 'sortino':sortino, 'calmar':calmar, 'max_drawdown':mdd, 'win_rate':win_rate, 'profit_factor':profit_factor, 'total_trades':total_trades, 'avg_ret_up_days': avg_ret_up_days, 'avg_ret_down_days': avg_ret_down_days, 'equity_curve':self.eq}
class ParameterOptimizer:
    def __init__(self, firm_config: FirmConfig, data: pd.DataFrame):
        self.config=firm_config; self.data=data; self.results=[]
    def run(self) -> pd.DataFrame:
        grids = {"Trend": list(itertools.product([20, 40, 60], [100, 150, 200])), "MeanReversion": list(itertools.product([20, 30], [2.0, 2.5]))}
        combos = list(itertools.product(grids["Trend"], grids["MeanReversion"]))
        for trend_p, mr_p in tqdm(combos, desc=f"Optimizing {self.data.attrs.get('symbol', '...')}", leave=False, ncols=80):
            cfgs = {"Trend": StrategyConfig.TrendFollowing(*trend_p), "MeanReversion": StrategyConfig.MeanReversion(*mr_p)}
            firm = PortfolioManager(self.config, cfgs)
            market = MarketSimulator(self.config, self.data, firm)
            eq, trades = market.run(); metrics = PerformanceAnalyzer(eq, trades, self.data, self.config.RISK_FREE_RATE).calculate_metrics()
            res = {'trend_sw': trend_p[0], 'trend_lw': trend_p[1], 'mr_w': mr_p[0], 'mr_std': mr_p[1], 'final_equity': eq.iloc[-1] if not eq.empty else 0}
            res.update(metrics); self.results.append(res)
        return pd.DataFrame(self.results)
class ReportGenerator:
    def __init__(self, symbol: str, results: pd.DataFrame):
        self.symbol=symbol; self.results=results
    def generate(self, show_plots: bool = True):
        best_params = self.get_best_params()
        if best_params is None: logging.error(f"Could not generate report for {self.symbol}."); return
        self._print_summary(best_params)
        if show_plots: self._plot_results(best_params)
    def _print_summary(self, best: pd.Series):
        header = f"\n{'='*60}\n--- INSTITUTIONAL QUANTITATIVE RESEARCH REPORT: {self.symbol} ---\n{'='*60}"
        params = f"Optimal Parameters (based on Sharpe Ratio):\n  - Trend: MA({int(best['trend_sw'])}, {int(best['trend_lw'])})\n  - MeanReversion: BBands({int(best['mr_w'])}, {best['mr_std']}σ)"
        perf = f"{'-'*60}\nPerformance Metrics:\n  - Final Equity:      ₹{best['final_equity']:,.2f}\n  - Sharpe Ratio:      {best['sharpe']:.2f}\n  - Max Drawdown:      {best['max_drawdown']:.2%}"
        stats = f"{'-'*30}\nTrade Statistics:\n  - Total Trades:      {int(best['total_trades'])}\n  - Win Rate:          {best['win_rate']:.2%}\n  - Profit Factor:     {best['profit_factor']:.2f}"
        alpha_header = f"{'-'*60}\nDaily Performance vs Market:"; alpha_up = f"  - Avg. Daily Return on UP Market Days:   {best['avg_ret_up_days']*10000:,.2f} bps"
        alpha_down = f"  - Avg. Daily Return on DOWN Market Days: {best['avg_ret_down_days']*10000:,.2f} bps\n{'='*60}"
        print(f"{header}\n{params}\n{perf}\n{stats}\n{alpha_header}\n{alpha_up}\n{alpha_down}")
    def _plot_results(self, best: pd.Series):
        equity_curve = best.get('equity_curve');
        if equity_curve is None or equity_curve.empty: logging.warning(f"Skipping plot for {self.symbol}."); return
        fig=plt.figure(figsize=(18,12)); gs=gridspec.GridSpec(2,2); ax_eq=fig.add_subplot(gs[0,:]); ax_t=fig.add_subplot(gs[1,0]); ax_mr=fig.add_subplot(gs[1,1])
        fig.suptitle(f'Performance Analysis for {self.symbol}', fontsize=20); equity_curve.plot(ax=ax_eq, color='navy'); ax_eq.set_title('Equity Curve'); ax_eq.grid(True, alpha=0.3)
        sns.heatmap(self.results.pivot_table(index='trend_sw', columns='trend_lw', values='sharpe'), ax=ax_t, annot=True, fmt=".2f", cmap="viridis").set_title('Trend Sharpe Ratios')
        sns.heatmap(self.results.pivot_table(index='mr_w', columns='mr_std', values='sharpe'), ax=ax_mr, annot=True, fmt=".2f", cmap="plasma").set_title('Mean Reversion Sharpe Ratios')
        plt.tight_layout(rect=[0, 0.03, 1, 0.95]); plt.show()
    def get_best_params(self) -> pd.Series | None:
        if self.results.empty or 'sharpe' not in self.results.columns or self.results['sharpe'].isnull().all(): return None
        return self.results.loc[self.results['sharpe'].idxmax()]
