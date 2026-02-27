from pathlib import Path

import duckdb
import h3
import json
import numpy as np
from typer.testing import CliRunner

from surface_mapper.cli.app import app
from surface_mapper.render3d.builder import get_builder_registry
from surface_mapper.surface.build import create_surface_table

runner = CliRunner()


def test_render3d_registry_contains_modes() -> None:
    registry = get_builder_registry()
    assert "hex-prism" in registry
    assert "terrain" in registry


def test_render_3d_terrain_mode_is_stubbed(tmp_path: Path) -> None:
    db_path = tmp_path / "render3d-terrain.duckdb"
    out_path = tmp_path / "out.glb"

    cell = h3.latlng_to_cell(43.0731, -89.4012, 6)

    conn = duckdb.connect(str(db_path))
    try:
        create_surface_table(conn, "surface_cells")
        conn.execute(
            """
            INSERT INTO surface_cells
            (dataset, grid, resolution, cell_id, metric, value, support, time_slice, start_date, end_date)
            VALUES
            ('ebird-ebd', 'h3', 6, ?, 'attention', 2.0, 2.0, NULL, NULL, NULL);
            """,
            [cell],
        )
    finally:
        conn.close()

    result = runner.invoke(
        app,
        [
            "render",
            "3d",
            "--mode",
            "terrain",
            "--db",
            str(db_path),
            "--metric",
            "attention",
            "--res",
            "6",
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 1
    assert "terrain" in result.output
    assert "not implemented" in result.output.lower()


def test_render_3d_preview_smoke_with_neighbors_and_water(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "render3d-preview.duckdb"
    out_path = tmp_path / "out.glb"
    preview_path = tmp_path / "preview.png"
    region_path = tmp_path / "region.geojson"
    neighbors_path = tmp_path / "neighbors.geojson"
    water_path = tmp_path / "water.geojson"

    cell = h3.latlng_to_cell(43.0731, -89.4012, 6)
    conn = duckdb.connect(str(db_path))
    try:
        create_surface_table(conn, "surface_cells")
        conn.execute(
            """
            INSERT INTO surface_cells
            (dataset, grid, resolution, cell_id, metric, value, support, time_slice, start_date, end_date)
            VALUES
            ('ebird-ebd', 'h3', 6, ?, 'attention', 2.0, 2.0, NULL, NULL, NULL);
            """,
            [cell],
        )
    finally:
        conn.close()

    def _feature(ring: list[tuple[float, float]], props: dict[str, str]):
        return {
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in ring]]},
        }

    region_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    _feature(
                        [
                            (-89.80, 42.70),
                            (-88.95, 42.70),
                            (-88.95, 43.45),
                            (-89.80, 43.45),
                            (-89.80, 42.70),
                        ],
                        {"STUSPS": "WI"},
                    )
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
                    _feature(
                        [
                            (-90.00, 42.60),
                            (-88.70, 42.60),
                            (-88.70, 43.55),
                            (-90.00, 43.55),
                            (-90.00, 42.60),
                        ],
                        {"name": "neighbors"},
                    )
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
                    _feature(
                        [
                            (-89.44, 43.02),
                            (-89.34, 43.02),
                            (-89.34, 43.10),
                            (-89.44, 43.10),
                            (-89.44, 43.02),
                        ],
                        {"name": "water"},
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    class _FakeMesh:
        point_data = {"value": [1.0]}
        cell_data = {}

        def __init__(self, points=None) -> None:
            self.points = np.array(
                points
                if points is not None
                else [
                    [-90.0, 42.5, -1.0],
                    [-88.0, 42.5, -1.0],
                    [-88.0, 43.6, 3.0],
                    [-90.0, 43.6, 3.0],
                ],
                dtype=float,
            )

        @property
        def bounds(self):
            return (
                float(self.points[:, 0].min()),
                float(self.points[:, 0].max()),
                float(self.points[:, 1].min()),
                float(self.points[:, 1].max()),
                float(self.points[:, 2].min()),
                float(self.points[:, 2].max()),
            )

        def copy(self, deep=True):
            del deep
            return _FakeMesh(self.points.copy())

    def _fake_build_surface_mesh(gdf, spec):
        assert spec.height_scale == 2.5
        return _FakeMesh()

    def _fake_polygon_gdf_to_flat_mesh(gdf, z, color_name):
        assert not gdf.empty
        assert color_name in {"neighbors", "water"}
        return _FakeMesh()

    def _fake_export_mesh(mesh, out_path, export_format):
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake-3d")
        return p

    def _fake_render_preview(
        hex_mesh,
        preview_path,
        cmap,
        style,
        base_z,
        neighbors_fill,
        neighbors_alpha,
        water_fill,
        water_alpha,
        north_up,
        neighbors_mesh,
        water_mesh,
        region_bounds,
        camera_preset,
    ):
        assert north_up is True
        assert neighbors_mesh is not None
        assert water_mesh is not None
        assert region_bounds is not None
        p = Path(preview_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake-preview")
        return p

    monkeypatch.setattr("surface_mapper.cli.app.build_surface_mesh", _fake_build_surface_mesh)
    monkeypatch.setattr("surface_mapper.cli.app.polygon_gdf_to_flat_mesh", _fake_polygon_gdf_to_flat_mesh)
    monkeypatch.setattr("surface_mapper.cli.app.export_mesh", _fake_export_mesh)
    monkeypatch.setattr("surface_mapper.cli.app.render_preview", _fake_render_preview)

    result = runner.invoke(
        app,
        [
            "render",
            "3d",
            "--mode",
            "hex-prism",
            "--db",
            str(db_path),
            "--metric",
            "attention",
            "--res",
            "6",
            "--height-scale",
            "2.5",
            "--region-file",
            str(region_path),
            "--region-value",
            "WI",
            "--neighbors-file",
            str(neighbors_path),
            "--water-file",
            str(water_path),
            "--mask-water",
            "--preview",
            str(preview_path),
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0
    assert out_path.exists()
    meta_path = Path(f"{out_path}.meta.json")
    assert meta_path.exists()
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    assert metadata["normalize_xy"] is True
    assert metadata["target_xy_size"] == 10.0
    assert metadata["xy_normalization_scale"] > 0.0
    assert preview_path.exists()
