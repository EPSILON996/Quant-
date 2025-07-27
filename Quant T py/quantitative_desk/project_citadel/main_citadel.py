# project_citadel/1_main_citadel.py
"""
Project Citadel: Standalone Live Engine (v3.0 - Definitive)
=============================================================
This is the dedicated entry point for running the Project Citadel live
simulation independently. It uses the pre-set parameters from its config
file and does not run the Project Atlas research phase.
"""
import logging
import time
from datetime import datetime, timedelta, time as dt_time

# --- Uses relative imports to work from within the citadel folder ---
from .core_config_citadel import LiveConfig
from .components_citadel import Alerter, RiskManager, ChiefInvestmentOfficer, MockBroker

def setup_logging() -> None:
    """Configures a professional logger without an automatic timestamp."""
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.INFO,
            format='%(levelname)-8s - [%(module)s] - %(message)s',
            handlers=[
                logging.FileHandler("citadel_runtime.log", encoding='utf-8', mode='w'),
                logging.StreamHandler()
            ]
        )

def is_market_open(now: datetime) -> bool:
    """Checks if the GIVEN time is within Indian market hours."""
    market_open = dt_time(9, 15)
    market_close = dt_time(15, 30)
    return now.weekday() < 5 and market_open <= now.time() <= market_close

def main():
    """The main execution loop for the standalone Citadel engine."""
    setup_logging()
    live_config = LiveConfig()
    
    logging.info("--- Project Citadel Standalone Engine Initializing ---")
    logging.info(f"Using pre-configured parameters for {live_config.SYMBOL}")

    cio = None
    try:
        alerter = Alerter()
        risk_manager = RiskManager(live_config.RiskParameters, alerter)
        cio = ChiefInvestmentOfficer(live_config, risk_manager, alerter)
        # In a real system, you'd fetch the last price. Here we use a realistic default.
        broker = MockBroker(initial_price=3800.0) 
        
        simulated_now = datetime.now().replace(hour=10, minute=0, second=0)
        while simulated_now.weekday() != 2: # Find the next Wednesday for testing
            simulated_now += timedelta(days=1)
        logging.warning(f"--- TIME SIMULATION ENABLED --- Starting clock at: {simulated_now.strftime('%A, %Y-%m-%d %H:%M:%S')}")
        
        last_status_log_time = 0
        start_day = simulated_now.date()
        
        while True:
            days_passed = (simulated_now.date() - start_day).days
            if days_passed >= live_config.MAX_SIMULATION_DAYS:
                logging.warning(f"--- GRACEFUL SHUTDOWN: Reached max simulation duration of {live_config.MAX_SIMULATION_DAYS} days. ---")
                break

            if is_market_open(simulated_now):
                current_tick = broker.get_live_tick()
                cio.on_market_data(current_tick, simulated_now)
                if time.time() - last_status_log_time > 15:
                    cio.log_status(simulated_now)
                    last_status_log_time = time.time()
                time.sleep(0.1)
            else:
                if time.time() - last_status_log_time > 30:
                    log_time = simulated_now.strftime('%Y-%m-%d %H:%M:%S')
                    logging.info(f"{log_time} - Market is currently closed. Standing by...")
                    last_status_log_time = time.time()
                time.sleep(1)
            
            simulated_now += timedelta(minutes=1)

    except KeyboardInterrupt:
        logging.warning("--- Shutdown signal received from user. ---")
    finally:
        if cio:
            final_equity = cio.get_total_equity()
            pnl = final_equity - live_config.INITIAL_CAPITAL
            pnl_percent = (pnl / live_config.INITIAL_CAPITAL) * 100
            print("\n" + "="*60); print("--- FINAL LIVE SESSION PERFORMANCE REPORT ---"); print("="*60)
            print(f"  Start Equity:    {live_config.INITIAL_CAPITAL:,.2f} INR")
            print(f"  End Equity:      {final_equity:,.2f} INR")
            print(f"  Session P&L:     {pnl:,.2f} INR ({pnl_percent:.2f}%)")
            print(f"  Trades Executed: {cio.trade_count}")
            print("="*60)
        
        logging.info("--- Project Citadel Shutdown Complete ---")

if __name__ == "__main__":
    main()
