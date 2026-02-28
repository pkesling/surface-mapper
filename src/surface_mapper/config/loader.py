"""surface_mapper.config.loader module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def default_config_path() -> Path:
    """Default config path."""
    local_path = Path.cwd() / "config.json"
    if local_path.exists():
        return local_path
    return Path.home() / ".config" / "surface-mapper" / "config.json"


def load_json_config(path: Path | None) -> dict[str, Any]:
    """Load json config."""
    config_path = path if path is not None else default_config_path()
    if not config_path.exists():
        return {}

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config root must be a JSON object: {config_path}")
    return payload


def render_flat_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Render flat config."""
    render = payload.get("render")
    if not isinstance(render, dict):
        return {}
    flat = render.get("flat")
    if not isinstance(flat, dict):
        return {}
    return flat


def render_3d_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Render 3d config."""
    render = payload.get("render")
    if not isinstance(render, dict):
        return {}
    layer = render.get("3d")
    if not isinstance(layer, dict):
        return {}
    return layer


__all__ = ["default_config_path", "load_json_config", "render_flat_config", "render_3d_config"]
