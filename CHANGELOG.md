# Changelog

## 0.1.0 (2026-11-14)

First release.

- `visibility(pairs, ...)` table function: line-of-sight per source/target pair over a north-up metre DEM, with minimum clearance, worst obstruction, 3D sightline, earth curvature/refraction and explicit status.
- `dem_cells(dem)` table function: cell-centre elevation, slope and aspect.
- `demo_input` table and bundled `demo://ridge.tif` synthetic ridge DEM.
- Composed examples driving `visibility` from `demo_input` and `dem_cells` (viewshed counts, clearance under the ridge, minimum clearing tower height), plus agent-sim tasks.

Targets: vgi-python 0.51 · VGI protocol 3.3 · Haybarn 2.0.0rc11 · vgi-lint-check 2.x (unpinned)
