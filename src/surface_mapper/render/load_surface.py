from __future__ import annotations

import duckdb
import pandas as pd

from surface_mapper.render.contracts import SurfaceQuery


def load_surface(query: SurfaceQuery) -> pd.DataFrame:
    conn = duckdb.connect(query.db_path, read_only=True)
    try:
        params: list[object] = [query.dataset, query.grid, query.resolution, query.metric]
        where_parts = [
            "dataset = ?",
            "grid = ?",
            "resolution = ?",
            "metric = ?",
        ]

        if query.time_slice is None:
            where_parts.append("time_slice IS NULL")
        else:
            where_parts.append("time_slice = ?")
            params.append(query.time_slice)

        if query.min_support is not None:
            where_parts.append("support >= ?")
            params.append(query.min_support)

        sql = (
            f"SELECT cell_id, value, support, time_slice "
            f"FROM {query.table} "
            f"WHERE {' AND '.join(where_parts)}"
        )
        return conn.execute(sql, params).df()
    finally:
        conn.close()
