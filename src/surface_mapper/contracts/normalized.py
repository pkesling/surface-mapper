"""surface_mapper.contracts.normalized module."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict

NORMALIZED_OBS_TABLE = "normalized_observations"
NORMALIZED_EVENTS_TABLE = "normalized_events"


class NormalizedObservation(BaseModel):
    """
    A single observation (e.g., a taxon observed during an event/checklist).
    This is dataset-agnostic and is the contract produced by ingest adapters.
    """
    model_config = ConfigDict(extra="allow")

    dataset: str = Field(..., description="Dataset identifier (e.g., 'ebird-ebd').")
    event_id: str = Field(..., description="Sampling event / checklist / visit identifier.")
    observed_at: date = Field(..., description="Observation date (or event date).")

    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

    taxon: str = Field(..., description="Taxon/species/category identifier (string).")
    count: Optional[int] = Field(None, ge=0, description="Observed count if numeric/known.")

    is_complete: Optional[bool] = Field(
        None,
        description="Whether the event/checklist is complete (if known)."
    )


class NormalizedEvent(BaseModel):
    """
    A single sampling event/checklist/visit.
    Useful for effort data, protocol, etc.
    """
    model_config = ConfigDict(extra="allow")

    dataset: str
    event_id: str
    observed_at: date

    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)

    # Effort/protocol metadata (optional, dataset-dependent)
    duration_minutes: Optional[float] = Field(None, ge=0)
    distance_km: Optional[float] = Field(None, ge=0)
    area_ha: Optional[float] = Field(None, ge=0)
    protocol: Optional[str] = None
    num_observers: Optional[int] = Field(None, ge=0)

    is_complete: Optional[bool] = None


__all__ = [
    "NORMALIZED_OBS_TABLE",
    "NORMALIZED_EVENTS_TABLE",
    "NormalizedObservation",
    "NormalizedEvent",
]
