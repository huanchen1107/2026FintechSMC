import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class TradePair:
    pair_id: int
    buy_time: pd.Timestamp
    sell_time: pd.Timestamp
    buy_price: float
    sell_price: float
    profit_pct: float
    buy_reason: str
    sell_reason: str
    pnl_value: float

def group_trades_into_pairs(trades_df: pd.DataFrame) -> List[TradePair]:
    """Groups a sequence of individual BUY/SELL actions into matched pairs."""
    if trades_df is None or trades_df.empty:
        return []
    
    pairs = []
    current_buy = None
    pair_id = 1
    
    for _, row in trades_df.iterrows():
        if row['type'] == 'BUY':
            # If we already have a buy, we treat it as an average up or ignore for pairing
            if current_buy is None:
                current_buy = row
        elif row['type'] == 'SELL':
            if current_buy is not None:
                # We have a matched pair
                buy_p = current_buy['price']
                sell_p = row['price']
                profit_pct = (sell_p - buy_p) / buy_p
                pnl = row['value'] - current_buy['value']
                
                pairs.append(TradePair(
                    pair_id=pair_id,
                    buy_time=pd.to_datetime(current_buy['datetime']),
                    sell_time=pd.to_datetime(row['datetime']),
                    buy_price=buy_p,
                    sell_price=sell_p,
                    profit_pct=profit_pct,
                    buy_reason="DQN Confidence (BUY Signal)", # Placeholder for now
                    sell_reason="DQN Confidence (SELL Signal)", # Placeholder for now
                    pnl_value=pnl
                ))
                pair_id += 1
                current_buy = None
                
    return pairs

def pairs_to_dataframe(pairs: List[TradePair]) -> pd.DataFrame:
    if not pairs:
        return pd.DataFrame()
    
    data = []
    for p in pairs:
        data.append({
            "ID": p.pair_id,
            "Buy Time": p.buy_time.strftime('%m-%d %H:%M'),
            "Profit %": f"{p.profit_pct*100:+.2f}%",
            "PnL": f"{p.pnl_value:,.0f}",
            "Summary": f"{p.buy_reason} -> {p.sell_reason}",
            "_raw_buy_time": p.buy_time,
            "_raw_sell_time": p.sell_time,
            "_profit_raw": p.profit_pct
        })
    return pd.DataFrame(data)
