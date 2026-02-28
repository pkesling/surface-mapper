"""Tests for test_render_load_surface_security."""

from pathlib import Path

import duckdb
import pytest

from surface_mapper.render.contracts import SurfaceQuery
from surface_mapper.render.load_surface import load_surface


def test_load_surface_rejects_unsafe_table_identifier(tmp_path: Path) -> None:
    """Test load surface rejects unsafe table identifier."""
    db_path = tmp_path / "security.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.close()
    query = SurfaceQuery(
        db_path=str(db_path),
        table="surface_cells; DROP TABLE surface_cells;--",
    )

    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        load_surface(query)
