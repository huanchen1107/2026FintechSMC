"""Multi-timeframe trading environment with target position rebalancing (V2)."""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from config import (
    ACTION_POSITION_RATIOS,
    ACTION_NAMES,
    ACTION_POSITION_RATIOS_DQN_ON_BUY,
    ACTION_NAMES_DQN_ON_BUY,
)
from utils.data_utils_v2 import ensure_datetime_index, reset_datetime_index


class MTFTradingEnvV2:
    def __init__(
        self,
        df: pd.DataFrame,
        feature_cols: List[str],
        cfg=None,
        initial_cash: float = 100000.0,
        transaction_cost_rate: float = 0.001425,
        tax_rate: float = 0.003,
        reward_scale: float = 100.0,
        drawdown_penalty: float = 0.10,
        trade_penalty: float = 0.001,
        mtf_bonus_weight: float = 0.003,
        higher_tf_conflict_penalty: float = 0.002,
        rr_progress_weight: float = 0.25,
        rr_terminal_bonus: float = 1.5,
    ):
        df = ensure_datetime_index(df)
        self.df = reset_datetime_index(df)
        self.feature_cols = feature_cols
        self.initial_cash = initial_cash
        self.transaction_cost_rate = transaction_cost_rate
        self.tax_rate = tax_rate
        self.reward_scale = reward_scale
        self.drawdown_penalty = drawdown_penalty
        self.trade_penalty = trade_penalty
        self.mtf_bonus_weight = mtf_bonus_weight
        self.higher_tf_conflict_penalty = higher_tf_conflict_penalty
        self.rr_progress_weight = rr_progress_weight
        self.rr_terminal_bonus = rr_terminal_bonus
        self.state_lookback = int(getattr(cfg, "state_lookback", 20) if cfg is not None else 20)
        self.training_rr_threshold = float(getattr(cfg, "training_rr_threshold", 2.0) if cfg is not None else 2.0)
        self.strategy_mode = getattr(cfg, "strategy_mode", "dqn_position") if cfg is not None else "dqn_position"
        if self.strategy_mode in {"dqn_on_buy", "dqn_on_buy_rr_box_sell"}:
            self.action_position_ratios = ACTION_POSITION_RATIOS_DQN_ON_BUY
            self.action_names = ACTION_NAMES_DQN_ON_BUY
        else:
            self.action_position_ratios = ACTION_POSITION_RATIOS
            self.action_names = ACTION_NAMES
        self.action_size = len(self.action_position_ratios)
        self.reset()

    def reset(self):
        self.step_idx = 0
        self.cash = self.initial_cash
        self.shares = 0.0
        self.portfolio_value = self.initial_cash
        self.peak_value = self.initial_cash
        self.done = False
        self.trades = []
        self.equity_curve = []
        return self._get_state()

    def _current_price(self) -> float:
        return float(self.df.loc[self.step_idx, "close"])

    def _get_state(self) -> np.ndarray:
        start_idx = max(0, self.step_idx - self.state_lookback + 1)
        window = self.df.loc[start_idx:self.step_idx].copy()
        pd_valid_cols = [c for c in ["w1_pd_valid", "d1_pd_valid", "h4_pd_valid", "h1_pd_valid"] if c in window.columns]
        if pd_valid_cols:
            valid_mask = (window[pd_valid_cols].fillna(0).astype(int) > 0).all(axis=1)
            valid_window = window.loc[valid_mask]
            if not valid_window.empty:
                window = valid_window
        history = window[self.feature_cols].values.astype(np.float32)
        if history.shape[0] < self.state_lookback:
            pad = np.repeat(history[:1], self.state_lookback - history.shape[0], axis=0) if history.shape[0] > 0 else np.zeros((self.state_lookback, len(self.feature_cols)), dtype=np.float32)
            history = np.vstack([pad, history]) if history.shape[0] > 0 else pad
        history_flat = history.reshape(-1)

        price = self._current_price()
        current_value = self.cash + self.shares * price
        cash_ratio = self.cash / max(current_value, 1e-8)
        position_ratio = (self.shares * price) / max(current_value, 1e-8)
        unrealized_pnl_ratio = current_value / max(self.initial_cash, 1e-8) - 1.0
        rr_features = self._current_rr_features(price)
        portfolio_features = np.array([cash_ratio, position_ratio, unrealized_pnl_ratio, *rr_features], dtype=np.float32)
        return np.concatenate([history_flat, portfolio_features])

    def _current_rr_features(self, price: float) -> np.ndarray:
        row = self.df.loc[self.step_idx]
        stop_loss = float(row.get("h4_rr_stop_loss_price", np.nan))
        take_profit = float(row.get("w1_rr_take_profit_price", np.nan))
        if pd.isna(stop_loss) or pd.isna(take_profit) or price <= 0:
            return np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        risk_pct = max((price - stop_loss) / price, 0.0)
        reward_pct = max((take_profit - price) / price, 0.0)
        rr_ratio = reward_pct / max(risk_pct, 1e-8) if risk_pct > 0 else 0.0
        rr_valid = 1.0 if (take_profit > price and stop_loss < price) else 0.0
        return np.array([risk_pct, reward_pct, rr_ratio, rr_valid], dtype=np.float32)

    def _rr_progress_score(self, price: float) -> float:
        row = self.df.loc[self.step_idx]
        stop_loss = float(row.get("h4_rr_stop_loss_price", np.nan))
        take_profit = float(row.get("w1_rr_take_profit_price", np.nan))
        if pd.isna(stop_loss) or pd.isna(take_profit) or price <= 0 or take_profit <= stop_loss:
            return 0.0
        denom = max(take_profit - stop_loss, 1e-8)
        progress = (price - stop_loss) / denom
        return float(np.clip(progress, 0.0, 1.0))

    def _rebalance_to_ratio(self, target_ratio: float) -> float:
        price = self._current_price()
        portfolio_value_before = self.cash + self.shares * price
        target_position_value = portfolio_value_before * target_ratio
        current_position_value = self.shares * price
        trade_value = target_position_value - current_position_value
        cost = 0.0
        if abs(trade_value) < 1e-8:
            return 0.0

        row = self.df.loc[self.step_idx]
        reason = self._build_trade_reason(target_ratio, trade_value, row)

        if trade_value > 0:
            buy_value = min(trade_value, self.cash)
            fee = buy_value * self.transaction_cost_rate
            actual = max(buy_value - fee, 0)
            shares_bought = actual / price
            buy_stop_loss = float(row.get("h4_rr_stop_loss_price", np.nan))
            buy_take_profit = float(row.get("w1_rr_take_profit_price", np.nan))
            self.shares += shares_bought
            self.cash -= buy_value
            cost += fee
            self.trades.append({
                "step": self.step_idx,
                "datetime": self.df.loc[self.step_idx, "datetime"],
                "type": "BUY", "price": price, "value": buy_value, "cost": fee,
                "reason": reason,
                "rr_stop_loss_price": buy_stop_loss,
                "rr_take_profit_price": buy_take_profit,
                "rr_stop_loss_time": self.df.loc[self.step_idx, "datetime"],
                "rr_take_profit_time": self.df.loc[self.step_idx, "datetime"],
                "rr_basis": f"H4 stop / W1 target" if pd.notna(buy_stop_loss) or pd.notna(buy_take_profit) else "",
            })
        else:
            sell_value = min(abs(trade_value), current_position_value)
            shares_sold = sell_value / price
            fee = sell_value * self.transaction_cost_rate
            tax = sell_value * self.tax_rate
            self.shares -= shares_sold
            self.cash += sell_value - fee - tax
            cost += fee + tax
            self.trades.append({
                "step": self.step_idx,
                "datetime": self.df.loc[self.step_idx, "datetime"],
                "type": "SELL", "price": price, "value": sell_value, "cost": fee + tax,
                "reason": reason,
                "rr_stop_loss_price": float(row.get("h4_rr_stop_loss_price", np.nan)),
                "rr_take_profit_price": float(row.get("w1_rr_take_profit_price", np.nan)),
                "rr_stop_loss_time": self.df.loc[self.step_idx, "datetime"],
                "rr_take_profit_time": self.df.loc[self.step_idx, "datetime"],
                "rr_basis": "AUTO_EXIT" if "AUTO_EXIT" in reason else "",
            })
        return cost

    def _auto_exit_if_needed(self) -> float:
        if self.shares <= 0:
            return 0.0
        row = self.df.loc[self.step_idx]
        price = self._current_price()
        stop_loss = float(row.get("h4_rr_stop_loss_price", np.nan))
        take_profit = float(row.get("w1_rr_take_profit_price", np.nan))
        if pd.notna(stop_loss) and price <= stop_loss:
            return self._forced_sell("STOP_LOSS", stop_loss)
        if pd.notna(take_profit) and price >= take_profit:
            return self._forced_sell("TAKE_PROFIT", take_profit)
        return 0.0

    def _forced_sell(self, trigger: str, trigger_price: float) -> float:
        price = self._current_price()
        position_value = self.shares * price
        if position_value <= 0:
            return 0.0
        fee = position_value * self.transaction_cost_rate
        tax = position_value * self.tax_rate
        self.cash += position_value - fee - tax
        self.shares = 0.0
        self.trades.append({
            "step": self.step_idx,
            "datetime": self.df.loc[self.step_idx, "datetime"],
            "type": "SELL",
            "price": price,
            "value": position_value,
            "cost": fee + tax,
            "reason": f"AUTO_EXIT | {trigger} | threshold {trigger_price:.4f}",
        })
        return fee + tax

    def _build_trade_reason(self, target_ratio: float, trade_value: float, row: pd.Series) -> str:
        action_name = self.action_names[int(np.argmin(np.abs(np.array(self.action_position_ratios) - target_ratio)))]
        confluence = float(row.get("mtf_confluence_score", 0.0))
        w1_bias = float(row.get("w1_smc_bias", 0.0))
        d1_bias = float(row.get("d1_smc_bias", 0.0))
        h4_bias = float(row.get("h4_smc_bias", 0.0))
        h1_bias = float(row.get("h1_smc_bias", 0.0))
        direction = "BUY" if trade_value > 0 else "SELL"
        return (
            f"{direction} | {action_name} | "
            f"MTF confluence {confluence:.2f} | "
            f"Bias W1/D1/H4/H1 = {w1_bias:.0f}/{d1_bias:.0f}/{h4_bias:.0f}/{h1_bias:.0f}"
        )

    def step(self, action: int):
        if self.done:
            raise ValueError("Episode is done. Please call reset().")

        price_before = self._current_price()
        value_before = self.cash + self.shares * price_before
        target_ratio = self.action_position_ratios[action]
        cost = self._rebalance_to_ratio(target_ratio)
        if self.strategy_mode in {"dqn_on_buy", "dqn_on_buy_rr_box_sell"}:
            cost += self._auto_exit_if_needed()

        self.step_idx += 1
        if self.step_idx >= len(self.df) - 1:
            self.done = True

        price_after = self._current_price()
        if self.done and self.shares > 0:
            cost += self._forced_sell("EPISODE_END", price_after)
            price_after = self._current_price()
        value_after = self.cash + self.shares * price_after
        self.portfolio_value = value_after
        self.peak_value = max(self.peak_value, value_after)

        period_return = value_after / max(value_before, 1e-8) - 1.0
        drawdown = (self.peak_value - value_after) / max(self.peak_value, 1e-8)

        row = self.df.loc[self.step_idx]
        rr_progress = self._rr_progress_score(price_after)
        rr_ratio = float(row.get("h1_rr_ratio", np.nan))
        rr_valid = int(row.get("h1_rr_valid", 0)) if "h1_rr_valid" in row else int(not pd.isna(rr_ratio) and rr_ratio >= self.training_rr_threshold)
        mtf_confluence = float(row["mtf_confluence_score"])
        w1_bias = float(row["w1_smc_bias"])
        d1_bias = float(row["d1_smc_bias"])
        mtf_conflict = int(row["mtf_conflict"])
        higher_tf_bearish = int(row["higher_tf_bearish"])
        higher_tf_bullish = int(row["higher_tf_bullish"])
        position_after = (self.shares * price_after) / max(value_after, 1e-8)

        mtf_alignment = np.tanh(mtf_confluence) * (position_after - 0.5)

        conflict_penalty = 0.0
        if higher_tf_bearish == 1 and position_after > 0.5:
            conflict_penalty += self.higher_tf_conflict_penalty * 1.5
        if w1_bias < 0 and position_after > 0.75:
            conflict_penalty += self.higher_tf_conflict_penalty
        if d1_bias < 0 and position_after > 0.75:
            conflict_penalty += self.higher_tf_conflict_penalty
        if higher_tf_bullish == 1 and position_after < 0.25:
            conflict_penalty += self.higher_tf_conflict_penalty * 0.5
        if mtf_conflict == 1 and position_after > 0.75:
            conflict_penalty += self.higher_tf_conflict_penalty

        reward = (
            period_return * self.reward_scale
            - self.drawdown_penalty * drawdown
            - self.trade_penalty * (1 if cost > 0 else 0)
            + self.mtf_bonus_weight * mtf_alignment
            + (self.rr_progress_weight * rr_progress if self.strategy_mode in {"dqn_on_buy", "dqn_on_buy_rr_box_sell"} else 0.0)
            - conflict_penalty
        )

        if self.strategy_mode in {"dqn_on_buy", "dqn_on_buy_rr_box_sell"} and self.shares <= 0:
            if price_after >= float(row.get("w1_rr_take_profit_price", np.nan)):
                reward += self.rr_terminal_bonus
            elif price_after <= float(row.get("h4_rr_stop_loss_price", np.nan)):
                reward -= self.rr_terminal_bonus

        self.equity_curve.append({
            "step": self.step_idx,
            "datetime": row["datetime"],
            "portfolio_value": value_after,
            "cash": self.cash,
            "shares": self.shares,
            "position_ratio": position_after,
            "drawdown": drawdown,
            "mtf_confluence_score": mtf_confluence,
            "w1_smc_bias": w1_bias,
            "d1_smc_bias": d1_bias,
            "h4_smc_bias": float(row["h4_smc_bias"]),
            "h1_smc_bias": float(row["h1_smc_bias"]),
            "higher_tf_bullish": higher_tf_bullish,
            "higher_tf_bearish": higher_tf_bearish,
        })

        next_state = self._get_state()
        info = {
            "portfolio_value": value_after,
            "period_return": period_return,
            "drawdown": drawdown,
            "cost": cost,
            "target_ratio": target_ratio,
            "position_ratio": position_after,
            "mtf_confluence_score": mtf_confluence,
            "rr_progress": rr_progress,
            "rr_ratio": rr_ratio,
            "rr_valid": rr_valid,
        }
        return next_state, reward, self.done, info


def make_env_v2(df: pd.DataFrame, cfg) -> MTFTradingEnvV2:
    from utils.data_utils_v2 import FEATURE_COLUMNS
    return MTFTradingEnvV2(
        df=df,
        feature_cols=FEATURE_COLUMNS,
        cfg=cfg,
        initial_cash=cfg.initial_cash,
        transaction_cost_rate=cfg.transaction_cost_rate,
        tax_rate=cfg.tax_rate,
        reward_scale=cfg.reward_scale,
        drawdown_penalty=cfg.drawdown_penalty,
        trade_penalty=cfg.trade_penalty,
        mtf_bonus_weight=cfg.mtf_bonus_weight,
        higher_tf_conflict_penalty=cfg.higher_tf_conflict_penalty,
    )
