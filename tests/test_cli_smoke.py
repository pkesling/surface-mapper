from pathlib import Path

import duckdb
from typer.testing import CliRunner

from surface_mapper.cli.app import app
from surface_mapper.contracts.normalized import NORMALIZED_OBS_TABLE
from surface_mapper.surface.build import create_surface_table

runner = CliRunner()


def test_help_runs() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "surface-mapper" in result.output


def test_subcommand_help_runs() -> None:
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0


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
