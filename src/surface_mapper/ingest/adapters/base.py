from __future__ import annotations

from abc import ABC, abstractmethod

import duckdb

from surface_mapper.ingest.types import IngestRequest, IngestStats


class IngestAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique adapter identifier."""

    @property
    def aliases(self) -> tuple[str, ...]:
        return ()

    @abstractmethod
    def ingest(self, conn: duckdb.DuckDBPyConnection, request: IngestRequest) -> IngestStats:
        """Normalize source data into canonical tables."""


__all__ = ["IngestAdapter"]
