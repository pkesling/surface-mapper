"""Tests for test_geodata_derive."""

from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon

from surface_mapper.geodata.derive import derive_boundary, derive_lakes, derive_neighbors


def test_derive_outputs_from_geojson_inputs(tmp_path: Path) -> None:
    """Test derive outputs from geojson inputs."""
    states_path = tmp_path / "states.geojson"
    lakes_path = tmp_path / "lakes.geojson"

    wi_main = Polygon([(-91.0, 42.5), (-86.5, 42.5), (-86.5, 47.5), (-91.0, 47.5), (-91.0, 42.5)])
    wi_island_a = Polygon([(-88.20, 47.00), (-88.15, 47.00), (-88.15, 47.04), (-88.20, 47.04), (-88.20, 47.00)])
    wi_island_b = Polygon([(-87.95, 46.90), (-87.90, 46.90), (-87.90, 46.94), (-87.95, 46.94), (-87.95, 46.90)])

    states = gpd.GeoDataFrame(
        {
            "STUSPS": ["WI", "MN", "IA", "IL", "MI"],
            "geometry": [
                MultiPolygon([wi_main, wi_island_a, wi_island_b]),
                Polygon([(-97.5, 43.0), (-91.0, 43.0), (-91.0, 49.0), (-97.5, 49.0), (-97.5, 43.0)]),
                Polygon([(-96.6, 40.2), (-90.1, 40.2), (-90.1, 43.5), (-96.6, 43.5), (-96.6, 40.2)]),
                Polygon([(-91.6, 36.9), (-87.4, 36.9), (-87.4, 42.6), (-91.6, 42.6), (-91.6, 36.9)]),
                Polygon([(-90.5, 41.7), (-82.0, 41.7), (-82.0, 48.4), (-90.5, 48.4), (-90.5, 41.7)]),
            ],
        },
        crs="EPSG:4326",
    )
    states.to_file(states_path, driver="GeoJSON")

    lakes = gpd.GeoDataFrame(
        {
            "name": ["Lake A", "Lake B"],
            "geometry": [
                Polygon([(-89.8, 43.1), (-89.3, 43.1), (-89.3, 43.5), (-89.8, 43.5), (-89.8, 43.1)]),
                Polygon([(-94.0, 46.0), (-93.5, 46.0), (-93.5, 46.4), (-94.0, 46.4), (-94.0, 46.0)]),
            ],
        },
        crs="EPSG:4326",
    )
    lakes.to_file(lakes_path, driver="GeoJSON")

    boundary_out = tmp_path / "WI_boundary.geojson"
    boundary_wgs84_out = tmp_path / "WI_boundary_wgs84.geojson"
    neighbors_out = tmp_path / "WI_neighbors.geojson"
    lakes_out = tmp_path / "WI_lakes.geojson"

    derive_boundary(states_path, state="WI", out_path=boundary_out, crs="EPSG:5070")
    derive_boundary(states_path, state="WI", out_path=boundary_wgs84_out, crs="EPSG:4326")
    derive_neighbors(states_path, neighbor_codes=["MN", "IA", "IL", "MI"], out_path=neighbors_out, crs="EPSG:5070")
    derive_lakes(lakes_path, boundary_out, lakes_out, crs="EPSG:5070", neighbors_geojson_path=neighbors_out)

    boundary_gdf = gpd.read_file(boundary_out)
    boundary_wgs84_gdf = gpd.read_file(boundary_wgs84_out)
    source_parts = len(states.iloc[0].geometry.geoms)
    derived_parts = len(boundary_gdf.iloc[0].geometry.geoms)
    derived_wgs84_parts = len(boundary_wgs84_gdf.iloc[0].geometry.geoms)

    assert boundary_out.exists() and boundary_out.stat().st_size > 0
    assert boundary_wgs84_out.exists() and boundary_wgs84_out.stat().st_size > 0
    assert neighbors_out.exists() and neighbors_out.stat().st_size > 0
    assert lakes_out.exists() and lakes_out.stat().st_size > 0
    assert derived_parts == source_parts
    assert derived_wgs84_parts == source_parts

    lakes_gdf = gpd.read_file(lakes_out)
    assert "Lake A" in set(lakes_gdf["name"])
    assert "Lake B" in set(lakes_gdf["name"])
