from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class PresetLegend(BaseModel):
    show: bool = True
    location: Literal["right", "bottom", "none"] = "right"
    label: str | None = None


class PresetTitle(BaseModel):
    enabled: bool = True
    fontsize: int = 16
    pad: float = 8.0


class PresetSubtitle(BaseModel):
    enabled: bool = True
    fontsize: int = 11


class PresetLayout(BaseModel):
    mode: Literal["single", "quad"] = "single"
    quad_titles: bool = True


class PresetScaleDefaults(BaseModel):
    scale: Literal["linear", "log", "gamma"] = "gamma"
    gamma: float = 0.6


class PresetFraming(BaseModel):
    pad_pct: float = 0.05


class RenderPreset(BaseModel):
    name: str
    style: str = "classic"
    colormap: str | None = None
    diverging_colormap: str | None = None
    background_color: str = "#ffffff"
    neighbors_fill: str = "#e6e6e6"
    neighbors_alpha: float = 0.45
    water_fill: str = "#d9ecff"
    water_alpha: float = 0.9
    outline_color: str = "#4a4a4a"
    outline_width: float = 1.1
    edge_color: str | None = None
    edge_width: float = 0.1
    legend: PresetLegend = Field(default_factory=PresetLegend)
    title: PresetTitle = Field(default_factory=PresetTitle)
    subtitle: PresetSubtitle = Field(default_factory=PresetSubtitle)
    layout: PresetLayout = Field(default_factory=PresetLayout)
    scale_defaults: PresetScaleDefaults = Field(default_factory=PresetScaleDefaults)
    framing: PresetFraming = Field(default_factory=PresetFraming)

    @classmethod
    def load(cls, name_or_path: str) -> "RenderPreset":
        builtin_dir = Path(__file__).resolve().parent / "builtin"
        builtin_path = builtin_dir / f"{name_or_path}.json"
        if builtin_path.exists():
            return cls.model_validate_json(builtin_path.read_text(encoding="utf-8"))

        path = Path(name_or_path).expanduser()
        if not path.exists():
            raise ValueError(f"Preset not found as builtin or file path: {name_or_path}")

        if path.suffix.lower() == ".json":
            return cls.model_validate_json(path.read_text(encoding="utf-8"))

        if path.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except Exception as exc:  # pragma: no cover
                raise ValueError("YAML preset requested but PyYAML is not installed") from exc
            payload = yaml.safe_load(path.read_text(encoding="utf-8"))
            return cls.model_validate(payload)

        raise ValueError(f"Unsupported preset file extension: {path.suffix}")


__all__ = ["RenderPreset"]
