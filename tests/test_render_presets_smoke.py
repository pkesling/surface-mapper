"""Tests for test_render_presets_smoke."""

from pathlib import Path
import json

import duckdb
import h3
from typer.testing import CliRunner

from surface_mapper.cli.app import app
from surface_mapper.surface.build import create_surface_table

runner = CliRunner()


def test_render_preset_neon_single_smoke(tmp_path: Path) -> None:
    """Test render preset neon single smoke."""
    db_path = tmp_path / "render-neon.duckdb"
    out_path = tmp_path / "render-neon.png"
    region_path = tmp_path / "region.geojson"

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

    result = runner.invoke(
        app,
        [
            "render",
            "flat",
            "--db",
            str(db_path),
            "--metric",
            "attention",
            "--res",
            "6",
            "--preset",
            "neon",
            "--region-file",
            str(region_path),
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_render_preset_classic_quad_smoke(tmp_path: Path) -> None:
    """Test render preset classic quad smoke."""
    db_path = tmp_path / "render-quad.duckdb"
    out_path = tmp_path / "render-quad.png"
    region_path = tmp_path / "region.geojson"

    cells = [
        h3.latlng_to_cell(43.0731, -89.4012, 6),
        h3.latlng_to_cell(43.20, -89.20, 6),
        h3.latlng_to_cell(43.00, -89.10, 6),
        h3.latlng_to_cell(43.12, -89.35, 6),
    ]

    conn = duckdb.connect(str(db_path))
    try:
        create_surface_table(conn, "surface_cells")
        conn.execute(
            """
            INSERT INTO surface_cells
            (dataset, grid, resolution, cell_id, metric, value, support, time_slice, start_date, end_date)
            VALUES
            ('ebird-ebd', 'h3', 6, ?, 'attention', 1.0, 2.0, 'winter', NULL, NULL),
            ('ebird-ebd', 'h3', 6, ?, 'attention', 2.0, 2.0, 'spring', NULL, NULL),
            ('ebird-ebd', 'h3', 6, ?, 'attention', 3.0, 2.0, 'summer', NULL, NULL),
            ('ebird-ebd', 'h3', 6, ?, 'attention', 4.0, 2.0, 'fall', NULL, NULL);
            """,
            cells,
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

    result = runner.invoke(
        app,
        [
            "render",
            "flat",
            "--db",
            str(db_path),
            "--metric",
            "attention",
            "--res",
            "6",
            "--preset",
            "classic",
            "--layout",
            "quad",
            "--region-file",
            str(region_path),
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0
    assert out_path.exists()
    assert out_path.stat().st_size > 0
