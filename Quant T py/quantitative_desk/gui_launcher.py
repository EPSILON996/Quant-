# quantitative_desk/gui_launcher.py
"""
Quantitative Trading System: GUI Launcher (v1.1 - Audited & Fixed)
===================================================================
This is the definitive, audited version of the GUI. It contains a single,
complete __init__ method, resolving the structural bug from the previous version.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import threading
import queue
import pandas as pd
import logging

# --- Matplotlib for plotting within Tkinter ---
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# --- Import our existing architecture ---
from project_citadel.components_citadel import Alerter, RiskManager, ChiefInvestmentOfficer, HistoricalBroker
from project_citadel.core_config_citadel import LiveConfig

# Setup basic logging to a queue for the GUI
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        self.log_queue.put(self.format(record))

class TradingApp(tk.Tk):
    """The main GUI application class with a single, correct __init__ method."""
    def __init__(self):
        super().__init__()
        self.title("Quantitative Trading Desk")
        self.geometry("1200x800")

        self.simulation_thread = None
        self.data_queue = queue.Queue()
        self.log_queue = queue.Queue()

        # --- Main layout frames ---
        control_frame = ttk.Frame(self, padding="10")
        control_frame.pack(side="top", fill="x", padx=5, pady=5)
        plot_frame = ttk.Frame(self, padding="10")
        plot_frame.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        log_frame = ttk.LabelFrame(self, text="Logs", padding="10")
        log_frame.pack(side="bottom", fill="x", padx=5, pady=5)

        # --- Control Widgets ---
        ttk.Label(control_frame, text="Simulation Date (YYYY-MM-DD):").pack(side="left", padx=(0, 5))
        self.date_entry = ttk.Entry(control_frame, width=15)
        self.date_entry.pack(side="left")
        self.date_entry.insert(0, "2024-05-15")

        self.start_button = ttk.Button(control_frame, text="Start Historical Simulation", command=self.start_simulation)
        self.start_button.pack(side="left", padx=10)
        
        self.progress = ttk.Progressbar(control_frame, orient="horizontal", length=300, mode='determinate')
        self.progress.pack(side="left", padx=10)
        
        self.status_label = ttk.Label(control_frame, text="Status: Ready", width=50, anchor="w")
        self.status_label.pack(side="left", padx=10)

        # --- Live Plotting Area ---
        self.fig = Figure(figsize=(12, 6), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)
        self.ax.set_title("Portfolio Equity")
        self.ax.grid(True, linestyle='--', alpha=0.6)

        # --- Log Viewer ---
        self.log_text = tk.Text(log_frame, height=10, state='disabled', wrap='none', bg="#f0f0f0")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

    def update_status(self, text):
        self.status_label.config(text=f"Status: {text}")

    def update_plot(self, data):
        self.ax.clear()
        data.plot(ax=self.ax, color='dodgerblue', linewidth=2)
        self.ax.set_title("Live Portfolio Equity")
        self.ax.set_ylabel("Equity (INR)")
        self.ax.grid(True, linestyle='--', alpha=0.6)
        self.fig.tight_layout()
        self.canvas.draw()
        
    def write_log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + '\n')
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def process_queue(self):
        # Process data queue
        try:
            while True:
                message = self.data_queue.get_nowait()
                if "equity_curve" in message: self.update_plot(message["equity_curve"])
                if "status" in message: self.update_status(message["status"])
                if "progress" in message: self.progress['value'] = message["progress"]
                if "done" in message:
                    self.start_button.config(state="normal")
                    final_pnl = message.get("pnl", 0)
                    self.update_status(f"Simulation Finished. Final P&L: {final_pnl:,.2f} INR")
        except queue.Empty:
            pass
            
        # Process log queue
        try:
            while True:
                log_record = self.log_queue.get_nowait()
                self.write_log(log_record)
        except queue.Empty:
            pass
            
        self.after(100, self.process_queue)

    def start_simulation(self):
        self.start_button.config(state="disabled")
        self.update_status("Starting...")
        self.ax.clear(); self.ax.set_title("Portfolio Equity"); self.ax.grid(True, linestyle='--'); self.canvas.draw()
        self.log_text.config(state='normal'); self.log_text.delete(1.0, tk.END); self.log_text.config(state='disabled')
        
        try: sim_date = datetime.strptime(self.date_entry.get(), "%Y-%m-%d").date()
        except ValueError: messagebox.showerror("Error", "Invalid date format."); self.start_button.config(state="normal"); return

        self.simulation_thread = threading.Thread(target=run_simulation_logic, args=(sim_date, self.data_queue, self.log_queue), daemon=True)
        self.simulation_thread.start()
        self.process_queue()

def run_simulation_logic(sim_date, data_queue, log_queue):
    # Configure logging to go to the GUI queue
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, QueueHandler) for h in logger.handlers):
        logger.addHandler(QueueHandler(log_queue))

    try:
        data_queue.put({"status": "Configuring system...", "progress": 10})
        live_config = LiveConfig()

        data_queue.put({"status": "Initializing Historical Broker...", "progress": 30})
        broker = HistoricalBroker(live_config.SYMBOLS_TO_TRADE, sim_date)
        if broker.is_empty():
            messagebox.showerror("Data Error", f"No market data found for {sim_date}. It may be a weekend or holiday.")
            data_queue.put({"status": "Error: No data for selected date.", "done": True}); return
            
        data_queue.put({"status": "Broker Initialized. Starting Simulation...", "progress": 50})
        alerter = Alerter(); risk_manager = RiskManager(live_config.RiskParameters, alerter)
        cio = ChiefInvestmentOfficer(live_config, risk_manager, alerter)

        equity_history = []; timestamps = []; total_ticks = broker.get_total_ticks(); ticks_processed = 0
        
        while True:
            tick_data = broker.get_next_ticks()
            if tick_data is None: break
            
            sim_time, ticks = tick_data['timestamp'], tick_data['ticks']
            cio.on_market_data(ticks, sim_time)
            
            timestamps.append(sim_time); equity_history.append(cio.get_total_equity())
            ticks_processed += 1 # We process one timestamp at a time
            progress_val = 50 + (ticks_processed / total_ticks) * 50
            
            if ticks_processed % 10 == 0: # Update GUI every 10 minutes of sim time
                data_queue.put({"equity_curve": pd.Series(equity_history, index=timestamps), "progress": progress_val})

        final_equity = cio.get_total_equity(); pnl = final_equity - live_config.INITIAL_CAPITAL
        data_queue.put({"equity_curve": pd.Series(equity_history, index=timestamps), "pnl": pnl, "progress": 100, "done": True})

    except Exception as e:
        logging.error(f"Simulation thread failed: {e}", exc_info=True)
        data_queue.put({"status": f"FATAL ERROR: {e}", "done": True})

if __name__ == "__main__":
    app = TradingApp()
    app.mainloop()
