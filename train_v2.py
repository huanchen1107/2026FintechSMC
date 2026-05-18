"""Multi-timeframe DQN+SMC+RRR training pipeline (V2)."""
from __future__ import annotations

from typing import Dict, Optional, Callable

import numpy as np
import pandas as pd
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from agent.dqn_agent import DQNAgent
from backtest import backtest
from config import Config, ACTION_POSITION_RATIOS
from env.trading_env_v2 import MTFTradingEnvV2, make_env_v2 as make_env
from utils.model_registry import register_model
from utils.data_utils_v2 import (
    FEATURE_COLUMNS, set_seed,
    download_and_build_mtf, build_mtf_dataset,
    split_data_time_order, fit_standardizer, apply_standardizer,
    build_pd_arrays_table,
)


def _strategy_tag(strategy_mode: str) -> str:
    # Prefer an explicit display/saved-model tag when provided.
    # The UI can attach cfg.strategy_label_tag without changing the underlying mode key.
    # This keeps old labels/tags stable while allowing new labels to coexist.
    #
    # Note: the function is kept for backward compatibility with older call sites.
    if strategy_mode == "dqn_on_buy_rr_box_sell":
        return "dqn-on-buy-rr-box-sell"
    if strategy_mode == "dqn_on_buy":
        return "dqn-on-buy"
    return "dqn-position"


def run_episode(env: MTFTradingEnvV2, agent: DQNAgent, training: bool = True, progress_callback: Optional[Callable] = None) -> Dict:
    state = env.reset()
    total_reward = 0.0
    losses = []

    while True:
        action = agent.select_action(state, training=training)
        next_state, reward, done, info = env.step(action)
        total_reward += reward

        if training:
            rr_threshold = float(getattr(env, "training_rr_threshold", 2.0))
            rr_ratio = float(info.get("rr_ratio", 0.0) or 0.0)
            rr_valid = bool(int(info.get("rr_valid", 0) or 0))
            if rr_valid and rr_ratio >= rr_threshold:
                agent.replay_buffer.push(state, action, reward, next_state, done)
                if progress_callback:
                    progress_callback(
                        f"Replay Buffer +1 | size={len(agent.replay_buffer)} | rr={rr_ratio:.2f} | threshold={rr_threshold:.2f}"
                    )
            loss = agent.update()
            if loss is not None:
                losses.append(loss)

        state = next_state
        if done:
            break

    return {
        "total_reward": total_reward,
        "final_value": env.portfolio_value,
        "total_return": env.portfolio_value / env.initial_cash - 1.0,
        "avg_loss": np.mean(losses) if losses else np.nan,
        "trades": len(env.trades),
    }


def train_agent(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    cfg: Config,
    progress_callback: Optional[Callable] = None,
):
    train_env = make_env(train_df, cfg)
    val_env = make_env(val_df, cfg)

    state_dim = train_env.reset().shape[0]
    action_dim = train_env.action_size
    agent = DQNAgent(state_dim, action_dim, cfg)

    logs = []
    best_val_return = -np.inf
    best_state_dict = None
    stale_epochs = 0
    early_stop_enabled = bool(getattr(cfg, "early_stop_enabled", False))
    early_stop_patience = int(getattr(cfg, "early_stop_patience", 50))
    early_stop_min_delta = float(getattr(cfg, "early_stop_min_delta", 0.001))

    for ep in range(1, cfg.episodes + 1):
        train_result = run_episode(train_env, agent, training=True, progress_callback=progress_callback)
        val_result = run_episode(val_env, agent, training=False)
        agent.decay_epsilon()

        if val_result["total_return"] > best_val_return + early_stop_min_delta:
            best_val_return = val_result["total_return"]
            best_state_dict = {k: v.detach().cpu().clone() for k, v in agent.policy_net.state_dict().items()}
            stale_epochs = 0
        else:
            stale_epochs += 1

        log = {
            "episode": ep,
            "epsilon": agent.epsilon,
            "train_return": train_result["total_return"],
            "val_return": val_result["total_return"],
            "train_reward": train_result["total_reward"],
            "val_reward": val_result["total_reward"],
            "avg_loss": train_result["avg_loss"],
            "test_loss": abs(val_result["total_return"] - train_result["total_return"]),
            "train_trades": train_result["trades"],
            "val_trades": val_result["trades"],
            "replay_buffer_size": len(agent.replay_buffer),
        }
        logs.append(log)

        log_line = (
            f"EP {ep:03d}/{cfg.episodes} | "
            f"eps={agent.epsilon:.4f} | "
            f"train_ret={train_result['total_return']:.2%} | "
            f"val_ret={val_result['total_return']:.2%} | "
            f"loss={train_result['avg_loss']:.5f} | "
            f"trades={train_result['trades']}"
        )
        print(log_line)
        if progress_callback:
            progress_callback(log_line)

        if early_stop_enabled and stale_epochs >= early_stop_patience:
            stop_line = (
                f"Early stopping triggered at EP {ep:03d}/{cfg.episodes} | "
                f"best_val_ret={best_val_return:.2%} | patience={early_stop_patience}"
            )
            print(stop_line)
            if progress_callback:
                progress_callback(stop_line)
            break

    if best_state_dict is not None:
        agent.policy_net.load_state_dict(best_state_dict)
        agent.target_net.load_state_dict(best_state_dict)

    return agent, pd.DataFrame(logs)


