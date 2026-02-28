"""surface_mapper.ingest.adapters.ebird module."""

from __future__ import annotations

import csv
import logging
import math
import time
from datetime import date
from pathlib import Path

import duckdb
import typer

from surface_mapper.contracts.normalized import (
    NORMALIZED_EVENTS_TABLE,
    NORMALIZED_OBS_TABLE,
    NormalizedEvent,
    NormalizedObservation,
)
from surface_mapper.ingest.adapters.base import IngestAdapter
from surface_mapper.ingest.types import IngestRequest, IngestStats
from surface_mapper.store.duckdb_store import (
    count_rows,
    insert_normalized_events,
    insert_normalized_observations,
)

logger = logging.getLogger("surface_mapper.ingest.ebird")

_OBS_REQUIRED_COLUMNS = {
    "SAMPLING EVENT IDENTIFIER",
    "OBSERVATION DATE",
    "LATITUDE",
    "LONGITUDE",
    "SCIENTIFIC NAME",
    "OBSERVATION COUNT",
}
_SAMPLING_REQUIRED_COLUMNS = {
    "SAMPLING EVENT IDENTIFIER",
    "OBSERVATION DATE",
    "LATITUDE",
    "LONGITUDE",
}


class EbirdIngestAdapter(IngestAdapter):
    """EbirdIngestAdapter."""

    @property
    def name(self) -> str:
        """Name."""
        return "ebird-ebd"

    @property
    def aliases(self) -> tuple[str, ...]:
        """Aliases."""
        return ("ebd", "ebird")

    def ingest(self, conn: duckdb.DuckDBPyConnection, request: IngestRequest) -> IngestStats:
        """Ingest."""
        dataset_key = self.name
        if request.python_parser:
            return self._ingest_with_python_parser(conn, dataset_key, request)
        return self._ingest_with_duckdb_parser(conn, dataset_key, request)

    def _ingest_with_duckdb_parser(
        self,
        conn: duckdb.DuckDBPyConnection,
        dataset_key: str,
        request: IngestRequest,
    ) -> IngestStats:
        """Internal helper for ingest with duckdb parser."""
        logger.info("Using DuckDB-native CSV parser")
        obs_columns = _read_csv_columns(conn, request.obs_path)
        _check_required_columns(request.obs_path, obs_columns, _OBS_REQUIRED_COLUMNS)

        obs_has_is_complete = "ALL SPECIES REPORTED" in obs_columns
        obs_is_complete_expr = (
            "CASE TRIM(COALESCE(CAST(\"ALL SPECIES REPORTED\" AS VARCHAR), '')) "
            "WHEN '1' THEN TRUE WHEN '0' THEN FALSE ELSE NULL END"
            if obs_has_is_complete
            else "NULL"
        )

        rows_read_obs = _count_source_rows(conn, request.obs_path) if request.progress else 0
        if request.progress and rows_read_obs:
            for checkpoint in range(request.progress_every, rows_read_obs + 1, request.progress_every):
                _emit_progress("obs", checkpoint, 0, 0, request.start_time)

        before_obs = count_rows(conn, NORMALIZED_OBS_TABLE)
        conn.execute(
            f"""
            INSERT INTO {NORMALIZED_OBS_TABLE}
            SELECT
                ?,
                TRIM(CAST("SAMPLING EVENT IDENTIFIER" AS VARCHAR)) AS event_id,
                TRY_CAST("OBSERVATION DATE" AS DATE) AS observed_at,
                TRY_CAST("LATITUDE" AS DOUBLE) AS lat,
                TRY_CAST("LONGITUDE" AS DOUBLE) AS lon,
                TRIM(CAST("SCIENTIFIC NAME" AS VARCHAR)) AS taxon,
                CASE
                    WHEN regexp_matches(TRIM(COALESCE(CAST("OBSERVATION COUNT" AS VARCHAR), '')), '^[0-9]+$')
                        THEN CAST(TRIM(CAST("OBSERVATION COUNT" AS VARCHAR)) AS INTEGER)
                    ELSE NULL
                END AS count,
                {obs_is_complete_expr} AS is_complete
            FROM read_csv(?, delim='\t', header=true, quote='', strict_mode=false)
            WHERE TRY_CAST("OBSERVATION DATE" AS DATE) IS NOT NULL
                AND TRY_CAST("LATITUDE" AS DOUBLE) IS NOT NULL
                AND TRY_CAST("LONGITUDE" AS DOUBLE) IS NOT NULL
                AND TRIM(COALESCE(CAST("SAMPLING EVENT IDENTIFIER" AS VARCHAR), '')) <> ''
                AND TRIM(COALESCE(CAST("SCIENTIFIC NAME" AS VARCHAR), '')) <> '';
            """,
            [dataset_key, str(request.obs_path)],
        )
        inserted_obs = count_rows(conn, NORMALIZED_OBS_TABLE) - before_obs
        batches_flushed_obs = math.ceil(inserted_obs / request.batch_size) if inserted_obs > 0 else 0

        rows_read_events = 0
        inserted_events = 0
        batches_flushed_events = 0
        if request.sampling_path is not None:
            sampling_columns = _read_csv_columns(conn, request.sampling_path)
            _check_required_columns(request.sampling_path, sampling_columns, _SAMPLING_REQUIRED_COLUMNS)

            sampling_has_is_complete = "ALL SPECIES REPORTED" in sampling_columns
            events_is_complete_expr = (
                "CASE TRIM(COALESCE(CAST(\"ALL SPECIES REPORTED\" AS VARCHAR), '')) "
                "WHEN '1' THEN TRUE WHEN '0' THEN FALSE ELSE NULL END"
                if sampling_has_is_complete
                else "NULL"
            )

            rows_read_events = _count_source_rows(conn, request.sampling_path) if request.progress else 0
            if request.progress and rows_read_events:
                for checkpoint in range(request.progress_every, rows_read_events + 1, request.progress_every):
                    _emit_progress("events", checkpoint, 0, 0, request.start_time)

            before_events = count_rows(conn, NORMALIZED_EVENTS_TABLE)
            conn.execute(
                f"""
                INSERT INTO {NORMALIZED_EVENTS_TABLE}
                SELECT
                    ?,
                    TRIM(CAST("SAMPLING EVENT IDENTIFIER" AS VARCHAR)) AS event_id,
                    TRY_CAST("OBSERVATION DATE" AS DATE) AS observed_at,
                    TRY_CAST("LATITUDE" AS DOUBLE) AS lat,
                    TRY_CAST("LONGITUDE" AS DOUBLE) AS lon,
                    TRY_CAST("DURATION MINUTES" AS DOUBLE) AS duration_minutes,
                    TRY_CAST("EFFORT DISTANCE KM" AS DOUBLE) AS distance_km,
                    TRY_CAST("EFFORT AREA HA" AS DOUBLE) AS area_ha,
                    NULLIF(TRIM(COALESCE(CAST("PROTOCOL NAME" AS VARCHAR), '')), '') AS protocol,
                    TRY_CAST("NUMBER OBSERVERS" AS INTEGER) AS num_observers,
                    {events_is_complete_expr} AS is_complete
                FROM read_csv(?, delim='\t', header=true, quote='', strict_mode=false)
                WHERE TRY_CAST("OBSERVATION DATE" AS DATE) IS NOT NULL
                    AND TRY_CAST("LATITUDE" AS DOUBLE) IS NOT NULL
                    AND TRY_CAST("LONGITUDE" AS DOUBLE) IS NOT NULL
                    AND TRIM(COALESCE(CAST("SAMPLING EVENT IDENTIFIER" AS VARCHAR), '')) <> '';
                """,
                [dataset_key, str(request.sampling_path)],
            )
            inserted_events = count_rows(conn, NORMALIZED_EVENTS_TABLE) - before_events
            batches_flushed_events = math.ceil(inserted_events / request.batch_size) if inserted_events > 0 else 0

        if request.progress:
            _emit_progress("obs", rows_read_obs or inserted_obs, inserted_obs, batches_flushed_obs, request.start_time)
            if request.sampling_path is not None:
                _emit_progress(
                    "events",
                    rows_read_events or inserted_events,
                    inserted_events,
                    batches_flushed_events,
                    request.start_time,
                )

        if rows_read_obs and rows_read_obs > inserted_obs:
            logger.warning("Skipped %d observation rows during normalization", rows_read_obs - inserted_obs)
        if rows_read_events and rows_read_events > inserted_events:
            logger.warning("Skipped %d sampling rows during normalization", rows_read_events - inserted_events)

        return IngestStats(
            rows_read_obs=rows_read_obs,
            inserted_obs=inserted_obs,
            batches_flushed_obs=batches_flushed_obs,
            rows_read_events=rows_read_events,
            inserted_events=inserted_events,
            batches_flushed_events=batches_flushed_events,
        )

    def _ingest_with_python_parser(
        self,
        conn: duckdb.DuckDBPyConnection,
        dataset_key: str,
        request: IngestRequest,
    ) -> IngestStats:
        """Internal helper for ingest with python parser."""
        logger.warning("Using Python CSV parser fallback; this is slower than DuckDB-native ingestion")
        rows_read_obs = 0
        rows_read_events = 0
        inserted_obs = 0
        inserted_events = 0
        batches_flushed_obs = 0
        batches_flushed_events = 0

        obs_batch: list[NormalizedObservation] = []
        with request.obs_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            _check_required_columns(request.obs_path, set(reader.fieldnames or []), _OBS_REQUIRED_COLUMNS)

            for row in reader:
                rows_read_obs += 1

                observed_at = _parse_date(row.get("OBSERVATION DATE", ""))
                lat = _parse_float(row.get("LATITUDE", ""))
                lon = _parse_float(row.get("LONGITUDE", ""))
                event_id = (row.get("SAMPLING EVENT IDENTIFIER", "") or "").strip()
                taxon = (row.get("SCIENTIFIC NAME", "") or "").strip()

                if not observed_at or lat is None or lon is None or not event_id or not taxon:
                    if request.progress and rows_read_obs % request.progress_every == 0:
                        _emit_progress("obs", rows_read_obs, inserted_obs, batches_flushed_obs, request.start_time)
                    continue

                obs_batch.append(
                    NormalizedObservation(
                        dataset=dataset_key,
                        event_id=event_id,
                        observed_at=observed_at,
                        lat=lat,
                        lon=lon,
                        taxon=taxon,
                        count=_parse_int(row.get("OBSERVATION COUNT", "")),
                        is_complete=_parse_bool_10(row.get("ALL SPECIES REPORTED", "")),
                    )
                )

                if len(obs_batch) >= request.batch_size:
                    insert_normalized_observations(conn, obs_batch)
                    inserted_obs += len(obs_batch)
                    batches_flushed_obs += 1
                    obs_batch.clear()

                if request.progress and rows_read_obs % request.progress_every == 0:
                    _emit_progress("obs", rows_read_obs, inserted_obs, batches_flushed_obs, request.start_time)

        if obs_batch:
            insert_normalized_observations(conn, obs_batch)
            inserted_obs += len(obs_batch)
            batches_flushed_obs += 1

        if request.sampling_path is not None:
            events_batch: list[NormalizedEvent] = []
            with request.sampling_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f, delimiter="\t")
                _check_required_columns(
                    request.sampling_path,
                    set(reader.fieldnames or []),
                    _SAMPLING_REQUIRED_COLUMNS,
                )

                for row in reader:
                    rows_read_events += 1

                    observed_at = _parse_date(row.get("OBSERVATION DATE", ""))
                    lat = _parse_float(row.get("LATITUDE", ""))
                    lon = _parse_float(row.get("LONGITUDE", ""))
                    event_id = (row.get("SAMPLING EVENT IDENTIFIER", "") or "").strip()

                    if not observed_at or lat is None or lon is None or not event_id:
                        if request.progress and rows_read_events % request.progress_every == 0:
                            _emit_progress(
                                "events",
                                rows_read_events,
                                inserted_events,
                                batches_flushed_events,
                                request.start_time,
                            )
                        continue

                    events_batch.append(
                        NormalizedEvent(
                            dataset=dataset_key,
                            event_id=event_id,
                            observed_at=observed_at,
                            lat=lat,
                            lon=lon,
                            duration_minutes=_parse_float(row.get("DURATION MINUTES", "")),
                            distance_km=_parse_float(row.get("EFFORT DISTANCE KM", "")),
                            area_ha=_parse_float(row.get("EFFORT AREA HA", "")),
                            protocol=(row.get("PROTOCOL NAME", "") or "").strip() or None,
                            num_observers=_parse_int(row.get("NUMBER OBSERVERS", "")),
                            is_complete=_parse_bool_10(row.get("ALL SPECIES REPORTED", "")),
                        )
                    )

                    if len(events_batch) >= request.batch_size:
                        insert_normalized_events(conn, events_batch)
                        inserted_events += len(events_batch)
                        batches_flushed_events += 1
                        events_batch.clear()

                    if request.progress and rows_read_events % request.progress_every == 0:
                        _emit_progress(
                            "events",
                            rows_read_events,
                            inserted_events,
                            batches_flushed_events,
                            request.start_time,
                        )

            if events_batch:
                insert_normalized_events(conn, events_batch)
                inserted_events += len(events_batch)
                batches_flushed_events += 1

        if rows_read_obs > inserted_obs:
            logger.warning("Skipped %d observation rows during normalization", rows_read_obs - inserted_obs)
        if rows_read_events > inserted_events:
            logger.warning("Skipped %d sampling rows during normalization", rows_read_events - inserted_events)

        return IngestStats(
            rows_read_obs=rows_read_obs,
            inserted_obs=inserted_obs,
            batches_flushed_obs=batches_flushed_obs,
            rows_read_events=rows_read_events,
            inserted_events=inserted_events,
            batches_flushed_events=batches_flushed_events,
        )


