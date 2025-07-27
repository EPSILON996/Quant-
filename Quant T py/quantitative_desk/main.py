# quantitative_desk/main.py (v13.0 - Definitive & Final)
"""
This definitive version uses parallel processing for fast optimization,
automatically disables plots, and is fully synchronized with all components.
"""
import logging, time, argparse
from datetime import datetime, timedelta, time as dt_time
from multiprocessing import Pool, cpu_count
from project_atlas.analysis import ParameterOptimizer, ReportGenerator
from project_atlas.infrastructure import DataLoader
from project_atlas.core_config import FirmConfig as AtlasConfig
from project_citadel.components_citadel import Alerter, RiskManager, ChiefInvestmentOfficer, YFinanceBroker, MockBroker
from project_citadel.core_config_citadel import LiveConfig

def run_analysis_for_symbol(symbol_data_tuple):
    symbol, historical_data = symbol_data_tuple
    logging.info(f"--- Starting analysis for {symbol} ---")
    atlas_config = AtlasConfig()
    optimizer = ParameterOptimizer(atlas_config, historical_data)
    results = optimizer.run()
    reporter = ReportGenerator(symbol, results)
    best_params_series = reporter.get_best_params()
    if best_params_series is not None:
        reporter.generate(show_plots=False)
        logging.info(f"--- Analysis for {symbol} complete. ---")
        return symbol, best_params_series
    else:
        logging.error(f"Optimization failed for {symbol}. Skipping.")
        return symbol, None

def setup_logging():
    log_format = '%(levelname)-8s - [%(name)s] - %(message)s'
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(level=logging.INFO, format=log_format, datefmt='%Y-%m-%d %H:%M:%S')

def is_market_open(now: datetime) -> bool:
    market_open = dt_time(9, 15); market_close = dt_time(15, 30)
    return now.weekday() < 5 and market_open <= now.time() <= market_close

def run_automated_workflow(simulate: bool):
    setup_logging()
    logger = logging.getLogger('main_workflow')
    mode = "SIMULATION" if simulate else "LIVE"
    logger.warning(f"--- UNIFIED WORKFLOW STARTED IN {mode} MODE ---")
    
    atlas_config = AtlasConfig(); loader = DataLoader(atlas_config.SYMBOLS); all_historical_data = loader.get_data()
    if not all_historical_data: logger.error("[WORKFLOW] Halting. Data loading failed."); return
    
    all_best_params = {}
    num_workers = cpu_count()
    logger.warning(f"[WORKFLOW] Starting parallel analysis for {len(all_historical_data)} symbols using {num_workers} workers.")
    
    with Pool(processes=num_workers) as pool:
        # Pass the symbol name to the data for better logging in the optimizer
        data_with_symbols = []
        for symbol, data in all_historical_data.items():
            data.attrs['symbol'] = symbol
            data_with_symbols.append((symbol, data))
        results = pool.map(run_analysis_for_symbol, data_with_symbols)

    for symbol, best_params in results:
        if best_params is not None: all_best_params[symbol] = best_params

    if not all_best_params: logger.error("[WORKFLOW] Halting. Optimization failed for all symbols."); return
    
    logger.warning("[WORKFLOW] Stage 2: Dynamically configuring live engine...")
    live_config = LiveConfig(); live_config.SYMBOLS_TO_TRADE = list(all_best_params.keys())
    first_successful_symbol = next(iter(all_best_params)); final_params = all_best_params[first_successful_symbol]
    live_config.StrategyParameters.Trend.SHORT_WINDOW = int(final_params['trend_sw'])
    live_config.StrategyParameters.Trend.LONG_WINDOW = int(final_params['trend_lw'])
    live_config.StrategyParameters.MeanReversion.WINDOW = int(final_params['mr_w'])
    live_config.StrategyParameters.MeanReversion.STD_DEV = final_params['mr_std']
    logger.info(f"Live engine configured with params from {first_successful_symbol}: Trend({final_params['trend_sw']:.0f}, {final_params['trend_lw']:.0f}), MR({final_params['mr_w']:.0f}, {final_params['mr_std']:.1f})")
    
    cio=None
    try:
        alerter=Alerter(); risk_manager=RiskManager(live_config.RiskParameters, alerter); cio=ChiefInvestmentOfficer(live_config,risk_manager,alerter)
        if simulate:
            initial_prices = {sym: df['Close'].iloc[-1] for sym,df in all_historical_data.items() if sym in live_config.SYMBOLS_TO_TRADE and not df.empty}
            broker = MockBroker(live_config.SYMBOLS_TO_TRADE, initial_prices); sim_now = datetime.now().replace(hour=10,minute=0,second=0)
            while sim_now.weekday() != 2: sim_now += timedelta(days=1)
            logger.warning(f"--- TIME SIMULATION ENABLED --- Starting clock at: {sim_now.strftime('%A, %Y-%m-%d %H:%M:%S')}")
            while is_market_open(sim_now):
                ticks = broker.get_live_ticks()
                if ticks: cio.on_market_data(ticks, sim_now)
                time.sleep(0.01); sim_now += timedelta(minutes=1)
    except KeyboardInterrupt: logger.warning("--- Shutdown signal received. ---")
    finally:
        if cio:
            final_equity=cio.get_total_equity(); pnl=final_equity-live_config.INITIAL_CAPITAL
            pnl_pct=(pnl/live_config.INITIAL_CAPITAL)*100 if live_config.INITIAL_CAPITAL > 0 else 0
            print("\n"+"="*60+f"\n--- FINAL SESSION PERFORMANCE REPORT (PORTFOLIO) ---\n"+"="*60)
            print(f"  Start Equity:    {live_config.INITIAL_CAPITAL:,.2f} INR\n  End Equity:      {final_equity:,.2f} INR")
            print(f"  Session P&L:     {pnl:,.2f} INR ({pnl_pct:.2f}%)\n  Trades Executed: {cio.trade_count}\n"+"="*60)
        logger.info("--- WORKFLOW SHUTDOWN COMPLETE ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified Quantitative Trading Workflow Engine.")
    parser.add_argument('--simulate', action='store_true', help="Run in accelerated simulation mode.")
    args = parser.parse_args()
    run_automated_workflow(simulate=args.simulate)
