from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DefaultDataset:
    name: str
    urls: tuple[str, ...]
    expected_basename: str


DEFAULT_STATES = DefaultDataset(
    name="states",
    # Choose a map from the "States" collection at https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html
    urls=("https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_5m.zip",),
    expected_basename="cb_2024_us_state_5m",
)

DEFAULT_LAKES = DefaultDataset(
    name="lakes",
    urls=(
        "https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip",
        # Keep these only as fallbacks; they can be brittle / 404.
        "https://www.naturalearthdata.com/http//www.naturalearthdata.com/download/10m/physical/ne_10m_lakes.zip",
        "https://www.naturalearthdata.com/download/10m/physical/ne_10m_lakes.zip",
    ),
    expected_basename="ne_10m_lakes",
)

DEFAULT_DATASETS: tuple[DefaultDataset, ...] = (
    DEFAULT_STATES,
    DEFAULT_LAKES,
)

DEFAULT_STATE_NEIGHBORS: dict[str, tuple[str, ...]] = {
    "WI": ("MN", "IA", "IL", "MI"),
}

__all__ = [
    "DefaultDataset",
    "DEFAULT_STATES",
    "DEFAULT_LAKES",
    "DEFAULT_DATASETS",
    "DEFAULT_STATE_NEIGHBORS",
]
