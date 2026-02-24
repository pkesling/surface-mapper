from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


GridType = Literal["h3"]
RenderStyle = Literal["classic", "neon"]
RenderScale = Literal["linear", "log", "gamma"]
RenderOutputFormat = Literal["png"]
RenderProjection = Literal["auto", "epsg:5070", "epsg:3857", "none"]
RenderLayoutMode = Literal["single", "quad"]


@dataclass(frozen=True)
class SurfaceQuery:
    db_path: str
    table: str = "surface_cells"
    dataset: str = "ebird-ebd"
    metric: str = "attention"
    grid: GridType = "h3"
    resolution: int = 6
    time_slice: str | None = None
    min_support: float | None = None


@dataclass(frozen=True)
class RenderSpec:
    style: RenderStyle = "classic"
    scale: RenderScale = "gamma"
    gamma: float = 0.6
    output_format: RenderOutputFormat = "png"
    width_px: int = 2200
    height_px: int = 1400
    dpi: int = 200
    pad_pct: float = 0.05
    show_legend: bool = True
    projection: RenderProjection = "auto"
    layout_mode: RenderLayoutMode = "single"
    quad_titles: bool = True
    neighbors: bool = True
    mask_water: bool = False
    region_file: str | None = None
    neighbors_file: str | None = None
    water_file: str | None = None
    region_key: str = "STUSPS"
    region_value: str | None = None
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
    legend_location: Literal["right", "bottom", "none"] = "right"
    legend_label: str | None = None
    title_enabled: bool = True
    title_fontsize: int = 16
    title_pad: float = 8.0
    subtitle_enabled: bool = True
    subtitle_fontsize: int = 11
    rotate_deg: float = 0.0
    preset_name: str = "classic"
    title: str | None = None
    subtitle: str | None = None
    out_path: str = "out.png"


@dataclass(frozen=True)
class RenderArtifacts:
    output_path: str
