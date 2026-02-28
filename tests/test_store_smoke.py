"""Tests for test_store_smoke."""

from datetime import date
from pathlib import Path

import pytest

from surface_mapper.contracts.normalized import (
    NORMALIZED_EVENTS_TABLE,
    NORMALIZED_OBS_TABLE,
    NormalizedEvent,
    NormalizedObservation,
)
from surface_mapper.store.duckdb_store import (
    DuckDBStore,
    count_rows,
    create_normalized_tables,
    insert_normalized_events,
    insert_normalized_observations,
    normalize_sql_identifier,
    quote_sql_identifier,
)


def test_store_creates_tables_and_inserts(tmp_path: Path) -> None:
    """Test store creates tables and inserts."""
    db_path = tmp_path / "store-smoke.duckdb"
    store = DuckDBStore(db_path=db_path)
    conn = store.connect()
    try:
        create_normalized_tables(conn)

        insert_normalized_events(
            conn,
            [
                NormalizedEvent(
                    dataset="test",
                    event_id="evt-1",
                    observed_at=date(2025, 1, 1),
                    lat=43.0,
                    lon=-89.0,
                    duration_minutes=35.0,
                    distance_km=1.2,
                    protocol="stationary",
                    num_observers=1,
                    is_complete=True,
                )
            ],
        )

        insert_normalized_observations(
            conn,
            [
                NormalizedObservation(
                    dataset="test",
                    event_id="evt-1",
                    observed_at=date(2025, 1, 1),
                    lat=43.0,
                    lon=-89.0,
                    taxon="Corvus brachyrhynchos",
                    count=2,
                    is_complete=True,
                ),
                NormalizedObservation(
                    dataset="test",
                    event_id="evt-1",
                    observed_at=date(2025, 1, 1),
                    lat=43.0,
                    lon=-89.0,
                    taxon="Poecile atricapillus",
                    count=1,
                    is_complete=True,
                ),
            ],
        )

        assert count_rows(conn, NORMALIZED_EVENTS_TABLE) == 1
        assert count_rows(conn, NORMALIZED_OBS_TABLE) == 2
    finally:
        conn.close()


@pytest.mark.parametrize(
    "identifier, expected",
    [
        ("surface_cells", '"surface_cells"'),
        (" surface_cells ", '"surface_cells"'),
        ("surface_cells_2026", '"surface_cells_2026"'),
    ],
)
def test_quote_sql_identifier_accepts_safe_names(identifier: str, expected: str) -> None:
    """Test quote sql identifier accepts safe names."""
    assert quote_sql_identifier(identifier) == expected


@pytest.mark.parametrize(
    "identifier",
    [
        "1surface",
        "surface-cells",
        "surface cells",
        "surface_cells; DROP TABLE surface_cells;--",
        "",
    ],
)
def test_quote_sql_identifier_rejects_unsafe_names(identifier: str) -> None:
    """Test quote sql identifier rejects unsafe names."""
    with pytest.raises(ValueError):
        normalize_sql_identifier(identifier)
