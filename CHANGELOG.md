# Changelog

## 0.2.1

- Docs link to upstream sources: the catalog `vgi.doc_md` gains a Sources and references section linking Rasterio, GDAL, the OGC GeoTIFF standard and pyproj (VGI183).
- The README quick-start install pin now points at the new release.

## 0.2.0 (2026-11-14)

- Removed the starter template's demo schema (`examples.greet`/`fetch_items`/`sequence_table`), `demo_input` and the placeholder `terrain_api` secret type. The worker no longer registers any secret type and needs no credentials.
- The bundled sample tower pairs are now `terrain.main.ridge_tower_pairs` (same columns and rows as the former `demo_input`); all examples, executable examples and agent tasks use it.
- Removed the starter SDK recipes (`examples/`), the mock REST API and the starter-only paginated inventory notebook.
- The catalog comment is now a short plain-text description of what the worker covers; the detailed analysis notes remain in the catalog's `vgi.doc_md` and `vgi.doc_llm` documentation.

## 0.1.0 (2026-11-14)

First release.

- `visibility(pairs, ...)` table function: line-of-sight per source/target pair over a north-up metre DEM, with minimum clearance, worst obstruction, 3D sightline, earth curvature/refraction and explicit status.
- `dem_cells(dem)` table function: cell-centre elevation, slope and aspect.
- `demo_input` table and bundled `demo://ridge.tif` synthetic ridge DEM.
- Composed examples driving `visibility` from `demo_input` and `dem_cells` (viewshed counts, clearance under the ridge, minimum clearing tower height), plus agent-sim tasks.

Targets: vgi-python 0.51 · VGI protocol 3.3 · Haybarn 2.0.0rc11 · vgi-lint-check 2.x (unpinned)
