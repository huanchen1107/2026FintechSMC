"""Helpers for reconstructing and persisting BUY/SELL trade pairs."""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd


@dataclass
class TradePair:
    pair_id: int
    ticker: str
    buy_trade_id: str
    sell_trade_id: str
    buy_time: pd.Timestamp
    sell_time: pd.Timestamp
    buy_price: float
    sell_price: float
    profit_pct: float
    pnl: float
    training_reward: float = 0.0
    rr_stop_loss_price: float = float("nan")
    rr_take_profit_price: float = float("nan")
    rr_stop_loss_time: pd.Timestamp = pd.Timestamp("NaT")
    rr_take_profit_time: pd.Timestamp = pd.Timestamp("NaT")
    rr_basis: str = ""
    buy_reason: str = ""
    sell_reason: str = ""
    is_correct: str = ""
    review_note: str = ""


def reconstruct_trade_pairs(trades_df: pd.DataFrame, ticker: str = "") -> List[TradePair]:
    pairs: List[TradePair] = []
    current_buy: Optional[pd.Series] = None
    pair_id = 1

    def _trade_id(row: pd.Series, fallback: int) -> str:
        for key in ("trade_id", "order_id", "id", "idx"):
            if key in row and pd.notna(row.get(key)):
                return str(row.get(key))
        dt = row.get("datetime")
        return f"{fallback}:{pd.Timestamp(dt).strftime('%Y%m%d%H%M%S') if pd.notna(dt) else 'unknown'}"

    for _, row in trades_df.iterrows():
        trade_type = str(row.get("type", "")).upper()
        if trade_type == "BUY":
            current_buy = row
        elif trade_type == "SELL" and current_buy is not None:
            buy_price = float(current_buy.get("price", 0.0))
            sell_price = float(row.get("price", 0.0))
            profit_pct = (sell_price - buy_price) / buy_price if buy_price else 0.0
            pnl = sell_price - buy_price
            training_reward = profit_pct * 100.0
            pairs.append(
                TradePair(
                    pair_id=pair_id,
                    ticker=ticker or str(current_buy.get("ticker", "")),
                    buy_trade_id=_trade_id(current_buy, pair_id),
                    sell_trade_id=_trade_id(row, pair_id),
                    buy_time=pd.Timestamp(current_buy.get("datetime")),
                    sell_time=pd.Timestamp(row.get("datetime")),
                    buy_price=buy_price,
                    sell_price=sell_price,
                    profit_pct=profit_pct,
                    pnl=pnl,
                    training_reward=training_reward,
                    rr_stop_loss_price=float(current_buy.get("rr_stop_loss_price", float("nan"))),
                    rr_take_profit_price=float(current_buy.get("rr_take_profit_price", float("nan"))),
                    rr_stop_loss_time=pd.Timestamp(current_buy.get("rr_stop_loss_time", current_buy.get("datetime"))),
                    rr_take_profit_time=pd.Timestamp(current_buy.get("rr_take_profit_time", current_buy.get("datetime"))),
                    rr_basis=str(current_buy.get("rr_basis", "") or row.get("rr_basis", "") or ""),
                    buy_reason=str(current_buy.get("reason", current_buy.get("reason_text", "")) or ""),
                    sell_reason=str(row.get("reason", row.get("reason_text", "")) or ""),
                )
            )
            pair_id += 1
            current_buy = None

    return pairs


def pairs_to_dataframe(pairs: Iterable[TradePair]) -> pd.DataFrame:
    rows = []
    for pair in pairs:
        row = asdict(pair)
        row["buy_time"] = pd.Timestamp(row["buy_time"])
        row["sell_time"] = pd.Timestamp(row["sell_time"])
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=[
            "pair_id", "ticker", "buy_trade_id", "sell_trade_id", "buy_time", "sell_time", "buy_price", "sell_price",
            "profit_pct", "pnl", "training_reward", "rr_stop_loss_price", "rr_take_profit_price", "rr_stop_loss_time",
            "rr_take_profit_time", "rr_basis",
            "buy_reason", "sell_reason", "is_correct", "review_note",
        ])
    return pd.DataFrame(rows)


def ensure_reviews_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            "pair_id,ticker,buy_trade_id,sell_trade_id,buy_time,sell_time,buy_price,sell_price,profit_pct,pnl,training_reward,rr_stop_loss_price,rr_take_profit_price,rr_stop_loss_time,rr_take_profit_time,rr_basis,buy_reason,sell_reason,is_correct,review_note\n",
            encoding="utf-8",
        )


def append_trade_review(path: Path, review: Dict[str, object]) -> None:
    ensure_reviews_file(path)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "pair_id", "ticker", "buy_trade_id", "sell_trade_id", "buy_time", "sell_time", "buy_price", "sell_price",
                "profit_pct", "pnl", "training_reward", "rr_stop_loss_price", "rr_take_profit_price", "rr_stop_loss_time",
                "rr_take_profit_time", "rr_basis",
                "buy_reason", "sell_reason", "is_correct", "review_note",
            ],
        )
        if not file_exists:
            writer.writeheader()
        writer.writerow(review)
