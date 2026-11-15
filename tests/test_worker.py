"""Catalog surface and subprocess round-trips. The SQL-level tests live in test/sql."""

from __future__ import annotations

from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
from vgi.arguments import Arguments
from vgi.client import Client

from terrain_worker.worker import TerrainWorker

SCHEMA = ["main"]


def _table(client: Client, name: str, *positional: Any, **named: Any) -> pa.Table:
    arguments = Arguments(
        positional=tuple(pa.scalar(v) for v in positional),
        named={k: pa.scalar(v) for k, v in named.items()},
    )
    batches = list(client.table_function(function_name=name, schema_path=SCHEMA, arguments=arguments))
    return pa.Table.from_batches(batches)


def test_catalog_exposes_only_terrain_analysis() -> None:
    schemas = TerrainWorker.catalog.schemas
    assert [s.path for s in schemas] == [SCHEMA]
    names = sorted(getattr(f, "Meta").name for f in schemas[0].functions)  # noqa: B009
    assert names == ["dem_cells", "ridge_tower_pairs", "visibility"]
    assert [t.name for t in schemas[0].tables] == ["ridge_tower_pairs"]
    assert not getattr(TerrainWorker, "secret_types", [])


def test_ridge_tower_pairs_round_trip(client: Client) -> None:
    table = _table(client, "ridge_tower_pairs").sort_by("pair_id")
    assert table.column("pair_id").to_pylist() == ["high", "low"]
    assert table.column("source_height_m").to_pylist() == [80.0, 2.0]


def test_dem_cells_round_trip(client: Client) -> None:
    table = _table(client, "dem_cells", "demo://ridge.tif")
    assert table.num_rows == 121
    assert pc.max(table.column("elevation_m")).as_py() == 30.0
