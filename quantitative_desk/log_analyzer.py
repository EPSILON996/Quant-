import pandas as pd
import re
import os
from collections import defaultdict

def parse_trade_log(log_file_path='live_trades.log'):
    """
    Parses the live_trades.log file into a structured DataFrame.
    """
    if not os.path.exists(log_file_path):
        print(f"Error: Log file not found at '{log_file_path}'")
        return None

    # --- DEFINITIVELY FIXED: This pattern now correctly matches your log format ---
    # The previous error was a mistake on my part: I was looking for "Qty of",
    # which is NOT in the logs. This new pattern removes that incorrect assumption.
    log_pattern = re.compile(
        r"\[(?P<time>.*?)\]\s+\[(?P<strategy>\w+)\]\s+EXEC:\s+"
        r"(?P<action>BUY|SELL)\s+(?P<qty>[\d,]+)\s+(?P<symbol>[\w\.-]+)\s+@?\s*(?P<price>[\d,\.]+)"
    )

    parsed_trades = []
    with open(log_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            # We use search() because the trade info might be followed by other data
            match = log_pattern.search(line)
            if match:
                trade_data = match.groupdict()
                # Remove commas from numbers before conversion
                trade_data['qty'] = trade_data['qty'].replace(',', '')
                trade_data['price'] = trade_data['price'].replace(',', '')
                parsed_trades.append(trade_data)
    
    if not parsed_trades:
        print("Error: No trades could be parsed. This is unexpected. Please check the log file content.")
        return None

    df = pd.DataFrame(parsed_trades)
    df['qty'] = pd.to_numeric(df['qty'])
    df['price'] = pd.to_numeric(df['price'])
    
    print(f"Successfully parsed {len(df)} trade executions from the log.")
    return df

def calculate_realized_pnl(trades_df):
    """
    Calculates realized P&L from a list of trades using FIFO logic.
    """
    open_positions = defaultdict(lambda: {'qty': 0, 'cost': 0.0})
    realized_trades = []

    for _, trade in trades_df.iterrows():
        symbol = trade['symbol']
        
        if trade['action'] == 'BUY':
            pos = open_positions[symbol]
            pos['cost'] += trade['qty'] * trade['price']
            pos['qty'] += trade['qty']
        
        elif trade['action'] == 'SELL':
            if open_positions[symbol]['qty'] > 0:
                pos = open_positions[symbol]
                avg_cost = pos['cost'] / pos['qty']
                
                sell_qty = min(trade['qty'], pos['qty'])
                pnl = (trade['price'] - avg_cost) * sell_qty
                
                realized_trades.append({
                    'strategy': trade['strategy'], 
                    'symbol': symbol, 
                    'pnl': pnl,
                    'qty_closed': sell_qty
                })
                
                pos['qty'] -= sell_qty
                pos['cost'] -= sell_qty * avg_cost

    if not realized_trades:
        print("\nNo trades were closed, so no realized P&L could be calculated.")
        return pd.DataFrame()
        
    return pd.DataFrame(realized_trades)

def analyze_performance(pnl_df):
    """
    Generates a performance summary report from the P&L DataFrame.
    """
    if pnl_df.empty:
        return "No performance data to analyze."

    total_pnl = pnl_df['pnl'].sum()
    total_trades = len(pnl_df)
    winning_trades = pnl_df[pnl_df['pnl'] > 0]
    losing_trades = pnl_df[pnl_df['pnl'] <= 0]
    
    win_rate = (len(winning_trades) / total_trades) * 100 if total_trades > 0 else 0
    avg_win = winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0
    avg_loss = losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0

    summary = f"""
==================================================
        OVERALL PERFORMANCE (REALIZED P&L)
==================================================
Total Net Profit/Loss: ₹{total_pnl:,.2f}
Total Closed Trades:   {total_trades}
Win Rate:              {win_rate:.2f}%
Average Winning Trade: ₹{avg_win:,.2f}
Average Losing Trade:  ₹{avg_loss:,.2f}
--------------------------------------------------

"""
    strategy_summary = pnl_df.groupby('strategy')['pnl'].agg(['sum', 'count']).reset_index()
    strategy_summary.columns = ['Strategy', 'Net P&L', 'Total Trades']
    
    summary += "PER-STRATEGY PERFORMANCE:\n"
    summary += strategy_summary.to_string(index=False)
    summary += "\n=================================================="

    return summary

if __name__ == "__main__":
    trades_df = parse_trade_log()
    
    if trades_df is not None:
        realized_pnl_df = calculate_realized_pnl(trades_df)
        
        performance_report = analyze_performance(realized_pnl_df)
        print(performance_report)

        if not realized_pnl_df.empty:
            output_filename = 'realized_pnl_analysis.csv'
            realized_pnl_df.to_csv(output_filename, index=False)
            print(f"\nDetailed P&L for each closed trade saved to '{output_filename}'")
