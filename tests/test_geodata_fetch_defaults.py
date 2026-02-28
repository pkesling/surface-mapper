"""Tests for test_geodata_fetch_defaults."""

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from surface_mapper.cli.app import app
from surface_mapper.geodata.defaults import DEFAULT_LAKES, DEFAULT_STATES

runner = CliRunner()


@pytest.mark.network
def test_geodata_fetch_defaults_smoke(tmp_path: Path) -> None:
    """Test geodata fetch defaults smoke."""
    if os.getenv("SURFACEMAPPER_OFFLINE") == "1":
        pytest.skip("SURFACEMAPPER_OFFLINE=1")

    result = runner.invoke(app, ["geodata", "fetch-defaults", "--dest", str(tmp_path)])
    if result.exit_code != 0:
        pytest.skip(f"Network unavailable or remote blocked: {result.output}")

    states = list((tmp_path / "states").glob("*.shp"))
    lakes = list((tmp_path / "lakes").glob("*.shp"))
    derived = tmp_path / "derived"

    assert any(p.name == f"{DEFAULT_STATES.expected_basename}.shp" for p in states)
    assert any(p.name == f"{DEFAULT_LAKES.expected_basename}.shp" for p in lakes)
    assert (derived / "WI_boundary.geojson").exists()
    assert (derived / "WI_boundary_wgs84.geojson").exists()
    assert (derived / "WI_neighbors.geojson").exists()
    assert (derived / "WI_lakes.geojson").exists()
