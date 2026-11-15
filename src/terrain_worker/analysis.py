"""DEM-based sight lines and terrain cells, exposed as relational VGI functions."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar

import numpy as np
import pyarrow as pa
from pyproj import Transformer
from rasterio.windows import Window
from shapely.geometry import LineString
from vgi import Arg
from vgi.arguments import TableInput
from vgi.catalog import Table
from vgi.catalog.constraints import constraint_record
from vgi.invocation import BindResponse
from vgi.table_function import (
    BindParams,
    OutputCollector,
    ProcessParams,
    TableFunctionGenerator,
    bind_fixed_schema,
    init_single_worker,
)
from vgi.table_in_out_function import TableInOutGenerator
from vgi_rpc import ArrowSerializableDataclass

from .raster_support import elevation, north_up, open_raster
from .support import (
    example,
    finite_parameters,
    identifier,
    metadata,
    metric_crs,
    numeric,
    require_columns,
    schema_of,
)

GIS_DESCRIPTION = (
    "Evaluate terrain visibility between query-supplied tower/building pairs and "
    "inspect DEM elevation, slope and aspect. "
    "Distances and heights are metres. Input coordinates have an explicit CRS; DEMs "
    "must be projected in metres. "
    "Missing terrain yields unknown visibility. Synthetic sample assets ship in the wheel. "
    "The main schema exposes visibility, dem_cells and the ridge_tower_pairs sample table."
)

INPUT_SCHEMA = schema_of(
    [
        ("pair_id", pa.string(), "Caller-owned identity for a tower/building pair."),
        ("source_x", pa.float64(), "Tower X in input_crs."),
        ("source_y", pa.float64(), "Tower Y in input_crs."),
        ("target_x", pa.float64(), "Building X in input_crs."),
        ("target_y", pa.float64(), "Building Y in input_crs."),
        ("source_height_m", pa.float64(), "Tower height above DEM surface, metres."),
        ("target_height_m", pa.float64(), "Receiver height above DEM surface, metres."),
    ]
)
RESULT = schema_of(
    [
        ("pair_id", pa.string(), "Input pair identity, suitable for joining to towers and buildings."),
        ("visible", pa.bool_(), "True if all sampled terrain clears the sight line; NULL if coverage is unknown."),
        ("distance_m", pa.float64(), "Horizontal distance in the projected DEM CRS, metres."),
        ("min_clearance_m", pa.float64(), "Smallest interior sight-line clearance above terrain, metres."),
        ("obstruction_x", pa.float64(), "Worst obstruction X in dem_crs, only when blocked."),
        ("obstruction_y", pa.float64(), "Worst obstruction Y in dem_crs, only when blocked."),
        ("sample_count", pa.int64(), "Number of elevation samples used along this sight line."),
        ("status", pa.string(), "visible, blocked, outside_dem, or nodata; unknown terrain is never reported clear."),
        (
            "sightline_wkb",
            pa.binary(),
            "3D WKB sight line with absolute endpoint elevations; NULL without terrain coverage.",
        ),
        ("dem_crs", pa.string(), "Horizontal coordinate reference system of the output geometry and obstruction."),
    ]
)
CELLS = schema_of(
    [
        ("cell_id", pa.int64(), "Row-major DEM cell index."),
        ("x", pa.float64(), "Cell centre X in dem_crs."),
        ("y", pa.float64(), "Cell centre Y in dem_crs."),
        ("elevation_m", pa.float64(), "Elevation in metres; NULL for nodata."),
        (
            "slope_deg",
            pa.float64(),
            "Slope from finite differences in degrees; NULL where neighbouring data are missing.",
        ),
        ("aspect_deg", pa.float64(), "Downhill azimuth clockwise from north; NULL on flat or unknown terrain."),
        ("dem_crs", pa.string(), "Projected horizontal CRS, with metre units."),
    ]
)


def load_dem(path: str, max_cells: int) -> tuple[Any, Any, Any]:
    """Read a bounded metre-based DEM and preserve missing cells as NaN."""
    with open_raster(path) as ds:
        crs = metric_crs(ds.crs)
        north_up(ds, max_cells=max_cells, min_size=2)
        return elevation(ds), ds.transform, crs


def cell_rows(ds: Any, offset: int, max_cells: int) -> tuple[list[dict[str, Any]], int]:
    """Read only a batch window plus derivative halo; retain global cell identities."""
    crs = metric_crs(ds.crs)
    north_up(ds, max_cells=max_cells, min_size=2)
    if offset >= ds.width * ds.height:
        return [], offset
    row_start, col_start = divmod(offset, ds.width)
    stop = min(offset + 4096, ds.width * ds.height)
    # Wide grids stay within one partial row so a small batch never reads the full raster.
    if ds.width > 4096:
        stop = min(stop, (row_start + 1) * ds.width)
    row_end, col_end = divmod(stop - 1, ds.width)
    left = max(0, col_start - 1) if row_start == row_end else 0
    right = min(ds.width, col_end + 2) if row_start == row_end else ds.width
    top, bottom = max(0, row_start - 1), min(ds.height, row_end + 2)
    data = elevation(ds, window=Window(left, top, right - left, bottom - top))
    dy, dx = np.gradient(data, abs(ds.transform.e), ds.transform.a)
    slopes = np.degrees(np.arctan(np.hypot(dx, dy)))
    aspects = np.degrees(np.arctan2(-dx, dy)) % 360
    slopes[~np.isfinite(data)] = np.nan
    aspects[~np.isfinite(data)] = np.nan
    result = []
    for idx in range(offset, stop):
        r, c = divmod(idx, ds.width)
        x = ds.transform.c + (c + 0.5) * ds.transform.a
        y = ds.transform.f + (r + 0.5) * ds.transform.e
        rr, cc = r - top, c - left
        value, slope, aspect = float(data[rr, cc]), float(slopes[rr, cc]), float(aspects[rr, cc])
        result.append(
            {
                "cell_id": idx,
                "x": x,
                "y": y,
                "elevation_m": value if math.isfinite(value) else None,
                "slope_deg": slope if math.isfinite(slope) else None,
                "aspect_deg": aspect if math.isfinite(aspect) and slope > 0 else None,
                "dem_crs": crs.to_string(),
            }
        )
    return result, stop


def sightline(row: dict[str, Any], data: Any, transform: Any, crs: Any, args: Any) -> dict[str, Any]:
    """Sample a sight line at half-cell spacing or finer, including curvature."""
    key = identifier(row, "pair_id")
    sx, sy, tx, ty, sh, th = numeric(
        row, "source_x", "source_y", "target_x", "target_y", "source_height_m", "target_height_m"
    )
    if sh < 0 or th < 0:
        raise ValueError("Endpoint heights above terrain must be nonnegative")
    project = Transformer.from_crs(args.input_crs, crs, always_xy=True)
    sx, sy = project.transform(sx, sy)
    tx, ty = project.transform(tx, ty)
    if not np.isfinite([sx, sy, tx, ty]).all():
        raise ValueError("Coordinates cannot be transformed to DEM CRS")
    distance = math.hypot(tx - sx, ty - sy)
    spacing = min(args.step_m, transform.a / 2, abs(transform.e) / 2)
    count = max(3, math.ceil(distance / spacing) + 1)
    if count > args.max_samples:
        raise ValueError("Sight line exceeds max_samples; increase the explicit limit")
    t = np.linspace(0, 1, count)
    xs, ys = sx + t * (tx - sx), sy + t * (ty - sy)
    cols = np.floor((xs - transform.c) / transform.a).astype(int)
    rows = np.floor((ys - transform.f) / transform.e).astype(int)
    result = {
        "pair_id": key,
        "visible": None,
        "distance_m": distance,
        "min_clearance_m": None,
        "obstruction_x": None,
        "obstruction_y": None,
        "sample_count": count,
        "status": "outside_dem",
        "sightline_wkb": None,
        "dem_crs": crs.to_string(),
    }
    if np.any((cols < 0) | (rows < 0) | (cols >= data.shape[1]) | (rows >= data.shape[0])):
        return result
    heights = data[rows, cols]
    if not np.isfinite(heights).all():
        result["status"] = "nodata"
        return result
    z0, z1 = float(heights[0] + sh), float(heights[-1] + th)
    curvature = t * (1 - t) * distance**2 / (2 * args.refraction_k * 6371008.8)
    clearance = z0 + t * (z1 - z0) - heights - curvature
    worst = int(np.argmin(clearance[1:-1])) + 1
    minimum = float(clearance[worst])
    visible = minimum >= -1e-9
    result.update(
        visible=visible,
        min_clearance_m=minimum,
        status="visible" if visible else "blocked",
        obstruction_x=None if visible else float(xs[worst]),
        obstruction_y=None if visible else float(ys[worst]),
        sightline_wkb=LineString([(sx, sy, z0), (tx, ty, z1)]).wkb,
    )
    return result


@dataclass(slots=True, frozen=True, kw_only=True)
class VisibilityArgs:
    """Relational endpoint pairs and explicit DEM sampling controls."""

    data: Annotated[
        TableInput, Arg(0, doc="Rows with pair_id, source_x/y, target_x/y, source_height_m and target_height_m.")
    ]
    dem: Annotated[
        str,
        Arg(
            "dem",
            default="demo://ridge.tif",
            doc="DEM GeoTIFF path or GDAL-supported URL; elevation units must be metres.",
        ),
    ]
    input_crs: Annotated[
        str, Arg("input_crs", default="EPSG:32618", doc="CRS for endpoint XY coordinates; always XY axis order.")
    ]
    step_m: Annotated[
        float,
        Arg(
            "step_m",
            default=5.0,
            gt=0,
            doc="Maximum sample spacing in metres, capped to half the smaller DEM cell size.",
        ),
    ]
    refraction_k: Annotated[
        float,
        Arg(
            "refraction_k",
            default=1.1666666667,
            gt=0,
            doc="Effective Earth radius factor for terrain curvature; 7/6 is the default.",
        ),
    ]
    max_cells: Annotated[
        int,
        Arg(
            "max_cells",
            default=2000000,
            ge=4,
            doc="Maximum loaded DEM cells; rejects larger rasters instead of silently truncating.",
        ),
    ]
    max_samples: Annotated[
        int, Arg("max_samples", default=200000, ge=3, doc="Maximum samples per sight line; excess raises an error.")
    ]


VIS_SQL = (
    "SELECT pair_id, visible, status FROM terrain.main.visibility((SELECT * FROM "
    "terrain.main.ridge_tower_pairs)) ORDER BY pair_id"
)


# Composed examples: each combines two or more of this worker's objects in one query.
VIEWSHED_PER_TOWER_SQL = (
    "SELECT split_part(v.pair_id, ':', 1) AS tower, count(*) FILTER (WHERE v.visible) AS visible_cells, "
    "count(*) FILTER (WHERE NOT v.visible) AS blocked_cells "
    "FROM terrain.main.visibility((SELECT t.pair_id || ':' || c.cell_id AS pair_id, t.source_x, t.source_y, "
    "c.x AS target_x, c.y AS target_y, t.source_height_m, 2.0 AS target_height_m "
    "FROM terrain.main.ridge_tower_pairs AS t CROSS JOIN terrain.main.dem_cells('demo://ridge.tif') AS c)) AS v "
    "GROUP BY tower ORDER BY tower"
)
VIEWSHED_PER_TOWER_DESCRIPTION = (
    "Viewshed per tower: cross join each ridge_tower_pairs tower with every dem_cells cell centre, run visibility "
    "on the 242 sight lines, and count visible vs blocked cells (80 m tower 99/22, 2 m tower 55/66 of 121)"
)
VIEWSHED_PER_TOWER_EXPECTED: list[list[Any]] = [["high", 99, 22], ["low", 55, 66]]

OBSTRUCTION_CELL_SQL = (
    "SELECT v.pair_id, round(v.min_clearance_m, 2) AS min_clearance_m, c.cell_id, c.x, c.y, c.elevation_m "
    "FROM terrain.main.visibility((SELECT * FROM terrain.main.ridge_tower_pairs)) AS v "
    "CROSS JOIN terrain.main.dem_cells('demo://ridge.tif') AS c WHERE v.status = 'blocked' "
    "QUALIFY row_number() OVER (PARTITION BY v.pair_id "
    "ORDER BY (c.x - v.obstruction_x) ^ 2 + (c.y - v.obstruction_y) ^ 2, c.cell_id) = 1 ORDER BY v.pair_id"
)
OBSTRUCTION_CELL_DESCRIPTION = (
    "Locate what blocks each blocked pair: snap the visibility obstruction point to the nearest dem_cells "
    "cell centre (the 2 m tower's line passes 28 m under the 30 m ridge crest cell 60)"
)

HEIGHT_SWEEP_SQL = (
    "WITH candidates AS (SELECT 'low@' || h.height_m AS pair_id, h.height_m, d.source_x, d.source_y, "
    "d.target_x, d.target_y, h.height_m::DOUBLE AS source_height_m, d.target_height_m "
    "FROM terrain.main.ridge_tower_pairs AS d CROSS JOIN range(40, 75, 5) AS h(height_m) WHERE d.pair_id = 'low') "
    "SELECT c.height_m, v.status, round(v.min_clearance_m, 2) AS min_clearance_m "
    "FROM terrain.main.visibility((SELECT * FROM candidates)) AS v JOIN candidates AS c USING (pair_id) "
    "ORDER BY c.height_m"
)
HEIGHT_SWEEP_DESCRIPTION = (
    "Tower height sweep: re-run the ridge_tower_pairs 'low' pair through visibility at heights 40-70 m in 5 m "
    "steps; heights up to 55 m are blocked by the ridge and 60 m is the first that clears it (+1.0 m)"
)


class Visibility(TableInOutGenerator[VisibilityArgs]):
    """Return one visibility assessment per input pair."""

    class Meta:
        """Discoverable visibility semantics and known ridge example."""

        name = "visibility"
        description = "Assess terrain obstruction between tower and building pairs"
        tags = metadata(
            "Terrain visibility",
            GIS_DESCRIPTION
            + (
                " Heights are above the DEM surface. This is sampled terrain visibility, not a "
                "radio propagation model. Nodata produces NULL visible; invalid inputs fail."
            ),
            RESULT,
            VIS_SQL,
            [["high", True, "visible"], ["low", False, "blocked"]],
            composed=[(VIEWSHED_PER_TOWER_DESCRIPTION, VIEWSHED_PER_TOWER_SQL, VIEWSHED_PER_TOWER_EXPECTED)],
        )
        examples = [
            *example(VIS_SQL, "A tall tower clears the ridge; a low tower is blocked"),
            *example(VIEWSHED_PER_TOWER_SQL, VIEWSHED_PER_TOWER_DESCRIPTION),
            *example(OBSTRUCTION_CELL_SQL, OBSTRUCTION_CELL_DESCRIPTION),
            *example(HEIGHT_SWEEP_SQL, HEIGHT_SWEEP_DESCRIPTION),
        ]

    @classmethod
    def on_bind(cls, params: BindParams[VisibilityArgs]) -> BindResponse:
        """Validate endpoint columns before execution."""
        finite_parameters(params.args)
        require_columns(params.bind_call.input_schema, tuple(INPUT_SCHEMA.names))
        return BindResponse(output_schema=RESULT)

    @classmethod
    def process(
        cls, params: ProcessParams[VisibilityArgs], state: None, batch: pa.RecordBatch, out: OutputCollector
    ) -> None:
        """Amortize one DEM load across every endpoint pair in the Arrow batch."""
        data, transform, crs = load_dem(params.args.dem, params.args.max_cells)
        rows = [sightline(row, data, transform, crs, params.args) for row in batch.to_pylist()]
        out.emit(pa.RecordBatch.from_pylist(rows, schema=params.output_schema))


@dataclass(slots=True, frozen=True, kw_only=True)
class CellsArgs:
    """A bounded DEM to expose as cell rows."""

    dem: Annotated[
        str, Arg(0, doc="North-up DEM GeoTIFF path or URL, with projected metre coordinates and metre elevations.")
    ]
    max_cells: Annotated[int, Arg("max_cells", default=2000000, ge=4, doc="Maximum number of DEM cells to read.")]


@dataclass(kw_only=True)
class Cursor(ArrowSerializableDataclass):
    """Serializable row cursor for stateless transport calls."""

    offset: int = 0


CELL_SQL = "SELECT count(*), max(elevation_m) FROM terrain.main.dem_cells('demo://ridge.tif')"


@init_single_worker
@bind_fixed_schema
class DemCells(TableFunctionGenerator[CellsArgs, Cursor]):
    """Expose terrain surfaces and target locations for SQL viewshed queries."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = CELLS

    class Meta:
        """DEM cell documentation."""

        name = "dem_cells"
        description = "Read DEM cell centres, elevation, slope and aspect"
        tags = metadata(
            "DEM cells and surfaces",
            "Read north-up projected metre DEM cells as rows. Nodata becomes NULL; "
            "finite-difference slope and aspect are NULL where neighbours are missing. Flat "
            "cells have NULL aspect. Cross join cells to observer locations and pass the "
            "endpoint pairs to visibility for a sampled viewshed. max_cells bounds memory. "
            "Elevations must be metres.",
            CELLS,
            CELL_SQL,
            [[121, 30.0]],
        )
        examples = example(CELL_SQL, "Count cells and find the ridge elevation")

    @classmethod
    def initial_state(cls, params: ProcessParams[CellsArgs]) -> Cursor:
        """Start at the first cell."""
        return Cursor()

    @classmethod
    def process(cls, params: ProcessParams[CellsArgs], state: Cursor, out: OutputCollector) -> None:
        """Emit cell rows in bounded batches."""
        with open_raster(params.args.dem) as ds:
            rows, state.offset = cell_rows(ds, state.offset, params.args.max_cells)
        if not rows:
            out.finish()
            return
        out.emit(pa.RecordBatch.from_pylist(rows, schema=params.output_schema))


