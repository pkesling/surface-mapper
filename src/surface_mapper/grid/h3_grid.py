from __future__ import annotations

import h3


def h3_cell(lat: float, lon: float, res: int) -> str:
    return h3.latlng_to_cell(lat, lon, res)


__all__ = ["h3_cell"]
