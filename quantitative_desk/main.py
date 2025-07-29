import logging
import time
import argparse
import json
import os
import random
import pytz 
import pandas as pd
import numpy as np 
from datetime import datetime, time as dt_time, timedelta
from multiprocessing import Pool, cpu_count
from functools import partial
import subprocess  # --- ADDED: To launch the dashboard as a separate process

# Import components from project_atlas
from project_atlas.analysis import ParameterOptimizer, ReportGenerator
from project_atlas.infrastructure import DataLoader
from project_atlas.core_config import FirmConfig as AtlasConfig

# Import components from project_citadel
from project_citadel.components_citadel import Alerter, RiskManager, ChiefInvestmentOfficer, YFinanceBroker, MockBroker
from project_citadel.core_config_citadel import LiveConfig

def run_analysis_for_symbol(symbol_data_tuple, benchmark_data=None):
    """
    Runs parameter optimization for a single symbol using Project Atlas.
    Designed for multiprocessing pool.
    """
    symbol, historical_data = symbol_data_tuple
    
    atlas_config = AtlasConfig()
    optimizer = ParameterOptimizer(atlas_config, historical_data, benchmark_data)
    
    historical_data.attrs['symbol'] = symbol
    
    results_df = optimizer.run()
    reporter = ReportGenerator(symbol, results_df)
    
    best_params_series = reporter.get_best_params()
    
    # We can disable plot generation during optimization to avoid GUI pop-ups
    reporter.generate(show_plots=False)
    
    return symbol, best_params_series

