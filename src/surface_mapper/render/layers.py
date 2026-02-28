"""surface_mapper.render.layers module."""

from __future__ import annotations

import geopandas as gpd


def load_layer(path: str) -> gpd.GeoDataFrame:
    """Load layer."""
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise ValueError(f"Layer is empty: {path}")
    if gdf.geometry.is_empty.all():
        raise ValueError(f"Layer has no valid geometry: {path}")
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def select_polygon(gdf: gpd.GeoDataFrame, key: str, value: str | None) -> gpd.GeoDataFrame:
    """Select polygon."""
    selected = gdf
    if value is not None:
        if key not in gdf.columns:
            raise ValueError(f"Field '{key}' not found in layer. Available fields: {', '.join(gdf.columns)}")
        selected = gdf[gdf[key].astype(str) == str(value)]

    if selected.empty:
        if value is None:
            raise ValueError("No polygons available in layer")
        raise ValueError(f"No polygons matched {key}={value}")

    dissolved = selected.dissolve()
    if dissolved.empty or dissolved.geometry.is_empty.all():
        raise ValueError("Selected polygon geometry is empty after dissolve")
    return dissolved


def reproject_to(gdf: gpd.GeoDataFrame, crs: str | None) -> gpd.GeoDataFrame:
    """Reproject to."""
    if crs is None:
        return gdf
    return gdf.to_crs(crs)
