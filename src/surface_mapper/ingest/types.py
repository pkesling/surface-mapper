"""surface_mapper.ingest.types module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IngestRequest:
    """IngestRequest."""
    dataset: str
    obs_path: Path
    sampling_path: Path | None
    batch_size: int
    progress: bool
    progress_every: int
    python_parser: bool
    start_time: float


@dataclass(frozen=True)
class IngestStats:
    """IngestStats."""
    rows_read_obs: int
    inserted_obs: int
    batches_flushed_obs: int
    rows_read_events: int
    inserted_events: int
    batches_flushed_events: int
