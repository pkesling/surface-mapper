from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import geopandas as gpd
from shapely.affinity import scale as scale_geom
from shapely.affinity import translate as translate_geom


ScaleUnits = Literal["m", "km"]
CenterOrigin = Literal["region", "data"]


@dataclass(frozen=True)
class XYTransform:
    origin_x: float
    origin_y: float
    scale_factor: float


def scale_factor_for_units(units: str) -> float:
    if units == "m":
        return 1.0
    if units == "km":
        return 0.001
    raise ValueError(f"Unsupported scale units: {units}. Use one of: m, km.")


def transform_xy(geom, ox: float, oy: float, scale_factor: float):
    shifted = translate_geom(geom, xoff=-ox, yoff=-oy)
    return scale_geom(shifted, xfact=scale_factor, yfact=scale_factor, origin=(0.0, 0.0))


def transform_xy_gdf(gdf: gpd.GeoDataFrame, ox: float, oy: float, scale_factor: float) -> gpd.GeoDataFrame:
    transformed = gdf.copy()
    transformed["geometry"] = transformed.geometry.apply(lambda geom: transform_xy(geom, ox, oy, scale_factor))
    return transformed


def _region_center(boundary_gdf: gpd.GeoDataFrame) -> tuple[float, float]:
    if hasattr(boundary_gdf.geometry, "union_all"):
        center = boundary_gdf.geometry.union_all().centroid
    else:
        center = boundary_gdf.unary_union.centroid
    return float(center.x), float(center.y)


def _data_center(gdf: gpd.GeoDataFrame) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = gdf.total_bounds
    return float(0.5 * (min_x + max_x)), float(0.5 * (min_y + max_y))


def resolve_xy_transform(
    gdf: gpd.GeoDataFrame,
    boundary_gdf: gpd.GeoDataFrame | None,
    center: bool,
    center_origin: str,
    scale_units: str,
) -> XYTransform:
    scale_factor = scale_factor_for_units(scale_units)
    if not center:
        return XYTransform(origin_x=0.0, origin_y=0.0, scale_factor=scale_factor)

    if center_origin == "region" and boundary_gdf is not None and not boundary_gdf.empty:
        ox, oy = _region_center(boundary_gdf)
    else:
        ox, oy = _data_center(gdf)
    return XYTransform(origin_x=ox, origin_y=oy, scale_factor=scale_factor)
