"""Simple model registry for keeping the best saved training runs."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


REGISTRY_FILENAME = "model_registry.json"
MODELS_DIRNAME = "models"
MAX_MODELS = 2


def _ensure_dirs(outputs_dir: Path) -> tuple[Path, Path]:
    models_dir = outputs_dir / MODELS_DIRNAME
    models_dir.mkdir(parents=True, exist_ok=True)
    registry_path = models_dir / REGISTRY_FILENAME
    if not registry_path.exists():
        registry_path.write_text("[]", encoding="utf-8")
    return models_dir, registry_path


def _read_registry(registry_path: Path) -> List[Dict[str, Any]]:
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return []


def _write_registry(registry_path: Path, items: List[Dict[str, Any]]) -> None:
    registry_path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def model_score(item: Dict[str, Any]) -> float:
    sharpe = float(item.get("sharpe", 0.0) or 0.0)
    total_return = float(item.get("total_return", 0.0) or 0.0)
    max_drawdown = abs(float(item.get("max_drawdown", 0.0) or 0.0))
    return sharpe + total_return - max_drawdown


def list_models(outputs_dir: Path) -> List[Dict[str, Any]]:
    _, registry_path = _ensure_dirs(outputs_dir)
    items = _read_registry(registry_path)
    return sorted(items, key=model_score, reverse=True)


def get_best_model(outputs_dir: Path) -> Optional[Dict[str, Any]]:
    models = list_models(outputs_dir)
    return models[0] if models else None


def load_model_by_id(outputs_dir: Path, model_id: str) -> Optional[Dict[str, Any]]:
    for item in list_models(outputs_dir):
        if item.get("model_id") == model_id:
            return item
    return None


def delete_model_by_id(outputs_dir: Path, model_id: str) -> Optional[Dict[str, Any]]:
    _, registry_path = _ensure_dirs(outputs_dir)
    items = _read_registry(registry_path)
    kept = []
    removed = None
    for item in items:
        if item.get("model_id") == model_id:
            removed = item
            path_str = item.get("path")
            if path_str:
                delete_model_artifact_if_present(str(path_str))
        else:
            kept.append(item)
    _write_registry(registry_path, kept)
    return removed


def register_model(
    outputs_dir: Path,
    *,
    model_path: str,
    ticker: str,
    sharpe: float,
    total_return: float,
    max_drawdown: float,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    models_dir, registry_path = _ensure_dirs(outputs_dir)
    strategy_mode = str((extra or {}).get("strategy_mode", "dqn_position"))
    strategy_tag = str(
        (extra or {}).get("strategy_label")
        or (extra or {}).get("strategy_label_tag")
        or ("dqn-on-buy-rr-box-sell" if strategy_mode == "dqn_on_buy_rr_box_sell" else ("dqn-on-buy" if strategy_mode == "dqn_on_buy" else "dqn-position"))
    )
    model_id = f"{ticker}_{strategy_tag}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    record = {
        "model_id": model_id,
        "ticker": ticker,
        "strategy_mode": strategy_mode,
        "path": str(model_path),
        "sharpe": float(sharpe),
        "total_return": float(total_return),
        "max_drawdown": float(max_drawdown),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    if extra:
        record.update(extra)

    items = _read_registry(registry_path)
    previous_paths = {item.get("path") for item in items}
    items.append(record)
    items = sorted(items, key=model_score, reverse=True)
    kept_items = items[:MAX_MODELS]
    kept_paths = {item.get("path") for item in kept_items}
    for old_path in previous_paths - kept_paths:
        if old_path:
            delete_model_artifact_if_present(str(old_path))
    items = kept_items
    _write_registry(registry_path, items)
    return record


def delete_model_artifact_if_present(path_str: str) -> None:
    try:
        path = Path(path_str)
        if path.exists():
            path.unlink()
    except Exception:
        pass
