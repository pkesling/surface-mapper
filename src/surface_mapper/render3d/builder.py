from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from surface_mapper.render.contracts import RenderScale, RenderStyle

if TYPE_CHECKING:
    import geopandas as gpd
    import pyvista as pv


Render3DMode = str


@dataclass(frozen=True)
class Surface3DSpec:
    mode: Render3DMode = "hex-prism"
    scale: RenderScale = "gamma"
    gamma: float = 0.6
    style: RenderStyle = "classic"
    colormap: str | None = None
    height_scale: float = 1.0
    base_z: float = 0.0
    scale_factor: float = 1.0
    z_exaggeration: float = 1.0
    camera_preset: str | None = None


class Surface3DBuilder(Protocol):
    def build(self, gdf: gpd.GeoDataFrame, spec: Surface3DSpec) -> pv.DataSet:
        """Build a 3D surface mesh from per-cell polygons + scaled values."""


def get_builder_registry() -> dict[str, type[Surface3DBuilder]]:
    from surface_mapper.render3d.hex_prism import HexPrismBuilder
    from surface_mapper.render3d.terrain import TerrainBuilder

    return {
        "hex-prism": HexPrismBuilder,
        "terrain": TerrainBuilder,
    }


def build_surface_mesh(gdf: gpd.GeoDataFrame, spec: Surface3DSpec):
    registry = get_builder_registry()
    if spec.mode not in registry:
        raise ValueError(f"Unsupported 3D mode: {spec.mode}. Use one of: {', '.join(sorted(registry))}.")
    builder = registry[spec.mode]()
    return builder.build(gdf, spec)
