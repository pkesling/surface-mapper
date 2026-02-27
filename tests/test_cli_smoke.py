from pathlib import Path
import re
import shutil

import duckdb
import pytest
from typer.testing import CliRunner

from surface_mapper.cli.app import app
from surface_mapper.contracts.normalized import NORMALIZED_OBS_TABLE
from surface_mapper.surface.build import create_surface_table

runner = CliRunner()


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _plain(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def test_help_runs() -> None:
    result = runner.invoke(app, ["--help"])
    output = _plain(result.output)
    assert result.exit_code == 0
    assert "Usage:" in output
    assert "surface-mapper" in output


def test_subcommand_help_runs() -> None:
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0


def test_run_help_runs() -> None:
    result = runner.invoke(app, ["run", "--help"])
    output = _plain(result.output)
    assert result.exit_code == 0
    assert "--obs" in output
    assert "--sampling" in output
    assert "--keep-artifacts" in output


def test_run_requires_sampling_for_ebird(tmp_path: Path) -> None:
    obs_path = tmp_path / "obs.tsv"
    obs_path.write_text("dummy\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "run",
            "--dataset",
            "ebird-ebd",
            "--obs",
            str(obs_path),
            "--out",
            str(tmp_path / "out.png"),
        ],
    )
    output = _plain(result.output)
    assert result.exit_code != 0
    assert "requires --sampling" in output


def test_run_orchestrates_and_cleans_temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    obs_path = tmp_path / "obs.tsv"
    sampling_path = tmp_path / "sampling.tsv"
    out_path = tmp_path / "out.png"
    obs_path.write_text("dummy\n", encoding="utf-8")
    sampling_path.write_text("dummy\n", encoding="utf-8")

    calls: dict[str, dict] = {}

    def _fake_ingest(*args, **kwargs):
        del args
        calls["ingest"] = kwargs
        Path(kwargs["out"]).write_bytes(b"duckdb-placeholder")

    def _fake_surface(*args, **kwargs):
        del args
        calls["surface"] = kwargs

    def _fake_render_flat(*args, **kwargs):
        del args
        calls["render_flat"] = kwargs
        Path(kwargs["out"]).write_bytes(b"fake-png")

    monkeypatch.setattr("surface_mapper.cli.app.ingest", _fake_ingest)
    monkeypatch.setattr("surface_mapper.cli.app.surface", _fake_surface)
    monkeypatch.setattr("surface_mapper.cli.app.render_flat", _fake_render_flat)

    result = runner.invoke(
        app,
        [
            "run",
            "--dataset",
            "ebird-ebd",
            "--obs",
            str(obs_path),
            "--sampling",
            str(sampling_path),
            "--out",
            str(out_path),
        ],
    )
    assert result.exit_code == 0
    assert out_path.exists()
    assert "pipeline complete" in result.output
    assert calls["ingest"]["dataset"] == "ebird-ebd"
    assert calls["render_flat"]["dataset"] == "ebird-ebd"
    assert calls["render_flat"]["style"] is None
    assert calls["render_flat"]["preset"] == "classic"

    db_path = Path(calls["ingest"]["out"])
    assert not db_path.exists()


def test_render3d_help_runs() -> None:
    result = runner.invoke(app, ["render3d", "--help"])
    output = _plain(result.output)
    assert result.exit_code == 0
    assert "--template" in output
    assert "--blender" in output
    assert "--dry-run" in output


def test_render_blender_help_runs() -> None:
    result = runner.invoke(app, ["render", "blender", "--help"])
    output = _plain(result.output)
    assert result.exit_code == 0
    assert "--template" in output
    assert "--blender" in output
    assert "--dry-run" in output


def test_render3d_dry_run_prints_command(tmp_path: Path) -> None:
    echo_bin = shutil.which("echo")
    if echo_bin is None:
        return

    glb_path = tmp_path / "mesh.glb"
    out_path = tmp_path / "render.png"
    glb_path.write_bytes(b"fake-glb")

    result = runner.invoke(
        app,
        [
            "render3d",
            "--glb",
            str(glb_path),
            "--out",
            str(out_path),
            "--blender",
            echo_bin,
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert " --glb " in result.output
    assert " --out " in result.output


def test_ingest_ebird_ebd_smoke(tmp_path: Path) -> None:
    obs_path = tmp_path / "obs.tsv"
    db_path = tmp_path / "out.duckdb"

    obs_path.write_text(
        "\t".join(
            [
                "SAMPLING EVENT IDENTIFIER",
                "OBSERVATION DATE",
                "LATITUDE",
                "LONGITUDE",
                "SCIENTIFIC NAME",
                "OBSERVATION COUNT",
            ]
        )
        + "\n"
        + "\t".join(["S1", "2025-01-01", "43.0", "-89.0", "Corvus brachyrhynchos", "2"])
        + "\n"
        + "\t".join(["S1", "2025-01-01", "43.0", "-89.0", "Poecile atricapillus", "1"])
        + "\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "ingest",
            "ebird-ebd",
            "--obs",
            str(obs_path),
            "--out",
            str(db_path),
            "--batch-size",
            "1",
            "--no-progress",
        ],
    )
    assert result.exit_code == 0

    conn = duckdb.connect(str(db_path))
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {NORMALIZED_OBS_TABLE}").fetchone()[0]
        assert count == 2
    finally:
        conn.close()


def test_export_surface_smoke(tmp_path: Path) -> None:
    db_path = tmp_path / "out.duckdb"
    parquet_path = tmp_path / "surfaces.parquet"

    conn = duckdb.connect(str(db_path))
    try:
        create_surface_table(conn, "surface_cells")
        conn.execute(
            """
            INSERT INTO surface_cells
            (dataset, grid, resolution, cell_id, metric, value, support, time_slice, start_date, end_date)
            VALUES ('ebird-ebd', 'h3', 6, '862681ac7ffffff', 'attention', 2.0, 2.0, NULL, NULL, NULL);
            """
        )
    finally:
        conn.close()

    result = runner.invoke(
        app,
        [
            "export",
            "surface",
            "--db",
            str(db_path),
            "--out",
            str(parquet_path),
        ],
    )
    assert result.exit_code == 0

    conn = duckdb.connect()
    try:
        rows = conn.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(parquet_path)]).fetchone()[0]
        assert rows == 1
    finally:
        conn.close()