@dataclass(slots=True, frozen=True, kw_only=True)
class SamplePairsArgs:
    """No arguments: return the bundled tower/building pairs."""


SAMPLE_PAIRS_SQL = "SELECT pair_id, source_height_m FROM terrain.main.ridge_tower_pairs ORDER BY pair_id"


@init_single_worker
@bind_fixed_schema
class RidgeTowerPairs(TableFunctionGenerator[SamplePairsArgs, Cursor]):
    """Return two reproducible observer/target pairs across a synthetic ridge."""

    FIXED_SCHEMA: ClassVar[pa.Schema] = INPUT_SCHEMA

    class Meta:
        """Bundled sample input metadata."""

        name = "ridge_tower_pairs"
        description = "Two tower/building pairs across a synthetic 30 metre ridge"
        tags = metadata(
            "Sample tower/building pairs",
            "Two synthetic pairs in EPSG:32618 for demo://ridge.tif: high has an 80 m tower and"
            " low has a 2 m tower. Both receivers are 2 m above ground. No network or "
            "credentials are needed.",
            INPUT_SCHEMA,
            SAMPLE_PAIRS_SQL,
            [["high", 80.0], ["low", 2.0]],
        )
        examples = example(SAMPLE_PAIRS_SQL, "Inspect the two tower heights")

    @classmethod
    def initial_state(cls, params: ProcessParams[SamplePairsArgs]) -> Cursor:
        """Start before the sample rows."""
        return Cursor()

    @classmethod
    def process(cls, params: ProcessParams[SamplePairsArgs], state: Cursor, out: OutputCollector) -> None:
        """Emit the sample pairs exactly once."""
        if state.offset:
            out.finish()
            return
        rows = [
            {
                "pair_id": key,
                "source_x": 500015.0,
                "source_y": 4100055.0,
                "target_x": 500095.0,
                "target_y": 4100055.0,
                "source_height_m": height,
                "target_height_m": 2.0,
            }
            for key, height in [("high", 80.0), ("low", 2.0)]
        ]
        out.emit(pa.RecordBatch.from_pylist(rows, schema=params.output_schema))
        state.offset = 2


GIS_FUNCTIONS: list[type[Any]] = [RidgeTowerPairs, Visibility, DemCells]

GIS_TABLES = [
    Table(
        name="ridge_tower_pairs",
        function=RidgeTowerPairs,
        comment=RidgeTowerPairs.Meta.description,
        constraints=(
            constraint_record(
                ["main"],
                "ridge_tower_pairs",
                "id_not_null",
                "NOT_NULL",
                [["pair_id"]],
                enforcement="ENFORCED",
                validation="ALL_ROWS",
            ),
            constraint_record(
                ["main"],
                "ridge_tower_pairs",
                "ridge_tower_pairs_pk",
                "PRIMARY_KEY",
                [["pair_id"]],
                enforcement="ENFORCED",
                validation="ALL_ROWS",
            ),
        ),
        tags={
            **RidgeTowerPairs.Meta.tags,
            "domain": "geospatial",
            "vgi.example_queries": json.dumps(
                [{"description": ex.description, "sql": ex.sql} for ex in RidgeTowerPairs.Meta.examples]
            ),
        },
        column_comments={
            f.name: (f.metadata or {}).get(b"comment", b"").decode() for f in RidgeTowerPairs.FIXED_SCHEMA
        },
    )
]