def setup_logging():
    """Configures basic logging for the application."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)-8s [%(name)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def is_market_open() -> bool:
    """Checks if the Indian stock market is currently open based on IST."""
    ist = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist)
    
    return now_ist.weekday() < 5 and dt_time(9, 15) <= now_ist.time() <= dt_time(15, 30)

def run_automated_workflow(simulate: bool, force_reoptimize: bool):
    """
    Orchestrates the unified trading workflow: optimization, simulation, or live trading.
    """
    setup_logging()
    logger = logging.getLogger('main_workflow')
    
    mode = "SIMULATION" if simulate else "LIVE"
    logger.warning(f"--- UNIFIED WORKFLOW STARTED IN [{mode}] MODE ---")
    
    atlas_config = AtlasConfig()
    cache_file = 'optimal_params.json'
    all_best_params = {}
    
    # --- Stage 1: Parameter Optimization / Loading Cache ---
    if os.path.exists(cache_file) and not force_reoptimize:
        logger.warning(f"Found parameter cache '{cache_file}'. Loading parameters.")
        with open(cache_file, 'r') as f:
            all_best_params = {s: pd.Series(p) for s, p in json.load(f).items()}
    else:
        if force_reoptimize:
            logger.warning("Forcing re-optimization as requested.")
        else:
            logger.warning("No parameter cache found. Starting full optimization.")
        
        # --- Robust benchmark data loading with fallback ---
        benchmark_data = None
        try:
            logger.info(f"Fetching benchmark data for {atlas_config.BENCHMARK_SYMBOL}...")
            benchmark_loader = DataLoader([atlas_config.BENCHMARK_SYMBOL])
            benchmark_data = benchmark_loader.get_data().get(atlas_config.BENCHMARK_SYMBOL)
        except Exception as e:
            logger.error(f"Error while loading benchmark data: {e}")

        if benchmark_data is None or benchmark_data.empty:
            logger.error("Failed to load benchmark data. Alpha and Beta calculations will be skipped.")
            benchmark_data = pd.DataFrame()
        
        data_loader = DataLoader(atlas_config.SYMBOLS)
        historical_data_for_optimization = data_loader.get_data()
        
        if not historical_data_for_optimization:
            logger.error("[WORKFLOW] Halting. Data loading failed for optimization."); return

        num_workers = cpu_count()
        logger.warning(f"[WORKFLOW] Starting parallel analysis for {len(historical_data_for_optimization)} symbols using {num_workers} workers.")
        
        with Pool(num_workers) as pool:
            analysis_func_with_benchmark = partial(run_analysis_for_symbol, benchmark_data=benchmark_data)
            results_from_pool = pool.map(analysis_func_with_benchmark, historical_data_for_optimization.items())
        
        for symbol, best_params in results_from_pool:
            if best_params is not None:
                all_best_params[symbol] = best_params

        if all_best_params:
            logger.warning(f"Optimization complete. Saving best parameters to '{cache_file}'.")
            params_to_save = {s: {k: v.item() if hasattr(v, 'item') else v
                                  for k, v in p.to_dict().items() if k not in ['equity_curve', 'benchmark_data']}
                              for s, p in all_best_params.items()}
            with open(cache_file, 'w') as f:
                json.dump(params_to_save, f, indent=4)
        else:
            logger.error("[WORKFLOW] Optimization completed, but no optimal parameters were found.")

    if not all_best_params:
        logger.error("[WORKFLOW] Halting. No optimal parameters available."); return

    # --- Stage 2 & 3: Live/Simulation Engine ---
    logger.warning("[WORKFLOW] Stage 2: Configuring live engine...")
    live_config = LiveConfig()
    live_config.SYMBOLS_TO_TRADE = list(all_best_params.keys())
    
    proxy_symbol = random.choice(list(all_best_params.keys()))
    proxy_params = all_best_params[proxy_symbol]
    
    # --- This section can be improved for better parameter mapping ---
    live_config.StrategyParameters.Trend.SHORT_WINDOW = int(proxy_params.get('trend_sw', 20))
    live_config.StrategyParameters.Trend.LONG_WINDOW = int(proxy_params.get('trend_lw', 50))
    # ... (rest of your parameter settings) ...
    
    logger.info(f"Live engine configured with general parameters from proxy symbol: {proxy_symbol}")
    
    chief_investment_officer = None
    try:
        alerter = Alerter()
        risk_manager = RiskManager(live_config.RiskParameters, alerter)
        chief_investment_officer = ChiefInvestmentOfficer(live_config, risk_manager, alerter)
        
        if simulate:
            logger.warning(f"--- ACCELERATED SIMULATION MODE ENABLED ---")
            historical_data_sim = DataLoader(live_config.SYMBOLS_TO_TRADE).get_data()
            if not historical_data_sim:
                logger.error("[WORKFLOW] Halting simulation: Data loading failed."); return
            
            initial_prices = {s: df['Close'].iloc[0] for s, df in historical_data_sim.items() if not df.empty}
            broker = MockBroker(live_config.SYMBOLS_TO_TRADE, initial_prices)
            
            sim_now = datetime.now().replace(hour=9, minute=15, second=0)
            while sim_now.weekday() > 4: sim_now += timedelta(days=1)
            
            logger.info(f"Starting simulation clock at: {sim_now.strftime('%A, %Y-%m-%d %H:%M:%S')}")
            for _ in range(360):
                ticks = broker.get_live_ticks()
                if ticks:
                    chief_investment_officer.on_market_data(ticks, sim_now)
                sim_now += timedelta(minutes=1)
                time.sleep(0.001)
            logger.warning("--- Accelerated simulation complete. ---")

        else: # Live trading mode
            logger.warning(f"--- LIVE TRADING ENGINE INITIALIZED ---")
            broker = YFinanceBroker(live_config.SYMBOLS_TO_TRADE)
            while is_market_open():
                try:
                    ticks = broker.get_live_ticks()
                    if ticks:
                        chief_investment_officer.on_market_data(ticks, datetime.now(pytz.timezone('Asia/Kolkata')))
                    chief_investment_officer.log_status()
                except Exception as e:
                    logger.error(f"An error occurred in the main trading loop: {e}")
                time.sleep(60)

    except KeyboardInterrupt:
        logger.warning("--- Shutdown signal received from user. ---")
    finally:
        if chief_investment_officer:
            logger.warning("--- Generating Final Performance Report ---")
            chief_investment_officer.log_status()
        logger.warning("--- WORKFLOW SHUTDOWN COMPLETE ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified Quantitative Trading Workflow Engine.")
    parser.add_argument('--simulate', action='store_true', help="Run in accelerated simulation mode.")
    parser.add_argument('--force-reoptimize', action='store_true', help="Ignore parameter cache and force re-optimization.")
    # --- ADDED: New argument to launch the dashboard ---
    parser.add_argument('--dashboard', action='store_true', help="Launch the live dashboard GUI automatically.")
    args = parser.parse_args()

    # --- ADDED: Logic to start the dashboard ---
    dashboard_process = None
    if args.dashboard:
        try:
            # Launch live_dashboard.py as a separate, non-blocking process
            dashboard_process = subprocess.Popen(['python', 'live_dashboard.py'])
            logging.warning("Live dashboard launched in a separate process.")
        except FileNotFoundError:
            logging.error("Could not launch dashboard. Make sure 'live_dashboard.py' is in the root directory.")
    
    try:
        run_automated_workflow(simulate=args.simulate, force_reoptimize=args.force_reoptimize)
    finally:
        # If the main script ends, you might want to close the dashboard automatically.
        # This is optional and commented out by default.
        # if dashboard_process:
        #     dashboard_process.terminate()
        #     logging.warning("Dashboard process terminated.")
        pass
