"""Tests for test_geodata_fetch_security."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from surface_mapper.geodata.fetch import fetch_and_unpack


def test_fetch_and_unpack_rejects_zip_traversal(tmp_path: Path) -> None:
    """Test fetch and unpack rejects zip traversal."""
    dest_dir = tmp_path / "geodata"
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dest_dir / "source.zip"
    outside_path = tmp_path / "escaped.txt"

    with ZipFile(archive_path, "w") as zf:
        zf.writestr("../escaped.txt", "owned")

    with pytest.raises(RuntimeError, match="Unsafe zip member path"):
        fetch_and_unpack(urls=["https://example.invalid/file.zip"], dest_dir=dest_dir, force=False)

    assert not outside_path.exists()
