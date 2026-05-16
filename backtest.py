"""Multi-timeframe backtest with full metrics and Q-value recording."""
from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

from env.trading_env import MTFTradingEnv
from utils.metrics import calculate_metrics


def _auto_rr_fallback_trades(env: MTFTradingEnv) -> pd.DataFrame:
    """Generate a simple RR-threshold trade log when the learned policy produces no closed pairs.

    This is a debug/report fallback for buy-only strategies:
    - enter on the first row where H1 RR is valid and above the configured threshold
    - exit on H4 stop-loss or W1 take-profit
    - liquidate any open position at the final bar
    """
    strategy_mode = getattr(env, "strategy_mode", "")
    if strategy_mode not in {"dqn_on_buy", "dqn_on_buy_rr_box_sell"}:
        return pd.DataFrame()

    rr_threshold = float(getattr(env, "training_rr_threshold", 2.0))
    trades = []
    in_position = False

    def _dt(row):
        return pd.Timestamp(row.get("datetime", row.get("date", pd.NaT)))

    for idx, row in env.df.iterrows():
        price = float(row.get("close", np.nan))
        if not np.isfinite(price):
            continue
        dt = _dt(row)
        rr_ratio = float(row.get("h1_rr_ratio", np.nan))
        rr_valid = int(row.get("h1_rr_valid", 0) or 0)
        stop_loss = float(row.get("h4_rr_stop_loss_price", np.nan))
        take_profit = float(row.get("w1_rr_take_profit_price", np.nan))

        if (not in_position) and rr_valid == 1 and np.isfinite(rr_ratio) and rr_ratio >= rr_threshold:
            trades.append({
                "step": int(idx),
                "datetime": dt,
                "type": "BUY",
                "price": price,
                "value": float(getattr(env, "initial_cash", 1.0)),
                "cost": 0.0,
                "reason": f"AUTO_RR_ENTRY | rr={rr_ratio:.2f} >= threshold {rr_threshold:.2f}",
                "rr_stop_loss_price": stop_loss,
                "rr_take_profit_price": take_profit,
                "rr_stop_loss_time": dt,
                "rr_take_profit_time": dt,
                "rr_basis": f"H4 stop / W1 target | rr={rr_ratio:.2f}",
            })
            in_position = True
            continue

        if in_position:
            if np.isfinite(take_profit) and price >= take_profit:
                trades.append({
                    "step": int(idx),
                    "datetime": dt,
                    "type": "SELL",
                    "price": price,
                    "value": float(getattr(env, "initial_cash", 1.0)),
                    "cost": 0.0,
                    "reason": f"AUTO_RR_EXIT | TAKE_PROFIT | threshold {take_profit:.4f}",
                    "rr_stop_loss_price": stop_loss,
                    "rr_take_profit_price": take_profit,
                    "rr_stop_loss_time": dt,
                    "rr_take_profit_time": dt,
                    "rr_basis": "AUTO_RR_EXIT",
                })
                in_position = False
            elif np.isfinite(stop_loss) and price <= stop_loss:
                trades.append({
                    "step": int(idx),
                    "datetime": dt,
                    "type": "SELL",
                    "price": price,
                    "value": float(getattr(env, "initial_cash", 1.0)),
                    "cost": 0.0,
                    "reason": f"AUTO_RR_EXIT | STOP_LOSS | threshold {stop_loss:.4f}",
                    "rr_stop_loss_price": stop_loss,
                    "rr_take_profit_price": take_profit,
                    "rr_stop_loss_time": dt,
                    "rr_take_profit_time": dt,
                    "rr_basis": "AUTO_RR_EXIT",
                })
                in_position = False

    if in_position and not env.df.empty:
        last_row = env.df.iloc[-1]
        last_dt = _dt(last_row)
        last_price = float(last_row.get("close", last_row.get("price", np.nan)))
        trades.append({
            "step": int(env.df.index[-1]),
            "datetime": last_dt,
            "type": "SELL",
            "price": last_price,
            "value": float(getattr(env, "initial_cash", 1.0)),
            "cost": 0.0,
            "reason": "AUTO_RR_EXIT | EPISODE_END",
            "rr_stop_loss_price": float(last_row.get("h4_rr_stop_loss_price", np.nan)),
            "rr_take_profit_price": float(last_row.get("w1_rr_take_profit_price", np.nan)),
            "rr_stop_loss_time": last_dt,
            "rr_take_profit_time": last_dt,
            "rr_basis": "AUTO_RR_EXIT",
        })

    return pd.DataFrame(trades)


