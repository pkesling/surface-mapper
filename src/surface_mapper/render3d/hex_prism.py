"""surface_mapper.render3d.hex_prism module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from shapely.ops import triangulate
from shapely.geometry import MultiPolygon, Polygon

from surface_mapper.render3d.builder import Surface3DBuilder, Surface3DSpec

if TYPE_CHECKING:
    import geopandas as gpd
    import pyvista as pv


def _require_pyvista():
    """Internal helper for require pyvista."""
    try:
        import pyvista as pv
    except ImportError as exc:
        raise ImportError(
            "render 3d requires optional dependency 'pyvista'. Install with: pip install 'surface-mapper[render3d]'"
        ) from exc
    return pv


def _polygon_base_mesh(polygon: Polygon, base_z: float):
    """Internal helper for polygon base mesh."""
    pv = _require_pyvista()
    ring = list(polygon.exterior.coords)
    if len(ring) < 4:
        return None
    points = np.array([(float(x), float(y), float(base_z)) for x, y in ring[:-1]], dtype=float)
    if len(points) < 3:
        return None
    faces = np.hstack(([len(points)], np.arange(len(points), dtype=np.int64)))
    return pv.PolyData(points, faces).triangulate()


def _mesh_parts_for_geometry(geom):
    """Internal helper for mesh parts for geometry."""
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return []


def _triangle_to_polydata(triangle: Polygon, z: float):
    """Internal helper for triangle to polydata."""
    pv = _require_pyvista()
    coords = list(triangle.exterior.coords)
    if len(coords) < 4:
        return None
    points = np.array([(float(x), float(y), float(z)) for x, y in coords[:3]], dtype=float)
    faces = np.array([3, 0, 1, 2], dtype=np.int64)
    return pv.PolyData(points, faces)


def polygon_gdf_to_flat_mesh(gdf: gpd.GeoDataFrame, z: float, color_name: str):
    """Convert polygon geodata into a single flat mesh at constant z."""
    del color_name

    meshes = []
    for row in gdf.itertuples(index=False):
        for polygon in _mesh_parts_for_geometry(row.geometry):
            if polygon.is_empty:
                continue
            for tri in triangulate(polygon):
                if tri.is_empty:
                    continue
                # Keep only triangles truly within the polygon footprint.
                if not polygon.covers(tri.representative_point()):
                    continue
                tri_mesh = _triangle_to_polydata(tri, z)
                if tri_mesh is not None:
                    meshes.append(tri_mesh)

    if not meshes:
        return None

    combined = meshes[0]
    for mesh in meshes[1:]:
        combined = combined.merge(mesh, merge_points=False)
    return combined


class HexPrismBuilder(Surface3DBuilder):
    """HexPrismBuilder."""
    def build(self, gdf: gpd.GeoDataFrame, spec: Surface3DSpec) -> pv.DataSet:
        """Build."""
        meshes = []

        for row in gdf.itertuples(index=False):
            geom = row.geometry
            scaled_value = float(row.scaled_value)
            height = float(spec.height_scale) * scaled_value * float(spec.scale_factor) * float(spec.z_exaggeration)
            for polygon in _mesh_parts_for_geometry(geom):
                base_mesh = _polygon_base_mesh(polygon, spec.base_z)
                if base_mesh is None:
                    continue
                if abs(height) > 1e-12:
                    prism = base_mesh.extrude((0.0, 0.0, height), capping=True)
                else:
                    prism = base_mesh
                prism.point_data["value"] = np.full(prism.n_points, scaled_value, dtype=float)
                prism.cell_data["value"] = np.full(prism.n_cells, scaled_value, dtype=float)
                meshes.append(prism)

        if not meshes:
            raise ValueError("No valid polygon geometry available for hex-prism 3D rendering.")

        combined = meshes[0]
        for mesh in meshes[1:]:
            combined = combined.merge(mesh, merge_points=False)
        return combined
