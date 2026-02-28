"""surface_mapper.render3d.transforms module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import geopandas as gpd
import numpy as np
from shapely.affinity import scale as scale_geom
from shapely.affinity import translate as translate_geom


ScaleUnits = Literal["m", "km"]
CenterOrigin = Literal["region", "data"]
TARGET_XY_SIZE = 10.0
_EPS = 1e-12


@dataclass(frozen=True)
class XYTransform:
    """XYTransform."""
    origin_x: float
    origin_y: float
    scale_factor: float


def scale_factor_for_units(units: str) -> float:
    """Scale factor for units."""
    if units == "m":
        return 1.0
    if units == "km":
        return 0.001
    raise ValueError(f"Unsupported scale units: {units}. Use one of: m, km.")


def transform_xy(geom, ox: float, oy: float, scale_factor: float):
    """Transform xy."""
    shifted = translate_geom(geom, xoff=-ox, yoff=-oy)
    return scale_geom(shifted, xfact=scale_factor, yfact=scale_factor, origin=(0.0, 0.0))


def transform_xy_gdf(gdf: gpd.GeoDataFrame, ox: float, oy: float, scale_factor: float) -> gpd.GeoDataFrame:
    """Transform xy gdf."""
    transformed = gdf.copy()
    transformed["geometry"] = transformed.geometry.apply(lambda geom: transform_xy(geom, ox, oy, scale_factor))
    return transformed


def normalize_xy_points(
    points: np.ndarray,
    target_size: float = TARGET_XY_SIZE,
    enabled: bool = True,
) -> tuple[np.ndarray, float]:
    """Normalize xy points."""
    arr = np.asarray(points, dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError("Expected points as an array shaped (n, 2+) with X and Y coordinates.")

    out = arr.copy()
    if not enabled or out.shape[0] == 0:
        return out, 1.0

    span_x = float(np.max(out[:, 0]) - np.min(out[:, 0]))
    span_y = float(np.max(out[:, 1]) - np.min(out[:, 1]))
    max_span = max(span_x, span_y)
    if max_span <= _EPS:
        return out, 1.0

    xy_scale = float(target_size) / max_span
    out[:, 0] *= xy_scale
    out[:, 1] *= xy_scale
    return out, xy_scale


def scale_xy_points(points: np.ndarray, xy_scale: float) -> np.ndarray:
    """Scale xy points."""
    arr = np.asarray(points, dtype=float)
    if arr.ndim != 2 or arr.shape[1] < 2:
        raise ValueError("Expected points as an array shaped (n, 2+) with X and Y coordinates.")
    if abs(float(xy_scale) - 1.0) <= _EPS:
        return arr.copy()
    out = arr.copy()
    out[:, 0] *= float(xy_scale)
    out[:, 1] *= float(xy_scale)
    return out


def _copy_mesh(mesh):
    """Internal helper for copy mesh."""
    if hasattr(mesh, "copy"):
        try:
            return mesh.copy(deep=True)
        except TypeError:
            return mesh.copy()
    return mesh


def normalize_mesh_xy(mesh, target_size: float = TARGET_XY_SIZE, enabled: bool = True):
    """Normalize mesh xy."""
    points = getattr(mesh, "points", None)
    if points is None:
        raise ValueError("Mesh does not expose point coordinates via .points for XY normalization.")
    normalized_points, xy_scale = normalize_xy_points(points, target_size=target_size, enabled=enabled)
    if abs(xy_scale - 1.0) <= _EPS:
        return mesh, 1.0
    mesh_out = _copy_mesh(mesh)
    mesh_out.points = normalized_points
    return mesh_out, xy_scale


def scale_mesh_xy(mesh, xy_scale: float):
    """Scale mesh xy."""
    if mesh is None or abs(float(xy_scale) - 1.0) <= _EPS:
        return mesh
    points = getattr(mesh, "points", None)
    if points is None:
        raise ValueError("Mesh does not expose point coordinates via .points for XY scaling.")
    mesh_out = _copy_mesh(mesh)
    mesh_out.points = scale_xy_points(points, xy_scale=float(xy_scale))
    return mesh_out


def _region_center(boundary_gdf: gpd.GeoDataFrame) -> tuple[float, float]:
    """Internal helper for region center."""
    if hasattr(boundary_gdf.geometry, "union_all"):
        center = boundary_gdf.geometry.union_all().centroid
    else:
        center = boundary_gdf.unary_union.centroid
    return float(center.x), float(center.y)


def _data_center(gdf: gpd.GeoDataFrame) -> tuple[float, float]:
    """Internal helper for data center."""
    min_x, min_y, max_x, max_y = gdf.total_bounds
    return float(0.5 * (min_x + max_x)), float(0.5 * (min_y + max_y))


def resolve_xy_transform(
    gdf: gpd.GeoDataFrame,
    boundary_gdf: gpd.GeoDataFrame | None,
    center: bool,
    center_origin: str,
    scale_units: str,
) -> XYTransform:
    """Resolve xy transform."""
    scale_factor = scale_factor_for_units(scale_units)
    if not center:
        return XYTransform(origin_x=0.0, origin_y=0.0, scale_factor=scale_factor)

    if center_origin == "region" and boundary_gdf is not None and not boundary_gdf.empty:
        ox, oy = _region_center(boundary_gdf)
    else:
        ox, oy = _data_center(gdf)
    return XYTransform(origin_x=ox, origin_y=oy, scale_factor=scale_factor)