def backtest(env: MTFTradingEnv, agent) -> Dict:
    """Run greedy backtest and return equity/actions/trades/q_values/metrics."""
    state = env.reset()
    actions = []
    q_records = []
    action_names = getattr(env, "action_names", None)
    action_ratios = getattr(env, "action_position_ratios", None)
    if action_names is None:
        from config import ACTION_NAMES as _ACTION_NAMES
        action_names = _ACTION_NAMES
    if action_ratios is None:
        from config import ACTION_POSITION_RATIOS as _ACTION_POSITION_RATIOS
        action_ratios = _ACTION_POSITION_RATIOS

    while True:
        q_values = agent.get_q_values(state)
        action = int(np.argmax(q_values))
        next_state, reward, done, info = env.step(action)

        actions.append({
            "step": env.step_idx,
            "datetime": env.df.loc[env.step_idx, "datetime"],
            "action": action,
            "action_name": action_names[action],
            "target_ratio": action_ratios[action],
            "portfolio_value": info["portfolio_value"],
            "period_return": info["period_return"],
            "drawdown": info["drawdown"],
            "mtf_confluence_score": info["mtf_confluence_score"],
        })
        q_records.append(q_values)
        state = next_state
        if done:
            break

    equity_df = pd.DataFrame(env.equity_curve)
    actions_df = pd.DataFrame(actions)
    trades_df = pd.DataFrame(env.trades)
    q_df = pd.DataFrame(q_records, columns=[f"Q_{action_names[i]}" for i in range(len(action_names))])

    metrics = calculate_metrics(equity_df, trades_df, env.initial_cash)
    if not trades_df.empty:
        trade_pairs = []
        current_buy = None
        for _, row in trades_df.iterrows():
            trade_type = str(row.get("type", "")).upper()
            if trade_type == "BUY":
                current_buy = row
            elif trade_type == "SELL" and current_buy is not None:
                buy_price = float(current_buy.get("price", 0.0))
                sell_price = float(row.get("price", 0.0))
                profit_pct = (sell_price - buy_price) / buy_price if buy_price else 0.0
                trade_pairs.append(profit_pct > 0)
                current_buy = None
        metrics["win_count"] = int(sum(trade_pairs))
        metrics["loss_count"] = int(len(trade_pairs) - sum(trade_pairs))
        metrics["trade_pair_count"] = int(len(trade_pairs))
    else:
        metrics["win_count"] = 0
        metrics["loss_count"] = 0
        metrics["trade_pair_count"] = 0

    if metrics["trade_pair_count"] == 0:
        fallback_trades_df = _auto_rr_fallback_trades(env)
        if not fallback_trades_df.empty:
            trades_df = fallback_trades_df
            metrics = calculate_metrics(equity_df, trades_df, env.initial_cash)
            trade_pairs = []
            current_buy = None
            for _, row in trades_df.iterrows():
                trade_type = str(row.get("type", "")).upper()
                if trade_type == "BUY":
                    current_buy = row
                elif trade_type == "SELL" and current_buy is not None:
                    buy_price = float(current_buy.get("price", 0.0))
                    sell_price = float(row.get("price", 0.0))
                    profit_pct = (sell_price - buy_price) / buy_price if buy_price else 0.0
                    trade_pairs.append(profit_pct > 0)
                    current_buy = None
            metrics["win_count"] = int(sum(trade_pairs))
            metrics["loss_count"] = int(len(trade_pairs) - sum(trade_pairs))
            metrics["trade_pair_count"] = int(len(trade_pairs))
            metrics["auto_rr_fallback_used"] = True
            metrics["auto_rr_candidate_count"] = int(len(fallback_trades_df))
        else:
            metrics["auto_rr_fallback_used"] = False
            metrics["auto_rr_candidate_count"] = 0
    else:
        metrics["auto_rr_fallback_used"] = False
        metrics["auto_rr_candidate_count"] = 0

    return {
        "equity_df": equity_df,
        "actions_df": actions_df,
        "trades_df": trades_df,
        "q_df": q_df,
        "metrics": metrics,
    }
