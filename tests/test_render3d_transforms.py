import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Polygon

from surface_mapper.render3d.transforms import TARGET_XY_SIZE, normalize_xy_points, transform_xy_gdf


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


def test_normalize_xy_points_scales_max_extent_to_target() -> None:
    points = np.array(
        [
            [10.0, -3.0, 0.0],
            [16.0, 9.0, 1.0],
            [22.0, 2.0, 2.0],
        ],
        dtype=float,
    )
    normalized, xy_scale = normalize_xy_points(points, target_size=TARGET_XY_SIZE, enabled=True)

    x_extent = float(np.max(normalized[:, 0]) - np.min(normalized[:, 0]))
    y_extent = float(np.max(normalized[:, 1]) - np.min(normalized[:, 1]))

    assert max(x_extent, y_extent) == pytest.approx(TARGET_XY_SIZE)
    assert normalized[:, 2].tolist() == pytest.approx(points[:, 2].tolist())
    assert xy_scale == pytest.approx(TARGET_XY_SIZE / 12.0)


def test_normalize_xy_points_disabled_keeps_extents_unchanged() -> None:
    points = np.array(
        [
            [1.0, 2.0, 0.0],
            [4.0, 10.0, 1.0],
            [3.0, 7.0, 2.0],
        ],
        dtype=float,
    )
    unchanged, xy_scale = normalize_xy_points(points, target_size=TARGET_XY_SIZE, enabled=False)

    assert np.allclose(unchanged, points)
    assert xy_scale == pytest.approx(1.0)
