import json
from pathlib import Path

import duckdb
import h3
from typer.testing import CliRunner

from surface_mapper.cli.app import app
from surface_mapper.render.contracts import SurfaceQuery
from surface_mapper.render.flat import stats_sidecar_path
from surface_mapper.render.load_surface import load_surface
from surface_mapper.surface.build import create_surface_table

runner = CliRunner()


def test_load_surface_and_render_flat_cli(tmp_path: Path) -> None:
    db_path = tmp_path / "render.duckdb"
    out_path = tmp_path / "out.png"
    region_path = tmp_path / "region.geojson"

    conn = duckdb.connect(str(db_path))
    try:
        create_surface_table(conn, "surface_cells")
        conn.execute(
            """
            INSERT INTO surface_cells
            (dataset, grid, resolution, cell_id, metric, value, support, time_slice, start_date, end_date)
            VALUES
            ('ebird-ebd', 'h3', 6, '862681ac7ffffff', 'attention', 2.0, 2.0, NULL, NULL, NULL),
            ('ebird-ebd', 'h3', 6, '862681adfffffff', 'attention', 4.0, 3.0, NULL, NULL, NULL);
            """
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

    df = load_surface(
        SurfaceQuery(
            db_path=str(db_path),
            table="surface_cells",
            dataset="ebird-ebd",
            metric="attention",
            grid="h3",
            resolution=6,
        )
    )
    assert len(df) == 2

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
            "--region-file",
            str(region_path),
            "--out",
            str(out_path),
        ],
    )
    assert result.exit_code == 0

    sidecar = stats_sidecar_path(str(out_path))
    assert sidecar.exists()
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert payload.get("rowcount") == 2


def test_render_flat_cli_supports_json_config(tmp_path: Path) -> None:
    db_path = tmp_path / "render-config.duckdb"
    out_path = tmp_path / "out-config.png"
    config_path = tmp_path / "config.json"
    neighbors_path = tmp_path / "neighbors.geojson"
    region_path = tmp_path / "region.geojson"

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
            [
                h3.latlng_to_cell(43.0731, -89.4012, 6),
                h3.latlng_to_cell(43.12, -89.35, 6),
            ],
        )
    finally:
        conn.close()

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
                                [-89.80, 42.70],
                                [-88.95, 42.70],
                                [-88.95, 43.45],
                                [-89.80, 43.45],
                                [-89.80, 42.70],
                            ]],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

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

    config_path.write_text(
        json.dumps(
            {
                "render": {
                    "flat": {
                        "db": str(db_path),
                        "metric": "attention",
                        "res": 6,
                        "out": str(out_path),
                        "region_file": str(region_path),
                        "neighbors_file": str(neighbors_path),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["render", "flat", "--config", str(config_path)])
    assert result.exit_code == 0
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_render_flat_uses_local_config_json_by_default(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "render-local-config.duckdb"
    out_path = tmp_path / "out-local-config.png"
    config_path = tmp_path / "config.json"
    region_path = tmp_path / "region.geojson"

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
            [
                h3.latlng_to_cell(43.0731, -89.4012, 6),
                h3.latlng_to_cell(43.12, -89.35, 6),
            ],
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

    config_path.write_text(
        json.dumps(
            {
                "render": {
                    "flat": {
                        "db": str(db_path),
                        "metric": "attention",
                        "res": 6,
                        "region_file": str(region_path),
                        "out": str(out_path),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["render", "flat"])
    assert result.exit_code == 0
    assert out_path.exists()
    assert out_path.stat().st_size > 0