def _parse_date(value: str) -> date | None:
    """Internal helper for parse date."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_float(value: str) -> float | None:
    """Internal helper for parse float."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: str) -> int | None:
    """Internal helper for parse int."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_bool_10(value: str) -> bool | None:
    """Internal helper for parse bool 10."""
    value = (value or "").strip()
    if value == "1":
        return True
    if value == "0":
        return False
    return None


def _check_required_columns(path: Path, found: set[str], required: set[str]) -> None:
    """Internal helper for check required columns."""
    missing = sorted(required - found)
    if missing:
        logger.error("Missing required columns in %s: %s", path, ", ".join(missing))
        raise typer.BadParameter(
            f"Missing required columns in {path}: {', '.join(missing)}",
            param_hint="--obs/--sampling",
        )


def _emit_progress(
    label: str,
    read_rows: int,
    inserted_rows: int,
    batches: int,
    start_time: float,
) -> None:
    """Internal helper for emit progress."""
    elapsed = max(time.time() - start_time, 1e-9)
    rate = read_rows / elapsed
    logger.info(
        "%s: read=%d, inserted=%d, batches=%d, rate=%.1f rows/s, elapsed=%.1fs",
        label,
        read_rows,
        inserted_rows,
        batches,
        rate,
        elapsed,
    )


def _read_csv_columns(conn: duckdb.DuckDBPyConnection, path: Path) -> set[str]:
    """Internal helper for read csv columns."""
    logger.info("Inspecting TSV columns: %s", path)
    rows = conn.execute(
        """
        DESCRIBE SELECT *
        FROM read_csv(?, delim='\t', header=true, quote='', strict_mode=false);
        """,
        [str(path)],
    ).fetchall()
    return {str(row[0]) for row in rows}


def _count_source_rows(conn: duckdb.DuckDBPyConnection, path: Path) -> int:
    """Internal helper for count source rows."""
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM read_csv(?, delim='\t', header=true, quote='', strict_mode=false);
            """,
            [str(path)],
        ).fetchone()[0]
    )


__all__ = ["EbirdIngestAdapter"]
