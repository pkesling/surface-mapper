from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from shapely.geometry import box
from shapely.geometry import MultiPolygon, Polygon

try:
    # Shapely 2.x
    from shapely.validation import make_valid  # type: ignore
except Exception:  # pragma: no cover
    make_valid = None  # type: ignore

LAKES_BOUNDARY_BUFFER_METERS = 20_000.0


def derive_boundary(states_path: Path, state: str, out_path: Path, crs: str) -> Path:
    states = gpd.read_file(states_path)
    if "STUSPS" not in states.columns:
        raise ValueError(f"Expected STUSPS field in states layer: {states_path}")

    selected = states[states["STUSPS"].astype(str) == state]
    if selected.empty:
        raise ValueError(f"No state found for STUSPS='{state}' in {states_path}")

    # Preserve source geometry fidelity (including small islands/parts): no dissolve/simplify.
    boundary = selected.copy()
    if boundary.crs is None:
        boundary = boundary.set_crs("EPSG:4326")
    boundary = boundary.to_crs(crs)

    # Keep a multipart boundary representation in derived output for stable downstream behavior.
    boundary = boundary.copy()
    boundary["geometry"] = boundary.geometry.apply(
        lambda geom: MultiPolygon([geom]) if isinstance(geom, Polygon) else geom
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    boundary.to_file(out_path, driver="GeoJSON")
    return out_path


def derive_neighbors(states_path: Path, neighbor_codes: list[str], out_path: Path, crs: str) -> Path:
    states = gpd.read_file(states_path)
    if "STUSPS" not in states.columns:
        raise ValueError(f"Expected STUSPS field in states layer: {states_path}")

    codes = {code.strip() for code in neighbor_codes if code.strip()}
    selected = states[states["STUSPS"].astype(str).isin(codes)]
    if selected.empty:
        raise ValueError(f"No neighbors found for codes={sorted(codes)} in {states_path}")

    if selected.crs is None:
        selected = selected.set_crs("EPSG:4326")
    selected = selected.to_crs(crs)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    selected.to_file(out_path, driver="GeoJSON")
    return out_path


def derive_lakes(lakes_path: Path, boundary_geojson_path: Path, out_path: Path, crs: str) -> Path:
    """Derive a lakes GeoJSON suitable for *rendering context*.

    We intentionally clip lakes to a padded bounding box around the state boundary
    (in an equal-area CRS), rather than clipping to the boundary polygon itself.

    Clipping to the boundary polygon produces only shoreline-adjacent slivers of
    large lakes (e.g., Lake Michigan/Superior). A bbox clip keeps full lake polygons
    while still dramatically shrinking the global lakes layer.
    """

    lakes = gpd.read_file(lakes_path)
    boundary = gpd.read_file(boundary_geojson_path)

    if lakes.empty:
        raise ValueError(f"Lakes layer is empty: {lakes_path}")
    if boundary.empty:
        raise ValueError(f"Boundary layer is empty: {boundary_geojson_path}")

    if lakes.crs is None:
        lakes = lakes.set_crs("EPSG:4326")
    if boundary.crs is None:
        boundary = boundary.set_crs("EPSG:4326")

    lakes = lakes.to_crs(crs)
    boundary = boundary.to_crs(crs)

    # Repair invalid lake geometries if possible (helps later union/difference operations).
    if make_valid is not None:
        lakes = lakes.copy()
        lakes["geometry"] = lakes.geometry.apply(lambda g: make_valid(g) if g is not None else g)
    else:
        # Fallback: buffer(0) can fix many self-intersections.
        lakes = lakes.copy()
        lakes["geometry"] = lakes.geometry.buffer(0)

    # Clip to a padded bbox around the boundary.
    minx, miny, maxx, maxy = boundary.total_bounds
    pad = LAKES_BOUNDARY_BUFFER_METERS
    bbox = box(minx - pad, miny - pad, maxx + pad, maxy + pad)
    bbox_gdf = gpd.GeoDataFrame({"_": [1]}, geometry=[bbox], crs=boundary.crs)

    clipped = gpd.clip(lakes, bbox_gdf)
    clipped = clipped[~clipped.geometry.is_empty]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    clipped.to_file(out_path, driver="GeoJSON")
    return out_path


__all__ = ["derive_boundary", "derive_neighbors", "derive_lakes", "LAKES_BOUNDARY_BUFFER_METERS"]
