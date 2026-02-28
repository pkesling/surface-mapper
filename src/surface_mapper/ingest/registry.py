"""surface_mapper.ingest.registry module."""

from __future__ import annotations

import logging
from functools import lru_cache
from importlib.metadata import entry_points

from surface_mapper.ingest.adapters.base import IngestAdapter
from surface_mapper.ingest.adapters.ebird import EbirdIngestAdapter

logger = logging.getLogger("surface_mapper.ingest.registry")

_ENTRYPOINT_GROUP = "surface_mapper.ingest_adapters"


def _iter_builtin_adapters() -> list[IngestAdapter]:
    """Internal helper for iter builtin adapters."""
    return [EbirdIngestAdapter()]


def _iter_plugin_adapters() -> list[IngestAdapter]:
    """Internal helper for iter plugin adapters."""
    adapters: list[IngestAdapter] = []
    for ep in entry_points(group=_ENTRYPOINT_GROUP):
        try:
            loaded = ep.load()
        except Exception:
            logger.exception("Failed to load ingest adapter entry point '%s'", ep.name)
            continue

        try:
            adapter = loaded() if isinstance(loaded, type) else loaded
        except Exception:
            logger.exception("Failed to instantiate ingest adapter entry point '%s'", ep.name)
            continue

        if not isinstance(adapter, IngestAdapter):
            logger.error(
                "Ignoring ingest adapter '%s': expected IngestAdapter, got %s",
                ep.name,
                type(adapter).__name__,
            )
            continue

        adapters.append(adapter)
    return adapters


@lru_cache(maxsize=1)
def get_adapter_index() -> dict[str, IngestAdapter]:
    """Get adapter index."""
    index: dict[str, IngestAdapter] = {}

    def register_key(key: str, adapter: IngestAdapter) -> None:
        if key in index:
            logger.warning("Adapter key '%s' already registered; keeping first adapter", key)
            return
        index[key] = adapter

    for adapter in [*_iter_builtin_adapters(), *_iter_plugin_adapters()]:
        register_key(adapter.name, adapter)
        for alias in adapter.aliases:
            register_key(alias, adapter)

    return index


def resolve_adapter(name: str) -> IngestAdapter:
    """Resolve adapter."""
    index = get_adapter_index()
    try:
        return index[name]
    except KeyError as exc:
        supported = ", ".join(sorted(index))
        raise KeyError(f"Unsupported adapter '{name}'. Available adapters: {supported}") from exc


def list_adapters() -> list[str]:
    """List adapters."""
    return sorted(get_adapter_index())


__all__ = ["resolve_adapter", "list_adapters", "get_adapter_index"]
