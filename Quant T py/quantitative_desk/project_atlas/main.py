# project_atlas/1_main.py
"""
Project Atlas: Main Execution
=============================
This script serves as the primary entry point for the Orion Backtesting Framework.
It orchestrates the high-level workflow:
1. Loads firm configuration.
2. Fetches market data.
3. Runs the parameter optimization process.
4. Generates a final performance and risk analysis report.
"""

import logging
from core_config import FirmConfig
from infrastructure import DataLoader
from analysis import ParameterOptimizer, ReportGenerator

def main() -> None:
    """Main workflow orchestrator."""
    logging.info("Project Atlas: Orion Backtesting Framework - Initializing...")
    
    try:
        # 1. Load Configuration
        config = FirmConfig()
        
        # 2. Load Data
        loader = DataLoader(config.SYMBOL)
        data = loader.get_data()
        
        if data is not None and not data.empty:
            # 3. Run Optimization
            optimizer = ParameterOptimizer(config, data)
            results = optimizer.run()
            
            # 4. Generate Report
            reporter = ReportGenerator(config.SYMBOL, results, config.FIRM_CAPITAL)
            reporter.generate()
            logging.info("Project Atlas: Run Completed Successfully.")
        else:
            logging.error("Could not run simulation due to data loading failure.")
            
    except Exception as e:
        logging.critical(f"A fatal error occurred in the main execution block: {e}", exc_info=True)

if __name__ == "__main__":
    main()