def run_training_pipeline_v2(
    cfg: Config,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """Full pipeline: download → build MTF → train → backtest → save (V2)."""
    set_seed(cfg.seed)
    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Download & build MTF dataset
    mtf_df, df_h1_raw, df_d1_raw = download_and_build_mtf(cfg, progress_callback)

    # 2. Split & standardize
    train_df, val_df, test_df = split_data_time_order(mtf_df, cfg)
    feature_mean, feature_std = fit_standardizer(train_df, FEATURE_COLUMNS)
    train_df = apply_standardizer(train_df, FEATURE_COLUMNS, feature_mean, feature_std)
    val_df = apply_standardizer(val_df, FEATURE_COLUMNS, feature_mean, feature_std)
    test_df = apply_standardizer(test_df, FEATURE_COLUMNS, feature_mean, feature_std)

    if progress_callback:
        progress_callback(f"Train: {len(train_df)} | Val: {len(val_df)} | Test: {len(test_df)}")

    # 3. Train
    agent, logs_df = train_agent(train_df, val_df, cfg, progress_callback)

    # 4. Backtest on test set
    test_env = make_env(test_df, cfg)
    bt = backtest(test_env, agent)
    metrics = bt["metrics"]
    pd_arrays = build_pd_arrays_table(mtf_df)
    training_summary = {
        "best_train_return": float(logs_df["train_return"].max()) if not logs_df.empty else 0.0,
        "best_val_return": float(logs_df["val_return"].max()) if not logs_df.empty else 0.0,
        "last_train_loss": float(logs_df["avg_loss"].dropna().iloc[-1]) if not logs_df.empty and logs_df["avg_loss"].notna().any() else np.nan,
        "last_test_loss": float(logs_df["test_loss"].dropna().iloc[-1]) if not logs_df.empty and "test_loss" in logs_df.columns and logs_df["test_loss"].notna().any() else np.nan,
    }
    metrics.update(training_summary)

    # 5. Save model (V2)
    strategy_mode = getattr(cfg, "strategy_mode", "dqn_position")
    strategy_tag = getattr(cfg, "strategy_label_tag", None) or _strategy_tag(strategy_mode)
    model_path = cfg.outputs_dir / f"mtf_dqn_model_v2_{strategy_tag}.pth"
    action_position_ratios = ACTION_POSITION_RATIOS if strategy_mode == "dqn_position" else [0.0, 1.0]
    agent.save(
        str(model_path),
        feature_columns=FEATURE_COLUMNS,
        feature_mean=feature_mean.to_dict(),
        feature_std=feature_std.to_dict(),
        config={k: v for k, v in cfg.__dict__.items() if not isinstance(v, type(cfg.project_dir))},
        action_position_ratios=action_position_ratios,
    )

    # 6. Save plots (V2)
    plt.figure(figsize=(10, 5))
    plt.plot(logs_df["episode"].values, logs_df["train_return"].values, label="Train Return")
    plt.plot(logs_df["episode"].values, logs_df["val_return"].values, label="Val Return")
    plt.axhline(0, linestyle="--", linewidth=1)
    plt.title("MTF DQN Training / Validation Return (V2)")
    plt.xlabel("Episode")
    plt.ylabel("Return")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(cfg.outputs_dir / "training_returns_v2.png", dpi=150)
    plt.close()

    plt.figure(figsize=(10, 5))
    plt.plot(logs_df["episode"].values, logs_df["avg_loss"].values, label="Avg Loss")
    if "test_loss" in logs_df.columns:
        plt.plot(logs_df["episode"].values, logs_df["test_loss"].values, label="Test Loss Proxy")
    plt.title("DQN Training Loss (V2)")
    plt.xlabel("Episode")
    plt.ylabel("Loss")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(cfg.outputs_dir / "training_losses_v2.png", dpi=150)
    plt.close()

    print(f"Model saved to: {model_path}")
    print(f"Artifacts saved in: {cfg.outputs_dir}")

    model_record = register_model(
        cfg.outputs_dir,
        model_path=str(model_path),
        ticker=cfg.ticker,
        sharpe=float(metrics.get("sharpe_ratio", 0.0) or 0.0),
        total_return=float(metrics.get("total_return", 0.0) or 0.0),
        max_drawdown=float(metrics.get("max_drawdown", 0.0) or 0.0),
        extra={"is_v2": True, "strategy_mode": strategy_mode, "strategy_label": strategy_tag},
    )

    return {
        "status": "success",
        "logs_df": logs_df,
        "model_path": str(model_path),
        "metrics": metrics,
        "agent": agent,
        "mtf_df": mtf_df,
        "feature_mean": feature_mean,
        "feature_std": feature_std,
        "test_backtest": bt,
        "is_v2": True,
        "model_record": model_record,
        "pd_arrays": pd_arrays,
        "training_summary": training_summary,
    }


def run_evaluation_pipeline_v2(
    cfg: Config,
    model_path: str,
    model_record: Optional[dict] = None,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """Load a saved V2 model, rebuild data, and run backtest/inference."""
    set_seed(cfg.seed)
    cfg.outputs_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
    checkpoint_action_ratios = checkpoint.get("action_position_ratios") if isinstance(checkpoint, dict) else None
    checkpoint_action_dim = len(checkpoint_action_ratios) if isinstance(checkpoint_action_ratios, (list, tuple)) else None
    if isinstance(checkpoint_action_ratios, (list, tuple)) and len(checkpoint_action_ratios) == 2:
        cfg.strategy_mode = "dqn_on_buy_rr_box_sell" if isinstance(model_record, dict) and model_record.get("strategy_mode") == "dqn_on_buy_rr_box_sell" else "dqn_on_buy"
    elif isinstance(checkpoint_action_ratios, (list, tuple)) and len(checkpoint_action_ratios) == 4:
        cfg.strategy_mode = "dqn_position"
    elif isinstance(model_record, dict) and model_record.get("strategy_mode") in {"dqn_on_buy", "dqn_on_buy_rr_box_sell"}:
        cfg.strategy_mode = str(model_record.get("strategy_mode"))
    elif isinstance(model_record, dict) and model_record.get("strategy_mode"):
        cfg.strategy_mode = str(model_record.get("strategy_mode"))
    if isinstance(model_record, dict) and model_record.get("strategy_label"):
        cfg.strategy_label_tag = str(model_record.get("strategy_label"))
    mtf_df, _, _ = download_and_build_mtf(cfg, progress_callback)
    train_df, val_df, test_df = split_data_time_order(mtf_df, cfg)
    feature_mean, feature_std = fit_standardizer(train_df, FEATURE_COLUMNS)
    train_df = apply_standardizer(train_df, FEATURE_COLUMNS, feature_mean, feature_std)
    val_df = apply_standardizer(val_df, FEATURE_COLUMNS, feature_mean, feature_std)
    test_df = apply_standardizer(test_df, FEATURE_COLUMNS, feature_mean, feature_std)
    if progress_callback:
        progress_callback(f"Loaded model evaluation: Train {len(train_df)} | Val {len(val_df)} | Test {len(test_df)}")

    test_env = make_env(test_df, cfg)
    state_dim = test_env.reset().shape[0]
    action_dim = checkpoint_action_dim or test_env.action_size
    agent = DQNAgent(state_dim, action_dim, cfg)
    checkpoint = agent.load(model_path)
    if checkpoint:
        if "feature_mean" in checkpoint and "feature_std" in checkpoint:
            feature_mean = pd.Series(checkpoint["feature_mean"])
            feature_std = pd.Series(checkpoint["feature_std"])
    bt = backtest(test_env, agent)
    metrics = bt["metrics"]
    pd_arrays = build_pd_arrays_table(mtf_df)
    return {
        "status": "success",
        "logs_df": pd.DataFrame(),
        "model_path": str(model_path),
        "metrics": metrics,
        "agent": agent,
        "mtf_df": mtf_df,
        "feature_mean": feature_mean,
        "feature_std": feature_std,
        "test_backtest": bt,
        "is_v2": True,
        "model_record": model_record,
        "pd_arrays": pd_arrays,
    }


def main() -> None:
    cfg = Config()
    result = run_training_pipeline_v2(cfg)
    metrics = result["metrics"]
    print("\n========== Test Backtest Metrics ==========")
    for k, v in metrics.items():
        if isinstance(v, float):
            if "rate" in k or "return" in k or "drawdown" in k:
                print(f"{k}: {v:.2%}")
            else:
                print(f"{k}: {v:.4f}")
        else:
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()
