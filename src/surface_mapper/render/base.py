"""surface_mapper.render.base module."""

from __future__ import annotations

from abc import ABC, abstractmethod

from surface_mapper.render.contracts import RenderArtifacts, RenderSpec, SurfaceQuery


class Renderer(ABC):
    """Renderer."""

    @abstractmethod
    def render(self, query: SurfaceQuery, spec: RenderSpec) -> RenderArtifacts:
        """Render."""
        raise NotImplementedError
