"""surface_mapper.render3d.terrain module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from surface_mapper.render3d.builder import Surface3DBuilder, Surface3DSpec

if TYPE_CHECKING:
    import geopandas as gpd
    import pyvista as pv


class TerrainBuilder(Surface3DBuilder):
    """TerrainBuilder."""
    def build(self, gdf: gpd.GeoDataFrame, spec: Surface3DSpec) -> pv.DataSet:
        """Build."""
        raise NotImplementedError("3D render mode 'terrain' is not implemented yet. Use --mode hex-prism for now.")

