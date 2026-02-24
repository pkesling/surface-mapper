import json
from pathlib import Path

import duckdb
import h3
from typer.testing import CliRunner

from surface_mapper.cli.app import app
from surface_mapper.surface.build import create_surface_table

runner = CliRunner()


def _write_geojson(path: Path, properties: dict[str, str], ring: list[tuple[float, float]]) -> None:
    feature = {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[list(p) for p in ring]],
        },
    }
    payload = {"type": "FeatureCollection", "features": [feature]}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_render_flat_with_region_neighbors_water(tmp_path: Path) -> None:
    db_path = tmp_path / "render-layers.duckdb"
    out_path = tmp_path / "render-layers.png"

    cell_a = h3.latlng_to_cell(43.0731, -89.4012, 6)
    cell_b = h3.latlng_to_cell(43.12, -89.35, 6)

    conn = duckdb.connect(str(db_path))
    try:
        create_surface_table(conn, "surface_cells")
        conn.execute(
            """
            INSERT INTO surface_cells
            (dataset, grid, resolution, cell_id, metric, value, support, time_slice, start_date, end_date)
            VALUES
            ('ebird-ebd', 'h3', 6, ?, 'attention', 2.0, 2.0, NULL, NULL, NULL),
            ('ebird-ebd', 'h3', 6, ?, 'attention', 4.0, 3.0, NULL, NULL, NULL);
            """,
            [cell_a, cell_b],
        )
    finally:
        conn.close()

    region_path = tmp_path / "region.geojson"
    neighbors_path = tmp_path / "neighbors.geojson"
    water_path = tmp_path / "water.geojson"

    # Region square around both cells.
    _write_geojson(
        region_path,
        {"STUSPS": "WI", "name": "Wisconsin"},
        [
            (-89.55, 42.95),
            (-89.20, 42.95),
            (-89.20, 43.25),
            (-89.55, 43.25),
            (-89.55, 42.95),
        ],
    )

    # Larger neighbors context square.
    _write_geojson(
        neighbors_path,
        {"name": "neighbors"},
        [
            (-89.80, 42.70),
            (-88.95, 42.70),
            (-88.95, 43.45),
            (-89.80, 43.45),
            (-89.80, 42.70),
        ],
    )

    # Water polygon overlapping one part of the target region.
    _write_geojson(
        water_path,
        {"name": "water"},
        [
            (-89.44, 43.02),
            (-89.34, 43.02),
            (-89.34, 43.10),
            (-89.44, 43.10),
            (-89.44, 43.02),
        ],
    )

    result = runner.invoke(
        app,
        [
            "render",
            "flat",
            "--db",
            str(db_path),
            "--dataset",
            "ebird-ebd",
            "--metric",
            "attention",
            "--res",
            "6",
            "--region-file",
            str(region_path),
            "--region-key",
            "STUSPS",
            "--region-value",
            "WI",
            "--neighbors-file",
            str(neighbors_path),
            "--neighbors",
            "--water-file",
            str(water_path),
            "--mask-water",
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0
    assert out_path.exists()
    assert out_path.stat().st_size > 0
