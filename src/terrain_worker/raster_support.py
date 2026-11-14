"""Bounded raster I/O and metadata checks for metric GIS analysis."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import numpy as np
import rasterio

from .support import resource


@contextmanager
def open_raster(path: str) -> Iterator[Any]:
    """Keep GDAL remote reads and retries bounded and close datasets reliably."""
    with (
        rasterio.Env(
            GDAL_HTTP_TIMEOUT=30,
            GDAL_HTTP_CONNECTTIMEOUT=10,
            GDAL_HTTP_MAX_RETRY=2,
            GDAL_HTTP_RETRY_DELAY=1,
            GDAL_CACHEMAX=64 * 1024 * 1024,
        ),
        rasterio.open(resource(path)) as dataset,
    ):
        yield dataset


def north_up(dataset: Any, *, max_cells: int | None = None, min_size: int = 1) -> None:
    """Reject grids whose dimensions or affine transform violate the analysis contract."""
    t = dataset.transform
    if max_cells is not None and dataset.width * dataset.height > max_cells:
        raise ValueError(f"Raster exceeds max_cells={max_cells}; provide a bounded region")
    if dataset.width < min_size or dataset.height < min_size:
        raise ValueError(f"Raster must be at least {min_size} by {min_size} cells")
    if not np.isfinite(tuple(t)).all() or t.a <= 0 or t.e >= 0 or t.b != 0 or t.d != 0:
        raise ValueError("Raster must be a finite north-up grid")


def elevation(dataset: Any, *, window: Any = None) -> Any:
    """Apply band scale/offset while retaining nodata and requiring metre elevations."""
    units = (dataset.units[0] or "").lower().strip()
    if units not in {"", "m", "metre", "metres", "meter", "meters"}:
        raise ValueError("DEM vertical units must be metres; convert the elevation band first")
    scale, offset = dataset.scales[0], dataset.offsets[0]
    if not np.isfinite([scale, offset]).all() or scale == 0:
        raise ValueError("DEM scale must be finite and nonzero and its offset finite")
    data = dataset.read(1, window=window, masked=True).astype("float64").filled(np.nan)
    data = data * scale + offset
    data[~np.isfinite(data)] = np.nan
    return data
