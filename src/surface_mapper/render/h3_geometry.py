from __future__ import annotations

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Polygon


def h3_to_polygon(cell_id: str) -> Polygon:
    boundary = h3.cell_to_boundary(cell_id)
    coords = [(float(lon), float(lat)) for lat, lon in boundary]
    return Polygon(coords)


def h3_df_to_gdf(df: pd.DataFrame, crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    work = df.copy()
    work["geometry"] = work["cell_id"].map(h3_to_polygon)
    return gpd.GeoDataFrame(work, geometry="geometry", crs=crs)
