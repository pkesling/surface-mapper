"""surface_mapper.ingest.adapters.__init__ module."""

from surface_mapper.ingest.adapters.base import IngestAdapter
from surface_mapper.ingest.adapters.ebird import EbirdIngestAdapter

__all__ = ["IngestAdapter", "EbirdIngestAdapter"]
