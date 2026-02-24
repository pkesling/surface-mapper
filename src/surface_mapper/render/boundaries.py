from __future__ import annotations

import geopandas as gpd


def get_state_boundary(state_code: str | None, source_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if source_gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs=source_gdf.crs)
    _ = state_code
    shape = source_gdf.geometry.union_all().convex_hull.buffer(0)
    return gpd.GeoDataFrame(geometry=[shape], crs=source_gdf.crs)


def get_neighbor_boundary(boundary_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if boundary_gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs=boundary_gdf.crs)
    outer = boundary_gdf.geometry.iloc[0].buffer(boundary_gdf.geometry.iloc[0].length * 0.15)
    frame = outer.difference(boundary_gdf.geometry.iloc[0])
    return gpd.GeoDataFrame(geometry=[frame], crs=boundary_gdf.crs)
