# Terrain visibility and viewsheds

Independent Python VGI worker: query geospatial analysis from SQL and join the resulting rows to your existing tables.

## Run it

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/Query-farm/vgi-terrain.git
cd vgi-terrain
uv sync --locked
make demo
make verify-stock
make check
```

`make demo` runs [demo.sql](demo.sql) in stock DuckDB 2.0.0. Demo datasets ship inside the wheel; no data credentials are required. The first run downloads dependencies and signed SQL extensions. `make verify-stock` asserts every expected result in [vgi-worker.json](vgi-worker.json), including empty inputs, joins and multiple batches.

## Analysis contract

`visibility((SELECT pair_id, source_x, source_y, target_x, target_y, source_height_m, target_height_m FROM pairs), ...)` returns visibility, minimum clearance, the worst obstruction, a 3D sightline and explicit status. `dem_cells(dem)` returns cell-centre elevation, slope and aspect. `demo_input` is a table of two tower/building pairs.

**Acceptance:** a 30 m ridge blocks the 2 m tower but clears the 80 m tower. SQL ranks the visible tower for a building and evaluates all 121 DEM cells as a viewshed. Coordinates transformed from longitude/latitude give the same result.

Supply a north-up DEM in a projected metre CRS, with metre elevations. Raster scale/offset is applied; declared non-metre elevation units fail explicitly. Endpoints can use another `input_crs`; endpoint heights are above the DEM surface. Sampling uses the smaller of `step_m` and half the smallest pixel dimension, with nearest-cell terrain. Effective-earth-radius curvature uses `refraction_k`, default 7/6. Missing samples make visibility unknown. This is sampled terrain visibility: it does not include buildings/trees absent from the elevation surface, radio Fresnel zones, or continuous subpixel obstructions.

Slope/aspect use finite differences; flat aspect is NULL and missing neighbours propagate unknown gradients. Defaults cap DEMs at 2 million cells and each sightline at 200,000 samples. For larger regions, tile inputs while ensuring each complete sightline is covered. Cross join towers to buildings or DEM cells in SQL before passing the resulting pairs.

## Use your data

From the repository directory after `uv sync`, launch the locked environment:

```sql
SET allow_extension_repositories = 'allowed';
CREATE EXTENSION REPOSITORY IF NOT EXISTS query_farm
  WITH PREFIX 'https://duckdb-extensions.query.farm';
INSTALL vgi FROM query_farm;
LOAD vgi FROM query_farm;
INSTALL spatial;
LOAD spatial;
ATTACH 'terrain' (TYPE vgi,
  LOCATION 'uv run --locked vgi-terrain-worker');
```

The following template expects your own source tables and paths:

```sql
SELECT pair_id, visible, min_clearance_m, status
FROM terrain.main.visibility((SELECT * FROM tower_building_pairs),
    dem := '/absolute/path/terrain.tif', input_crs := 'EPSG:4326')
ORDER BY pair_id;
```

WKB is an ordinary SQL BLOB with an explicit companion CRS, not an automatically transformed geometry. Use `ST_AsWKB` on input and `ST_GeomFromWKB` on output when using Spatial. Coordinates always use X/Y order. Do not join different coordinate systems without transforming them. Input IDs are retained as VARCHAR for joins. Invalid input schemas, geometries, coordinates and exceeded resource limits fail explicitly.

## Verification and provenance

- Scientific fixtures and edge cases: [tests/test_analysis.py](tests/test_analysis.py).
- Real SQL across stdio, launch and HTTP: [test/sql/gis.test](test/sql/gis.test), run by `make check` alongside the preserved SDK regression suite.
- Stock DuckDB contract: `make verify-stock` writes local evidence to `validation/stock-duckdb.json`.
- Full local checks: `make check`; generated validation output is intentionally untracked.
- Worker language: Python, pinned locally to 3.13. SDK: `vgi-python 0.51.1` with the starter's `>=0.51.1,<0.52` compatibility bound retained.
- Starter: [Query-farm/vgi-starter-python](https://github.com/Query-farm/vgi-starter-python), commit `9cca9105474d6e0052b8e343c8ea21f3d1a7503c`, template 1.3.0.
- Stock engine: DuckDB 2.0.0, signed VGI extension `e75482339d` from `query_farm`. The starter integration runner is separately pinned to `haybarn-unittest 2.0.0rc11`; it is not the stock DuckDB check.

`make check` includes formatting, Ruff, strict mypy, docstring checks, unit tests, all three SQL transports, executed metadata examples and stock DuckDB assertions. `make lint-ai` is an optional agent evaluation and is not part of the completed checks. The `examples` schema preserves starter functions; GIS functions live in `main`. Tests use synthetic known-answer fixtures, not a claim of production accuracy on every dataset.

Run `make release-check` to build a wheel from the source archive and verify its installed SQL interface outside the checkout. `make verify-container` builds locked runtime dependencies and checks every stock SQL assertion through a non-root, read-only HTTP container. See [PRODUCTION.md](PRODUCTION.md) for deployment, capacity limits, release evidence and operational boundaries.

## Support

Source and issue tracking are published at [Query-farm/vgi-terrain](https://github.com/Query-farm/vgi-terrain). No hosted deployment or container release is provided by publishing this source. Keep reports tied to the input CRS, resource limits and reproducible SQL. See [LICENSE](LICENSE) for the starter's license and dependency licenses for their terms.

## Notebook

[One ray is not a viewshed](notebooks/README.md) is an executed, portable SQL analysis of the bundled synthetic ridge.
