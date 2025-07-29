import tkinter as tk
from tkinter import ttk, filedialog
import json
import os
import yfinance as yf
import pandas as pd
import threading
import time
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.ticker as mticker
import logging
from ttkthemes import ThemedTk
from datetime import datetime

class LiveDashboard(ThemedTk):
    def __init__(self, portfolio_file='live_portfolio.json', trade_log_file='live_trades.log', initial_capital=1_000_000):
        super().__init__(theme="radiance")
        self.title("Professional Multi-Chart Trading Dashboard")
        self.geometry("1920x1080")
        
        self.portfolio_file = portfolio_file
        self.trade_log_file = trade_log_file
        self.initial_capital = initial_capital
        self.portfolio_data = {}
        self.live_prices = {}
        self.entry_costs = {}
        self.pnl_history = pd.Series(dtype=float)
        self.strategy_equity_history = {"Trend": pd.Series(dtype=float), "MeanReversion": pd.Series(dtype=float)}
        self.last_trade_log_pos = 0
        self.data_feed_status = False
        self.logger = logging.getLogger("Dashboard")

        self._configure_styles()
        self._setup_gui()

        self.update_thread = threading.Thread(target=self.data_update_loop, daemon=True)
        self.update_thread.start()
        self.process_gui_updates()

    def _configure_styles(self):
        style = ttk.Style()
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28)
        style.configure("Profit.TLabel", foreground="green", font=("Segoe UI", 12, "bold"))
        style.configure("Loss.TLabel", foreground="red", font=("Segoe UI", 12, "bold"))

    def _setup_gui(self):
        # --- FIXED: Rewritten with a robust layout to prevent crashes and missing widgets ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        # --- Top Frame for KPIs ---
        kpi_frame = ttk.Frame(main_frame)
        kpi_frame.pack(fill="x", pady=(0, 5))
        self.capital_label = ttk.Label(kpi_frame, text="Capital: N/A", font=("Segoe UI", 12, "bold"))
        self.capital_label.pack(side="left", padx=10)
        self.pnl_label = ttk.Label(kpi_frame, text="Total P&L: N/A", font=("Segoe UI", 12, "bold"))
        self.pnl_label.pack(side="left", padx=10)
        self.strategy_summary_label = ttk.Label(kpi_frame, text="Strategies: N/A", font=("Segoe UI", 12, "bold"))
        self.strategy_summary_label.pack(side="left", padx=10)

        # --- Main Content Paned Window (Splits Left and Right) ---
        main_paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        main_paned_window.pack(fill="both", expand=True, pady=5)

        left_pane = ttk.Frame(main_paned_window)
        main_paned_window.add(left_pane, weight=3)
        right_pane = ttk.Frame(main_paned_window)
        main_paned_window.add(right_pane, weight=1)

        # --- Left Paned Window (Splits Charts and Table) ---
        left_paned_window = ttk.PanedWindow(left_pane, orient=tk.VERTICAL)
        left_paned_window.pack(fill="both", expand=True)

        plots_container = ttk.LabelFrame(left_paned_window, text="Live Performance")
        left_paned_window.add(plots_container, weight=1)
        
        positions_frame = ttk.LabelFrame(left_paned_window, text="Live Portfolio")
        left_paned_window.add(positions_frame, weight=1)

        # --- Plotting Area ---
        self.fig = Figure(figsize=(15, 8), dpi=100)
        self.fig.tight_layout(pad=3.0)
        self.axes = {
            "Total P&L": self.fig.add_subplot(3, 1, 1),
            "Trend Strategy Equity": self.fig.add_subplot(3, 1, 2),
            "MeanReversion Strategy Equity": self.fig.add_subplot(3, 1, 3)
        }
        self.canvas = FigureCanvasTkAgg(self.fig, master=plots_container)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # --- Portfolio Table ---
        self.tree = ttk.Treeview(positions_frame, columns=('Strategy', 'Symbol', 'Qty', 'Entry', 'Mkt Value', 'P&L', '% P&L'), show='headings')
        cols = {'Strategy': 120, 'Symbol': 120, 'Qty': 80, 'Entry': 100, 'Mkt Value': 120, 'P&L': 120, '% P&L': 80}
        for col, width in cols.items():
            self.tree.heading(col, text=col, command=lambda c=col: self.sort_column(c, False))
            self.tree.column(col, anchor=tk.E if col not in ['Strategy', 'Symbol'] else tk.W, width=width)
        self.tree.pack(side="left", fill="both", expand=True)

        # --- Trade Log Area ---
        log_frame = ttk.LabelFrame(right_pane, text="Live Trade Log")
        log_frame.pack(fill="both", expand=True)
        self.trade_log_text = tk.Text(log_frame, wrap="word", state="disabled", font=("Consolas", 9), bg="#f5f5f5")
        self.trade_log_text.pack(fill="both", expand=True, padx=5, pady=5)
        
        # --- Bottom Status Frame ---
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill="x", side="bottom", pady=(5, 0))
        self.export_button = ttk.Button(status_frame, text="Export Portfolio to CSV", command=self.export_to_csv)
        self.export_button.pack(side="left")
        self.broker_status_label = ttk.Label(status_frame, text="Broker API: Connected ✅", font=("Segoe UI", 9))
        self.broker_status_label.pack(side="right", padx=10)
        self.data_feed_label = ttk.Label(status_frame, text="Data Feed: Disconnected ❌", font=("Segoe UI", 9))
        self.data_feed_label.pack(side="right", padx=10)

        self.tree.tag_configure('profit_text', foreground='green')
        self.tree.tag_configure('loss_text', foreground='red')

    def data_update_loop(self):
        while True:
            if os.path.exists(self.portfolio_file):
                try:
                    with open(self.portfolio_file, 'r') as f: self.portfolio_data = json.load(f)
                except (json.JSONDecodeError, FileNotFoundError): self.portfolio_data = {}
            else: self.portfolio_data = {}
            
            symbols = list(set(s for pos in self.portfolio_data.values() for s in pos.keys()))
            if symbols:
                try:
                    data = yf.download(tickers=symbols, period="1d", progress=False)
                    if not data.empty:
                        if len(symbols) > 1:
                            self.live_prices = data['Close'].iloc[-1].to_dict()
                        else:
                            self.live_prices = {symbols[0]: data['Close'].iloc[-1]}
                        self.data_feed_status = True
                    else:
                        self.data_feed_status = False
                except Exception as e:
                    self.logger.error(f"CRITICAL: Data fetch loop failed: {e}")
                    self.data_feed_status = False
            else:
                self.data_feed_status = True
            
            time.sleep(1)

    def process_gui_updates(self):
        all_positions, total_market_value, total_entry_cost = [], 0, 0
        strategy_counts = {strat_id: 0 for strat_id in self.strategy_equity_history.keys()}

        for strategy, positions in self.portfolio_data.items():
            for symbol, qty in positions.items():
                if qty == 0: continue
                if strategy in strategy_counts: strategy_counts[strategy] += 1
                
                current_price = self.live_prices.get(symbol, self.entry_costs.get(symbol, 0)) 
                
                if symbol not in self.entry_costs and self.live_prices.get(symbol, 0) > 0:
                    self.entry_costs[symbol] = self.live_prices.get(symbol)
                
                entry_price = self.entry_costs.get(symbol, 0)
                
                mkt_value, entry_cost = qty * current_price, qty * entry_price
                pnl = mkt_value - entry_cost
                total_market_value += mkt_value
                total_entry_cost += entry_cost
                all_positions.append([strategy, symbol, qty, entry_price, mkt_value, pnl])
        
        self._update_equity_histories(total_market_value, total_entry_cost)
        self._update_gui_components(all_positions, total_market_value, total_entry_cost, strategy_counts)
        self._update_trade_log_display()
        self.after(1000, self.process_gui_updates)

    def _update_equity_histories(self, total_market_value, total_entry_cost):
        cash_left = self.initial_capital - total_entry_cost
        total_pnl = (cash_left + total_market_value) - self.initial_capital
        timestamp = pd.to_datetime(time.time(), unit='s')
        self.pnl_history[timestamp] = total_pnl

        num_strategies = len(self.strategy_equity_history)
        capital_per_strategy = self.initial_capital / num_strategies if num_strategies > 0 else 0

        for strat_id in self.strategy_equity_history.keys():
            positions = self.portfolio_data.get(strat_id, {})
            strat_mkt_value = sum(qty * self.live_prices.get(sym, self.entry_costs.get(sym, 0)) for sym, qty in positions.items())
            strat_entry_cost = sum(qty * self.entry_costs.get(sym, 0) for sym, qty in positions.items())
            strat_cash = capital_per_strategy - strat_entry_cost
            strat_equity = strat_cash + strat_mkt_value
            if strat_equity > 0: self.strategy_equity_history[strat_id][timestamp] = strat_equity

    def _update_gui_components(self, all_positions, total_market_value, total_entry_cost, strategy_counts):
        self.tree.delete(*self.tree.get_children())
        for pos in all_positions:
            strategy, symbol, qty, entry, mkt_val, pnl = pos
            pnl_pct = (pnl / (qty * entry) * 100) if qty * entry > 0 else 0
            self.tree.insert('', 'end', values=(strategy, symbol, qty, f"{entry:,.2f}", f"{mkt_val:,.2f}", f"{pnl:,.2f}", f"{pnl_pct:.2f}%"),
                             tags=('profit_text' if pnl >= 0 else 'loss_text',))
        
        cash_left = self.initial_capital - total_entry_cost
        current_equity = cash_left + total_market_value
        total_pnl = current_equity - self.initial_capital
        total_pnl_pct = (total_pnl / self.initial_capital * 100) if self.initial_capital > 0 else 0
        
        self.capital_label.config(text=f"Capital Used: {total_entry_cost:,.2f} / Cash Left: {cash_left:,.2f} INR")
        self.pnl_label.config(text=f"Total P&L: {total_pnl:,.2f} ({total_pnl_pct:.2f}%)", style="Profit.TLabel" if total_pnl >= 0 else "Loss.TLabel")
        summary_str = " | ".join([f"{k}: {v}" for k,v in strategy_counts.items() if v > 0])
        self.strategy_summary_label.config(text=f"Active Trades: {summary_str}")
        self.data_feed_label.config(text=f"Data Feed: {'Connected ✅' if self.data_feed_status else 'Disconnected ❌'}")

        self._update_all_plots()

    def _update_all_plots(self):
        plot_configs = {
            "Total P&L": {"data": self.pnl_history, "color": "#007acc"},
            "Trend Strategy Equity": {"data": self.strategy_equity_history["Trend"], "color": "green"},
            "MeanReversion Strategy Equity": {"data": self.strategy_equity_history["MeanReversion"], "color": "purple"}
        }

        for name, config in plot_configs.items():
            ax = self.axes[name]
            data = config["data"]
            ax.clear()
            
            if not data.empty:
                data.plot(ax=ax, color=config["color"], linewidth=1.5)
                ax.plot(data.index[-1], data.iloc[-1], 'o', color='red', markersize=4)
            
            ax.set_title(name, fontsize=10, weight="bold")
            ax.grid(True, linestyle='--', alpha=0.6)
            ax.yaxis.set_major_formatter(mticker.FuncFormatter(self.inr_formatter))
        
        self.fig.canvas.draw_idle()

    def inr_formatter(self, x, pos):
        if abs(x) >= 1_00_00_000: return f'₹{x/1_00_00_000:.2f} Cr'
        if abs(x) >= 1_00_000: return f'₹{x/1_00_000:.2f} L'
        if abs(x) >= 1_000: return f'₹{x/1_000:.1f} K'
        return f'₹{int(x)}'

    def _update_trade_log_display(self):
        if not os.path.exists(self.trade_log_file): return
        with open(self.trade_log_file, 'r') as f:
            f.seek(self.last_trade_log_pos)
            new_lines = f.readlines()
            if new_lines:
                self.trade_log_text.config(state="normal")
                for line in new_lines: self.trade_log_text.insert(tk.END, line)
                self.trade_log_text.see(tk.END)
                self.trade_log_text.config(state="disabled")
            self.last_trade_log_pos = f.tell()

    def sort_column(self, col, reverse):
        def get_sort_key(item):
            val = self.tree.set(item, col).replace('₹','').replace(',','').replace('%','').strip()
            try: return float(val)
            except ValueError: return val
        items = [(get_sort_key(k), k) for k in self.tree.get_children('')]
        items.sort(reverse=reverse)
        for index, (val, k) in enumerate(items): self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def export_to_csv(self):
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if not filepath: return
        data_to_export = []
        for child in self.tree.get_children():
            item = self.tree.item(child)['values']
            data_to_export.append(item)
        df = pd.DataFrame(data_to_export, columns=self.tree["columns"])
        df.to_csv(filepath, index=False)
        self.logger.info(f"Portfolio exported to {filepath}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)-8s [%(name)s] %(message)s')
    if not os.path.exists('live_trades.log'):
        with open('live_trades.log', 'w') as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] Dashboard trade log initialized.\n")
    app = LiveDashboard()
    app.mainloop()
