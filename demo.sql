-- Offline acceptance demos. Run with: uv run --with duckdb==2.0.0 python scripts/run_demo.py
-- The runner loads VGI, attaches this worker, and installs Spatial for geometry joins.

-- Demo tower pairs on bundled synthetic data
SELECT pair_id, source_height_m FROM terrain.main.demo_input ORDER BY pair_id;

-- Terrain visibility on bundled synthetic data
SELECT pair_id, visible, status FROM terrain.main.visibility((SELECT * FROM terrain.main.demo_input)) ORDER BY pair_id;

-- DEM cells and surfaces on bundled synthetic data
SELECT count(*), max(elevation_m) FROM terrain.main.dem_cells('demo://ridge.tif');

-- Rank a suitable tower per building
WITH buildings(pair_id, building_id, tower_id) AS (VALUES ('high', 'library', 'tower-80m'), ('low', 'library', 'tower-2m')),
visibility AS (SELECT * FROM terrain.main.visibility((SELECT * FROM terrain.main.demo_input)))
SELECT b.building_id, b.tower_id, v.status
FROM visibility v JOIN buildings b USING(pair_id) WHERE v.visible
QUALIFY row_number() OVER (PARTITION BY b.building_id ORDER BY v.min_clearance_m DESC, b.tower_id) = 1
ORDER BY b.building_id;

-- Build a viewshed as rows
SELECT count(*), count(visible), count(*) FILTER (WHERE status NOT IN ('visible', 'blocked'))
FROM terrain.main.visibility((SELECT cell_id::VARCHAR pair_id, 500015.0 source_x, 4100055.0 source_y,
x target_x, y target_y, 80.0 source_height_m, 2.0 target_height_m FROM terrain.main.dem_cells('demo://ridge.tif')));
