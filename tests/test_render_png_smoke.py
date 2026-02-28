"""Tests for test_render_png_smoke."""

from pathlib import Path
import json

import duckdb
import h3
from typer.testing import CliRunner

from surface_mapper.cli.app import app
from surface_mapper.surface.build import create_surface_table

runner = CliRunner()


def test_render_flat_png_smoke(tmp_path: Path) -> None:
    """Test render flat png smoke."""
    db_path = tmp_path / "render-png.duckdb"
    out_path = tmp_path / "render.png"
    region_path = tmp_path / "region.geojson"
    neighbors_path = tmp_path / "neighbors.geojson"
    water_path = tmp_path / "water.geojson"

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

    region_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"STUSPS": "WI"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[
                                [-130.0, 20.0],
                                [-60.0, 20.0],
                                [-60.0, 55.0],
                                [-130.0, 55.0],
                                [-130.0, 20.0],
                            ]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    neighbors_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "neighbors"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[
                                [-130.0, 20.0],
                                [-58.0, 20.0],
                                [-58.0, 57.0],
                                [-130.0, 57.0],
                                [-130.0, 20.0],
                            ]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    water_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "water"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[
                                [-121.0, 31.0],
                                [-120.5, 31.0],
                                [-120.5, 31.5],
                                [-121.0, 31.5],
                                [-121.0, 31.0],
                            ]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
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
            "--neighbors-file",
            str(neighbors_path),
            "--water-file",
            str(water_path),
            "--mask-water",
            "--rotate-deg",
            "-2.5",
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0
    assert out_path.exists()
    assert out_path.stat().st_size > 0
