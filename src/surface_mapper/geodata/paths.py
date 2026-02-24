from __future__ import annotations

from pathlib import Path


def default_derived_paths(dest_dir: Path, state: str, derived_dir: Path | None = None) -> dict[str, Path]:
    base = derived_dir if derived_dir is not None else dest_dir / "derived"
    state_up = state.upper()
    return {
        "boundary_geojson": base / f"{state_up}_boundary.geojson",
        "boundary_wgs84_geojson": base / f"{state_up}_boundary_wgs84.geojson",
        "neighbors_geojson": base / f"{state_up}_neighbors.geojson",
        "lakes_geojson": base / f"{state_up}_lakes.geojson",
    }


__all__ = ["default_derived_paths"]
