from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from terrain_worker.analysis import cell_rows, load_dem, sightline


def test_windowed_derivatives_match_analytic_plane_and_nodata(tmp_path: Path) -> None:
    r, c = np.indices((5, 5000))
    data = (2 * r + 3 * c).astype("float32")
    data[2, 4096] = -9999
    path = tmp_path / "plane.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=5000,
        height=5,
        count=1,
        dtype="float32",
        crs="EPSG:32618",
        transform=from_origin(0, 20, 2, 4),
        nodata=-9999,
    ) as dst:
        dst.write(data, 1)
    result = []
    offset = 0
    with rasterio.open(path) as ds:
        while offset < data.size:
            rows, offset = cell_rows(ds, offset, data.size)
            assert 0 < len(rows) <= 4096
            result.extend(rows)
    assert [v["cell_id"] for v in result] == list(range(data.size))
    expected_slope = np.degrees(np.arctan(np.hypot(1.5, 0.5)))
    expected_aspect = np.degrees(np.arctan2(-1.5, 0.5)) % 360
    for idx in [0, 4095, 4096, 4999, 5000, 14999, 24999]:
        assert result[idx]["slope_deg"] == pytest.approx(expected_slope)
        assert result[idx]["aspect_deg"] == pytest.approx(expected_aspect)
    assert result[14096]["elevation_m"] is None
    assert result[14096]["slope_deg"] is None
    assert result[14095]["slope_deg"] is None


def test_dem_scale_offset_and_vertical_units(tmp_path: Path) -> None:
    path = tmp_path / "encoded.tif"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=2,
        height=2,
        count=1,
        dtype="int16",
        crs="EPSG:32618",
        transform=from_origin(0, 20, 10, 10),
        nodata=-9999,
    ) as dst:
        dst.write(np.array([[0, 20], [-9999, 40]], dtype="int16"), 1)
        dst.scales, dst.offsets = (0.5,), (100.0,)
        dst.set_band_unit(1, "m")
    data, _, _ = load_dem(str(path), 4)
    assert data[0].tolist() == [100.0, 110.0]
    assert np.isnan(data[1, 0])
    assert data[1, 1] == 120
    with rasterio.open(path, "r+") as dst:
        dst.set_band_unit(1, "ft")
    with pytest.raises(ValueError, match="vertical units"):
        load_dem(str(path), 4)


def args(**updates: Any) -> SimpleNamespace:
    return SimpleNamespace(
        **{"input_crs": "EPSG:32618", "step_m": 5.0, "max_samples": 200000, "refraction_k": 7 / 6, **updates}
    )


def pair(**updates: Any) -> Any:
    return {
        "pair_id": "a",
        "source_x": 500015.0,
        "source_y": 4100055.0,
        "target_x": 500095.0,
        "target_y": 4100055.0,
        "source_height_m": 2.0,
        "target_height_m": 2.0,
        **updates,
    }


def test_ridge_blocks_low_tower_but_not_high_tower() -> None:
    data, transform, crs = load_dem("demo://ridge.tif", 1000)
    low = sightline(pair(), data, transform, crs, args())
    high = sightline(pair(source_height_m=80.0), data, transform, crs, args())
    assert low["visible"] is False
    assert low["distance_m"] == 80
    assert low["min_clearance_m"] == pytest.approx(-28, abs=0.001)
    assert 500050 <= low["obstruction_x"] < 500060
    assert high["visible"] is True
    assert high["obstruction_x"] is None


def test_missing_elevation_never_becomes_clear() -> None:
    data, transform, crs = load_dem("demo://ridge.tif", 1000)
    data[5, 5] = np.nan
    result = sightline(pair(source_height_m=80), data, transform, crs, args())
    assert result["visible"] is None
    assert result["status"] == "nodata"


def test_outside_dem_and_negative_height() -> None:
    data, transform, crs = load_dem("demo://ridge.tif", 1000)
    assert sightline(pair(target_x=499995), data, transform, crs, args())["status"] == "outside_dem"
    with pytest.raises(ValueError, match="nonnegative"):
        sightline(pair(source_height_m=-1), data, transform, crs, args())


def test_reprojected_endpoints_have_same_result() -> None:
    data, transform, crs = load_dem("demo://ridge.tif", 1000)
    p = Transformer.from_crs(32618, 4326, always_xy=True)
    sx, sy = p.transform(500015, 4100055)
    tx, ty = p.transform(500095, 4100055)
    result = sightline(
        pair(source_x=sx, source_y=sy, target_x=tx, target_y=ty), data, transform, crs, args(input_crs="EPSG:4326")
    )
    assert result["visible"] is False
    assert result["distance_m"] == pytest.approx(80, abs=1e-6)


def test_resource_limits_and_nulls_are_enforced() -> None:
    with pytest.raises(ValueError, match="max_cells"):
        load_dem("demo://ridge.tif", 10)
    data, transform, crs = load_dem("demo://ridge.tif", 1000)
    with pytest.raises(ValueError, match="max_samples"):
        sightline(pair(), data, transform, crs, args(max_samples=3))
    with pytest.raises(ValueError, match="numbers"):
        sightline(pair(source_x=None), data, transform, crs, args())


def test_identical_endpoints_and_flat_terrain() -> None:
    data, transform, crs = load_dem("demo://ridge.tif", 1000)
    data[:] = 100
    result = sightline(pair(target_x=500015), data, transform, crs, args())
    assert result["visible"] is True
    assert result["distance_m"] == 0
    assert result["min_clearance_m"] == 2
