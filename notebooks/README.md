# Terrain analysis walkthroughs

- [01 · One ray is not a viewshed](01_one_ray_is_not_a_viewshed.ipynb) compares sampled terrain visibility from two observer heights, maps all 121 synthetic DEM cell centres and independently reconstructs the highlighted ridge crossing in visible SQL. Unknown coverage remains distinct from blocked terrain.
- [02 · Complete the input before previewing a report](02_paginated_inventory_report.ipynb) demonstrates the separately named `examples` schema: a real worker reads three local synthetic API pages, generates seven budget scenarios, and formats local reviewer previews without inventing missing names. These starter recipes do not perform terrain analysis.

The two stories cover all six distinct public names. The worker's `demo_input` table/function aliases and `greet` overloads each count once. All data are explicitly synthetic; there are no real observations, recommendations, credentials or messages.

## Run locally or in Colab

Install [uv](https://docs.astral.sh/uv/) and Git. From `notebooks/`:

```sh
uv sync --locked
uv run --locked vgi-notebooks 01_one_ray_is_not_a_viewshed.ipynb
uv run --locked vgi-notebooks 02_paginated_inventory_report.ipynb
```

For an editor, select `notebooks/.venv/bin/python`, use `notebooks/` as the working directory and restart/run all after changing parameters. Each notebook's Colab badge opens its source. Its visible bootstrap installs the shared base package; the locked local environment adds `[runner]`. The shared `terrain` companion registry retrieves the second notebook's hash-verified fixture without cloning the repository. The first notebook is self-contained.

The literal released launcher is the same in both:

```sql
ATTACH 'terrain' (TYPE vgi,
 LOCATION 'uvx --python 3.13 --from git+https://github.com/Query-farm/vgi-terrain@v0.1.0 vgi-terrain-worker');
```

The worker runs in its own Python 3.13 environment. Its release owns dependency constraints, including Rasterio, Shapely, PyProj and the SDK; no old constraints file, extra `--with` pins, local checkout or notebook-kernel GIS installation is needed. First use needs Git, package and VGI extension downloads. Source is release-pinned; transitive versions follow the release's declared constraints, while local notebook dependencies are locked.

Shared connections create a fresh empty SQL secret directory and disable persistent secrets. The second notebook's [fixture](terrain_fixture.py) clears/restores `TERRAIN_API_TOKEN` without displaying it, rejects Authorization headers, and binds only to loopback. The worker's API call is materialized before DataFrame capture. A sanitized audit requires exactly three requests for the six known IDs; no SQL secret is created. Cleanup closes the connection and local server.

## Terrain model and experiment

`demo://ridge.tif` is bundled package data: 121 synthetic 10 m cells with a 30 m ridge, in EPSG:32618 and metre elevations. No acquisition date, real surveyed place or live fallback is implied. `demo_input` supplies observer/receiver geometry. The notebook loads the DEM once and builds 244 pairs: 121 cell-centre receivers plus an outside control, for each of two heights. Visibility is materialized once; subsequent selections read local tables.

Observer/receiver heights are above their own DEM cells. Grid colouring describes each receiver centre, not every location in a square. The 5 m maximum sampling step does not create subpixel terrain detail; nearest-cell terrain, k=7/6 curvature, at most 121 loaded cells and at most 40 samples per ray are explicit. Minimum clearance uses interior samples with a -1e-9 m tolerance. Outside/nodata visibility stays NULL, not clear or blocked. No building/tree model, Fresnel zone, radio link budget or continuous visibility guarantee is included.

The selected observer defaults to 80 m, with a fixed 2 m reference. Change it to 40 m while preserving the saved default:

```sh
uv run --locked vgi-notebooks 01_one_ray_is_not_a_viewshed.ipynb \
  --parameters '{"SOURCE_HEIGHT_M":40.0}' --output-dir validation/height-40
```

Compare the complete receiver population and highlighted 80 m horizontal ray. An unchanged cell/reference fingerprint, ten SQL invariants and population controls enforce the comparison. The independent ray reconstruction includes curvature and checks agreement with the worker within 1e-10 m. The authored parameter domain is finite heights from 0 to 150 m; it does not establish a realistic tower design.

## Starter workflow experiment

The second notebook serves six invented equipment prices from a local HTTP fixture. Prices are in illustrative USD, converted to SQL decimals. The selected budget applies to **one item at a time**, not a shopping basket. Seven scenarios from 0 to 150 USD use the same inventory; the line between budget scenarios is deliberately not interpolated.

```sh
uv run --locked vgi-notebooks 02_paginated_inventory_report.ipynb \
  --parameters '{"BUDGET_USD":75}' --output-dir validation/budget-75
```

The default 50 USD budget allows three items; 75 USD allows four. IDs, prices, three API pages and the full scenario grid remain fixed. The item highlighting, selected scenario and two local reviewer preview strings change. A third reviewer's missing name remains NULL in both greeting overloads and the preview. Formatting a salutation neither resolves identity nor sends a message.

## Evidence and limits

[coverage.json](coverage.json) binds all six names to visible executed SQL, results and interpretation. Complete function/table/view exports, including empty views, are saved in [coverage/](coverage/). Authentication-capable `examples.fetch_items` remains in the denominator and is exercised with the explicit local fixture. Both release and current public-main catalogs were captured through actual Haybarn 2.0.0rc11 at the same source revision, `b08c5c9f06937f34ab65684f26ccda4635ee4e98`.

Defaults and both notebook-only detached experiments execute independently. The runner protects successful defaults, rejects unknown parameters and requires a separate experiment destination. Charts use shared SVG presentation, with linked published assets retained under `charts/`. Review PNGs and diagnostics remain ignored. One fresh preloaded Python 3.12 kernel checks the full worker/fixture bootstrap path without replacing already loaded pandas, Matplotlib, IPython, ipykernel or jupyter-client, and without installing runner/GIS libraries into the kernel. Hosted Colab was not manually executed.

The unchanged worker's green [source CI](https://github.com/Query-farm/vgi-terrain/actions/runs/43619270181) is reused; no source rebuild, full suite repetition or container publication is part of this notebook update. Full notebook standards live in the [shared package](https://github.com/Query-farm/vgi-example-notebooks/blob/main/docs/standard.md).
