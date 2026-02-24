from __future__ import annotations

from datetime import date
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict


GridType = Literal["h3"]  # future: "geohash", "s2", ...


class SurfaceCell(BaseModel):
    """
    One row in a surface table: a metric value over a spatial cell.
    """
    model_config = ConfigDict(extra="allow")

    dataset: str = Field(..., description="Dataset identifier (e.g., 'ebird-ebd').")
    grid: GridType = Field("h3", description="Grid backend used for cell_id.")
    resolution: int = Field(..., ge=0, description="Grid resolution (e.g., H3 res).")

    cell_id: str = Field(..., description="Cell identifier (e.g., H3 index string).")

    metric: str = Field(..., description="Metric name (attention, richness, etc.).")
    value: float = Field(..., description="Metric value for the cell.")
    support: Optional[float] = Field(
        None,
        description="Optional support size (e.g., checklist_count). Helps interpret confidence."
    )

    time_slice: Optional[str] = Field(
        None,
        description="Optional time grouping label (winter/spring/summer/fall, month, etc.)."
    )

    start_date: Optional[date] = None
    end_date: Optional[date] = None


SURFACE_TABLE_DEFAULT = "surface_cells"

__all__ = [
    "SURFACE_TABLE_DEFAULT",
    "GridType",
    "SurfaceCell",
]
