"""surface_mapper.__init__ module."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("surface-mapper")
except PackageNotFoundError:
    # Fallback for source-only execution before installation.
    __version__ = "0.0.0+local"
