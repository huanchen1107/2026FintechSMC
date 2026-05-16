"""Persist AI comments by model_id so the same model can reuse them."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


def _cache_path(outputs_dir: Path) -> Path:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return outputs_dir / "ai_comments.json"


def load_ai_comments(outputs_dir: Path) -> Dict[str, str]:
    path = _cache_path(outputs_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}


def get_ai_comment(outputs_dir: Path, model_id: str) -> Optional[str]:
    return load_ai_comments(outputs_dir).get(model_id)


def save_ai_comment(outputs_dir: Path, model_id: str, comment: str) -> None:
    path = _cache_path(outputs_dir)
    data = load_ai_comments(outputs_dir)
    data[model_id] = comment
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
