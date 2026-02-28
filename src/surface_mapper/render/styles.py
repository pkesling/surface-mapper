"""surface_mapper.render.styles module."""

from __future__ import annotations

from matplotlib import colormaps
from matplotlib.colors import Colormap


def get_cmap(
    style: str,
    metric: str,
    colormap: str | None = None,
    diverging_colormap: str | None = None,
) -> Colormap:
    """Get cmap."""
    if colormap:
        return colormaps[colormap]

    if diverging_colormap and "residual" in metric:
        return colormaps[diverging_colormap]

    if style == "classic":
        return colormaps["viridis"]
    if style == "neon":
        return colormaps["turbo"]
    raise ValueError(f"Unsupported style: {style}")
