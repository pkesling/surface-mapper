from datetime import date
from pathlib import Path

from surface_mapper.contracts.normalized import NormalizedEvent, NormalizedObservation
from surface_mapper.store.duckdb_store import (
    DuckDBStore,
    create_normalized_tables,
    insert_normalized_events,
    insert_normalized_observations,
)
from surface_mapper.surface.build import (
    build_event_cells,
    create_event_cells_table,
    create_surface_table,
    write_surface_attention,
    write_surface_richness_unique,
)


def test_surface_build_attention_and_richness_unique(tmp_path: Path) -> None:
    db_path = tmp_path / "surface-smoke.duckdb"
    conn = DuckDBStore(db_path).connect()
    try:
        create_normalized_tables(conn)
        create_surface_table(conn, "surface_cells")
        create_event_cells_table(conn)

        insert_normalized_events(
            conn,
            [
                NormalizedEvent(
                    dataset="ebird-ebd",
                    event_id="E1",
                    observed_at=date(2025, 1, 10),
                    lat=43.0,
                    lon=-89.0,
                ),
                NormalizedEvent(
                    dataset="ebird-ebd",
                    event_id="E2",
                    observed_at=date(2025, 1, 11),
                    lat=43.0,
                    lon=-89.0,
                ),
            ],
        )

        insert_normalized_observations(
            conn,
            [
                NormalizedObservation(
                    dataset="ebird-ebd",
                    event_id="E1",
                    observed_at=date(2025, 1, 10),
                    lat=43.0,
                    lon=-89.0,
                    taxon="Corvus brachyrhynchos",
                    count=1,
                ),
                NormalizedObservation(
                    dataset="ebird-ebd",
                    event_id="E2",
                    observed_at=date(2025, 1, 11),
                    lat=43.0,
                    lon=-89.0,
                    taxon="Poecile atricapillus",
                    count=1,
                ),
            ],
        )

        build_event_cells(conn, dataset="ebird-ebd", res=6, force=True, batch_size=1000)

        rows_attention = write_surface_attention(
            conn,
            dataset="ebird-ebd",
            res=6,
            out_table="surface_cells",
        )
        assert rows_attention == 1

        attention_value = conn.execute(
            """
            SELECT value
            FROM surface_cells
            WHERE dataset = 'ebird-ebd' AND resolution = 6 AND metric = 'attention' AND time_slice IS NULL
            """
        ).fetchone()[0]
        assert attention_value == 2.0

        rows_richness = write_surface_richness_unique(
            conn,
            dataset="ebird-ebd",
            res=6,
            out_table="surface_cells",
        )
        assert rows_richness == 1

        richness_value = conn.execute(
            """
            SELECT value
            FROM surface_cells
            WHERE dataset = 'ebird-ebd' AND resolution = 6 AND metric = 'richness_unique' AND time_slice IS NULL
            """
        ).fetchone()[0]
        assert richness_value == 2.0
    finally:
        conn.close()
