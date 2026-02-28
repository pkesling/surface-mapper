"""surface_mapper.store.duckdb_store module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import duckdb

from surface_mapper.contracts.normalized import (
    NORMALIZED_EVENTS_TABLE,
    NORMALIZED_OBS_TABLE,
    NormalizedEvent,
    NormalizedObservation,
)

_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def normalize_sql_identifier(value: str) -> str:
    """Normalize sql identifier."""
    name = value.strip()
    if not _SQL_IDENTIFIER_RE.fullmatch(name):
        raise ValueError(
            f"Invalid SQL identifier '{value}'. Use letters, numbers, and underscores only, "
            "and do not start with a number."
        )
    return name


def quote_sql_identifier(value: str) -> str:
    """Quote sql identifier."""
    name = normalize_sql_identifier(value)
    return f'"{name}"'


@dataclass(frozen=True)
class DuckDBStore:
    """Small wrapper around a DuckDB file for SurfaceMapper tables."""

    db_path: Path

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Connect."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.db_path))


def create_normalized_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create canonical normalized tables and basic indexes."""
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {NORMALIZED_OBS_TABLE} (
            dataset         VARCHAR NOT NULL,
            event_id        VARCHAR NOT NULL,
            observed_at     DATE NOT NULL,
            lat             DOUBLE NOT NULL,
            lon             DOUBLE NOT NULL,
            taxon           VARCHAR NOT NULL,
            count           INTEGER,
            is_complete     BOOLEAN
        );
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {NORMALIZED_EVENTS_TABLE} (
            dataset          VARCHAR NOT NULL,
            event_id         VARCHAR NOT NULL,
            observed_at      DATE NOT NULL,
            lat              DOUBLE NOT NULL,
            lon              DOUBLE NOT NULL,
            duration_minutes DOUBLE,
            distance_km      DOUBLE,
            area_ha          DOUBLE,
            protocol         VARCHAR,
            num_observers    INTEGER,
            is_complete      BOOLEAN
        );
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{NORMALIZED_OBS_TABLE}_event_id ON {NORMALIZED_OBS_TABLE}(event_id);"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{NORMALIZED_OBS_TABLE}_observed_at ON {NORMALIZED_OBS_TABLE}(observed_at);"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{NORMALIZED_EVENTS_TABLE}_event_id ON {NORMALIZED_EVENTS_TABLE}(event_id);"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{NORMALIZED_EVENTS_TABLE}_observed_at ON {NORMALIZED_EVENTS_TABLE}(observed_at);"
    )


def insert_normalized_observations(
    conn: duckdb.DuckDBPyConnection, rows: Iterable[NormalizedObservation]
) -> None:
    """Insert normalized observations."""
    payload = [
        (
            row.dataset,
            row.event_id,
            row.observed_at,
            row.lat,
            row.lon,
            row.taxon,
            row.count,
            row.is_complete,
        )
        for row in rows
    ]
    if not payload:
        return
    conn.executemany(
        f"INSERT INTO {NORMALIZED_OBS_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
        payload,
    )


def insert_normalized_events(
    conn: duckdb.DuckDBPyConnection, rows: Iterable[NormalizedEvent]
) -> None:
    """Insert normalized events."""
    payload = [
        (
            row.dataset,
            row.event_id,
            row.observed_at,
            row.lat,
            row.lon,
            row.duration_minutes,
            row.distance_km,
            row.area_ha,
            row.protocol,
            row.num_observers,
            row.is_complete,
        )
        for row in rows
    ]
    if not payload:
        return
    conn.executemany(
        f"INSERT INTO {NORMALIZED_EVENTS_TABLE} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        payload,
    )


def count_rows(conn: duckdb.DuckDBPyConnection, table_name: str) -> int:
    """Count rows."""
    table = quote_sql_identifier(table_name)
    return int(conn.execute(f"SELECT COUNT(*) FROM {table};").fetchone()[0])


__all__ = [
    "DuckDBStore",
    "create_normalized_tables",
    "insert_normalized_observations",
    "insert_normalized_events",
    "count_rows",
    "normalize_sql_identifier",
    "quote_sql_identifier",
]
