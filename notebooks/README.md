# Terrain notebook

[01 · One ray is not a viewshed](01_one_ray_is_not_a_viewshed.ipynb) compares sampled terrain visibility from two observer heights, maps a complete 121-cell synthetic DEM and reconstructs the highlighted ridge crossing in visible SQL. Unknown coverage stays distinct from blocked terrain.

Run from this directory alone with [uv](https://docs.astral.sh/uv/) and Git:

```sh
uv sync --locked
uv run --locked python execute.py
uv run --locked python execute.py --parameters '{"SOURCE_HEIGHT_M":40.0}' --output-dir validation/height-40
```

For interactive use, register the environment with `uv run --locked python -m ipykernel install --user --name terrain-notebooks --display-name 'Python (Terrain notebooks)'` and select it in Jupyter. Restart Kernel → Run All after editing the visible parameter. The runner uses a temporary kernel and replaces saved output only after success. Parameter overrides require a separate destination and copy branding, documentation and runtime companions. Generated `artifacts/` and `validation/` outputs are ignored.

## Portable source and synthetic data

The literal ATTACH launches `uvx --python 3.13 --from git+https://github.com/Query-farm/vgi-terrain.git@851dddfeeeb0b267325b987f5848c3df4177b01a --constraints worker-constraints.txt vgi-terrain-worker`. uv fetches/builds the immutable public revision and caches it with constrained registry dependencies. No local worker checkout, root environment or parent-path discovery is used. Worker constraints are exported from that source lock, including SDK 0.51.1/RPC 0.53.1 and its scientific packages. Update pin and constraints together after validation. The notebook has its own locked Haybarn 2.0.0rc11 environment.

`demo://ridge.tif` is bundled package data: 121 synthetic 10 m cells with a 30 m ridge, in EPSG:32618 and metre elevations. No acquisition date, real surveyed place, live feed or fallback dataset is implied. The source package also supplies the observer/receiver geometry. The notebook reads DEM cells once, constructs 244 pairs (121 cell-centre receivers plus one outside control, for each of two heights), and invokes visibility once over all pairs. Later queries use materialized in-memory tables. Bounds: 121 loaded DEM cells and 40 samples per ray. The fixed maximum step is 5 m; nearest-cell terrain and k=7/6 curvature are explicit.

The SQL connection uses a fresh temporary secret directory with persistent secrets disabled, fully drains and asserts an empty inventory before ATTACH, then closes the connection and cleans up. These computations need no credentials.

## Interpretation and validation

Observer and receiver heights are above their own DEM cells. Grid colouring represents each receiver centre, not every location within a filled square. The minimum clearance uses interior ray samples and accepts values >= -1e-9 m for numerical tolerance. Outside or nodata samples yield unknown visibility; NULL must not be converted to a blocked or clear result.

Default observer height is 80 m; the independent low reference is 2 m. The separate experiment lowers the selected height to 40 m while keeping the DEM, receivers, reference and sampling fixed. Compare the entire mapped population as well as the highlighted 80 m ray. A cell/reference fingerprint, ten SQL invariants and population controls enforce that comparison. The ray reconstruction includes the curvature term and checks agreement with the worker within 1e-10 m.

The default and notebook-only detached experiment are executed separately, both figures are visually reviewed and three runner guards verify default protection. Audit JSON and extracted charts remain under ignored `artifacts/` and `validation/`. Scientific assumptions are explicit: no buildings/trees beyond the supplied DEM, no Fresnel-zone/radio model, no continuous subpixel visibility guarantee. Half-pixel sampling does not add new terrain information.

Source gates pass: 14 Python 3.13 and 14 isolated 3.14 units, 105 stdio/105 Unix/69 HTTP SQL assertions, metadata 100/L2 with zero findings, Ruff/type/doc checks, seven stock DuckDB 2.0.0 checks and seven checks through an isolated sdist-built wheel. Docker is unavailable, so no container check or deployment is claimed. See [STANDARD.md](STANDARD.md) and the root source documentation.
