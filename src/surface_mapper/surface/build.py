"""surface_mapper.surface.build module."""

from __future__ import annotations

import csv
import logging
import tempfile
import time
from pathlib import Path

import duckdb

from surface_mapper.contracts.normalized import NORMALIZED_EVENTS_TABLE, NORMALIZED_OBS_TABLE
from surface_mapper.contracts.surface import SURFACE_TABLE_DEFAULT
from surface_mapper.grid.h3_grid import h3_cell
from surface_mapper.store.duckdb_store import normalize_sql_identifier, quote_sql_identifier

logger = logging.getLogger("surface_mapper.surface.build")

EVENT_CELLS_TABLE = "event_cells"
SEASON_CASE_SQL = (
    "CASE "
    "WHEN EXTRACT(MONTH FROM observed_at) IN (12, 1, 2) THEN 'winter' "
    "WHEN EXTRACT(MONTH FROM observed_at) IN (3, 4, 5) THEN 'spring' "
    "WHEN EXTRACT(MONTH FROM observed_at) IN (6, 7, 8) THEN 'summer' "
    "ELSE 'fall' END"
)


def create_surface_table(conn: duckdb.DuckDBPyConnection, table_name: str = SURFACE_TABLE_DEFAULT) -> None:
    """Create surface table."""
    normalized_name = normalize_sql_identifier(table_name)
    table = quote_sql_identifier(normalized_name)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            dataset     VARCHAR NOT NULL,
            grid        VARCHAR NOT NULL,
            resolution  INTEGER NOT NULL,
            cell_id     VARCHAR NOT NULL,
            metric      VARCHAR NOT NULL,
            value       DOUBLE NOT NULL,
            support     DOUBLE,
            time_slice  VARCHAR,
            start_date  DATE,
            end_date    DATE
        );
        """
    )
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{normalized_name}_metric ON {table}(metric);")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{normalized_name}_cell_id ON {table}(cell_id);")


def create_event_cells_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create event cells table."""
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {EVENT_CELLS_TABLE} (
            dataset     VARCHAR NOT NULL,
            event_id    VARCHAR NOT NULL,
            observed_at DATE NOT NULL,
            resolution  INTEGER NOT NULL,
            cell_id     VARCHAR NOT NULL
        );
        """
    )


def create_event_cells_indexes(conn: duckdb.DuckDBPyConnection) -> None:
    """Create event cells indexes."""
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{EVENT_CELLS_TABLE}_event_id ON {EVENT_CELLS_TABLE}(event_id);"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{EVENT_CELLS_TABLE}_cell_id ON {EVENT_CELLS_TABLE}(cell_id);"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{EVENT_CELLS_TABLE}_observed_at ON {EVENT_CELLS_TABLE}(observed_at);"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{EVENT_CELLS_TABLE}_resolution ON {EVENT_CELLS_TABLE}(resolution);"
    )


def drop_event_cells_indexes(conn: duckdb.DuckDBPyConnection) -> None:
    """Drop event cells indexes."""
    conn.execute(f"DROP INDEX IF EXISTS idx_{EVENT_CELLS_TABLE}_event_id;")
    conn.execute(f"DROP INDEX IF EXISTS idx_{EVENT_CELLS_TABLE}_cell_id;")
    conn.execute(f"DROP INDEX IF EXISTS idx_{EVENT_CELLS_TABLE}_observed_at;")
    conn.execute(f"DROP INDEX IF EXISTS idx_{EVENT_CELLS_TABLE}_resolution;")


def build_event_cells(
    conn: duckdb.DuckDBPyConnection,
    dataset: str,
    res: int,
    force: bool = False,
    batch_size: int = 50000,
) -> int:
    """Build event cells."""
    create_event_cells_table(conn)
    create_event_cells_indexes(conn)

    existing = int(
        conn.execute(
            f"SELECT COUNT(*) FROM {EVENT_CELLS_TABLE} WHERE dataset = ? AND resolution = ?;",
            [dataset, res],
        ).fetchone()[0]
    )
    if existing > 0 and not force:
        logger.info("event_cells already present for dataset=%s res=%d rows=%d", dataset, res, existing)
        return 0

    if force and existing > 0:
        logger.info("Rebuilding event_cells for dataset=%s res=%d", dataset, res)
        conn.execute(
            f"DELETE FROM {EVENT_CELLS_TABLE} WHERE dataset = ? AND resolution = ?;",
            [dataset, res],
        )
    else:
        logger.info("Building event_cells for dataset=%s res=%d", dataset, res)

    start_time = time.time()
    total_rows = int(
        conn.execute(
            f"SELECT COUNT(*) FROM {NORMALIZED_EVENTS_TABLE} WHERE dataset = ?;",
            [dataset],
        ).fetchone()[0]
    )
    inserted = 0
    processed = 0
    drop_event_cells_indexes(conn)
    temp_path: str | None = None
    try:
        rows = conn.execute(
            f"""
            SELECT dataset, event_id, observed_at, lat, lon
            FROM {NORMALIZED_EVENTS_TABLE}
            WHERE dataset = ?;
            """,
            [dataset],
        ).fetchall()

        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            suffix=".tsv",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            writer = csv.writer(temp_file, delimiter="\t", lineterminator="\n")

            next_log = batch_size
            for ds, event_id, observed_at, lat, lon in rows:
                writer.writerow(
                    [
                        ds,
                        event_id,
                        observed_at.isoformat(),
                        res,
                        h3_cell(float(lat), float(lon), res),
                    ]
                )
                processed += 1

                if processed < next_log:
                    continue

                elapsed = max(time.time() - start_time, 1e-9)
                rate = processed / elapsed
                logger.info(
                    "event_cells progress dataset=%s res=%d processed=%d/%d staged=%d inserted=%d rate=%.1f rows/s elapsed=%.1fs",
                    dataset,
                    res,
                    processed,
                    total_rows,
                    processed,
                    inserted,
                    rate,
                    elapsed,
                )
                next_log += batch_size

        conn.execute(
            f"""
            INSERT INTO {EVENT_CELLS_TABLE}
            SELECT
                dataset,
                event_id,
                CAST(observed_at AS DATE),
                CAST(resolution AS INTEGER),
                cell_id
            FROM read_csv(
                ?,
                delim='\t',
                header=false,
                columns={{
                    'dataset': 'VARCHAR',
                    'event_id': 'VARCHAR',
                    'observed_at': 'VARCHAR',
                    'resolution': 'INTEGER',
                    'cell_id': 'VARCHAR'
                }}
            );
            """,
            [temp_path],
        )
        inserted = total_rows
        processed = total_rows
        elapsed = max(time.time() - start_time, 1e-9)
        rate = processed / elapsed
        logger.info(
            "event_cells progress dataset=%s res=%d processed=%d/%d staged=%d inserted=%d rate=%.1f rows/s elapsed=%.1fs",
            dataset,
            res,
            processed,
            total_rows,
            processed,
            inserted,
            rate,
            elapsed,
        )
    finally:
        if temp_path is not None:
            Path(temp_path).unlink(missing_ok=True)
        create_event_cells_indexes(conn)

    logger.info("Built event_cells dataset=%s res=%d inserted=%d", dataset, res, inserted)
    return inserted


def _metric_delete_sql(table_name: str, metric: str, time_slice: str | None) -> tuple[str, list[object]]:
    """Internal helper for metric delete sql."""
    table = quote_sql_identifier(table_name)
    if time_slice is None:
        return (
            f"DELETE FROM {table} WHERE dataset = ? AND resolution = ? AND metric = ? AND time_slice IS NULL;",
            [],
        )
    return (
        f"DELETE FROM {table} WHERE dataset = ? AND resolution = ? AND metric = ? AND time_slice = ?;",
        [time_slice],
    )


def _event_cells_scope(time_slice: str | None) -> tuple[str, list[object]]:
    """Internal helper for event cells scope."""
    if time_slice is None:
        return ("", [])
    return (f" AND {SEASON_CASE_SQL} = ?", [time_slice])


def write_surface_attention(
    conn: duckdb.DuckDBPyConnection,
    dataset: str,
    res: int,
    out_table: str,
    time_slice: str | None = None,
) -> int:
    """Write surface attention."""
    create_surface_table(conn, out_table)
    out_table_sql = quote_sql_identifier(out_table)
    delete_sql, delete_extra = _metric_delete_sql(out_table, "attention", time_slice)
    conn.execute(delete_sql, [dataset, res, "attention", *delete_extra])

    scope_sql, scope_args = _event_cells_scope(time_slice)
    conn.execute(
        f"""
        INSERT INTO {out_table_sql}
        SELECT
            ?,
            'h3',
            ?,
            ec.cell_id,
            'attention',
            CAST(COUNT(*) AS DOUBLE) AS value,
            CAST(COUNT(*) AS DOUBLE) AS support,
            ?,
            NULL,
            NULL
        FROM {EVENT_CELLS_TABLE} ec
        WHERE ec.dataset = ? AND ec.resolution = ? {scope_sql}
        GROUP BY ec.cell_id;
        """,
        [dataset, res, time_slice, dataset, res, *scope_args],
    )

    if time_slice is None:
        return int(
            conn.execute(
                f"SELECT COUNT(*) FROM {out_table_sql} WHERE dataset=? AND resolution=? AND metric='attention' AND time_slice IS NULL;",
                [dataset, res],
            ).fetchone()[0]
        )
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM {out_table_sql} WHERE dataset=? AND resolution=? AND metric='attention' AND time_slice=?;",
            [dataset, res, time_slice],
        ).fetchone()[0]
    )


def write_surface_richness_unique(
    conn: duckdb.DuckDBPyConnection,
    dataset: str,
    res: int,
    out_table: str,
    time_slice: str | None = None,
    min_checklists: int | None = None,
) -> int:
    """Write surface richness unique."""
    create_surface_table(conn, out_table)
    out_table_sql = quote_sql_identifier(out_table)
    delete_sql, delete_extra = _metric_delete_sql(out_table, "richness_unique", time_slice)
    conn.execute(delete_sql, [dataset, res, "richness_unique", *delete_extra])

    scope_sql, scope_args = _event_cells_scope(time_slice)
    conn.execute(
        f"""
        INSERT INTO {out_table_sql}
        WITH ec_filtered AS (
            SELECT dataset, event_id, cell_id
            FROM {EVENT_CELLS_TABLE}
            WHERE dataset = ? AND resolution = ? {scope_sql}
        ),
        support AS (
            SELECT cell_id, COUNT(*) AS checklist_count
            FROM ec_filtered
            GROUP BY cell_id
        ),
        richness AS (
            SELECT ec.cell_id, COUNT(DISTINCT o.taxon) AS richness_unique
            FROM ec_filtered ec
            JOIN {NORMALIZED_OBS_TABLE} o
              ON o.dataset = ec.dataset
             AND o.event_id = ec.event_id
            GROUP BY ec.cell_id
        )
        SELECT
            ?,
            'h3',
            ?,
            r.cell_id,
            'richness_unique',
            CAST(r.richness_unique AS DOUBLE),
            CAST(s.checklist_count AS DOUBLE),
            ?,
            NULL,
            NULL
        FROM richness r
        JOIN support s ON s.cell_id = r.cell_id
        WHERE (? IS NULL OR s.checklist_count >= ?);
        """,
        [dataset, res, *scope_args, dataset, res, time_slice, min_checklists, min_checklists],
    )

    if time_slice is None:
        return int(
            conn.execute(
                f"SELECT COUNT(*) FROM {out_table_sql} WHERE dataset=? AND resolution=? AND metric='richness_unique' AND time_slice IS NULL;",
                [dataset, res],
            ).fetchone()[0]
        )
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM {out_table_sql} WHERE dataset=? AND resolution=? AND metric='richness_unique' AND time_slice=?;",
            [dataset, res, time_slice],
        ).fetchone()[0]
    )


def write_surface_richness_mean(
    conn: duckdb.DuckDBPyConnection,
    dataset: str,
    res: int,
    out_table: str,
    time_slice: str | None = None,
    min_checklists: int | None = None,
) -> int:
    """Write surface richness mean."""
    create_surface_table(conn, out_table)
    out_table_sql = quote_sql_identifier(out_table)
    delete_sql, delete_extra = _metric_delete_sql(out_table, "richness_mean", time_slice)
    conn.execute(delete_sql, [dataset, res, "richness_mean", *delete_extra])

    scope_sql, scope_args = _event_cells_scope(time_slice)
    conn.execute(
        f"""
        INSERT INTO {out_table_sql}
        WITH ec_filtered AS (
            SELECT dataset, event_id, cell_id
            FROM {EVENT_CELLS_TABLE}
            WHERE dataset = ? AND resolution = ? {scope_sql}
        ),
        per_event_species AS (
            SELECT dataset, event_id, COUNT(DISTINCT taxon) AS species_count
            FROM {NORMALIZED_OBS_TABLE}
            WHERE dataset = ?
            GROUP BY dataset, event_id
        ),
        per_cell AS (
            SELECT
                ec.cell_id,
                AVG(CAST(pes.species_count AS DOUBLE)) AS richness_mean,
                COUNT(*) AS checklist_count
            FROM ec_filtered ec
            JOIN per_event_species pes
              ON pes.dataset = ec.dataset
             AND pes.event_id = ec.event_id
            GROUP BY ec.cell_id
        )
        SELECT
            ?,
            'h3',
            ?,
            cell_id,
            'richness_mean',
            richness_mean,
            CAST(checklist_count AS DOUBLE),
            ?,
            NULL,
            NULL
        FROM per_cell
        WHERE (? IS NULL OR checklist_count >= ?);
        """,
        [dataset, res, *scope_args, dataset, dataset, res, time_slice, min_checklists, min_checklists],
    )

    if time_slice is None:
        return int(
            conn.execute(
                f"SELECT COUNT(*) FROM {out_table_sql} WHERE dataset=? AND resolution=? AND metric='richness_mean' AND time_slice IS NULL;",
                [dataset, res],
            ).fetchone()[0]
        )
    return int(
        conn.execute(
            f"SELECT COUNT(*) FROM {out_table_sql} WHERE dataset=? AND resolution=? AND metric='richness_mean' AND time_slice=?;",
            [dataset, res, time_slice],
        ).fetchone()[0]
    )


__all__ = [
    "EVENT_CELLS_TABLE",
    "create_surface_table",
    "create_event_cells_table",
    "build_event_cells",
    "write_surface_attention",
    "write_surface_richness_unique",
    "write_surface_richness_mean",
]
