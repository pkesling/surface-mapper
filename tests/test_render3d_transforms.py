import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from surface_mapper.render3d.transforms import transform_xy_gdf


def test_transform_xy_center_and_km_scale() -> None:
    square = Polygon(
        [
            (900.0, 1900.0),
            (1100.0, 1900.0),
            (1100.0, 2100.0),
            (900.0, 2100.0),
            (900.0, 1900.0),
        ]
    )
    gdf = gpd.GeoDataFrame([{"geometry": square}], crs="EPSG:5070")

    transformed = transform_xy_gdf(gdf, ox=1000.0, oy=2000.0, scale_factor=0.001)
    min_x, min_y, max_x, max_y = transformed.total_bounds

    assert min_x == pytest.approx(-0.1)
    assert max_x == pytest.approx(0.1)
    assert min_y == pytest.approx(-0.1)
    assert max_y == pytest.approx(0.1)
