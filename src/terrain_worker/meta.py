"""Discovery metadata: the one file to edit when you rename or extend the worker.

DuckDB, coding agents and the ``vgi-lint`` metadata checker all read these
tags. Keep every object documented and ``make lint`` stays at 100.

* Catalog-level tags (title, license, author, links, long description) live in
  ``CATALOG_TAGS`` below.
* Every function and table carries ``object_tags(...)``: a title, a category
  from ``SCHEMA_CATEGORIES``, search keywords, and LLM- and human-facing docs.
"""

from __future__ import annotations

import json
from typing import Any

import pyarrow as pa

CATALOG_NAME = "terrain"

SOURCE_URL = "https://github.com/Query-farm/vgi-terrain"

# Categories group functions in docs and agent tools. Every object's
# ``vgi.category`` must name one of these.
SCHEMA_CATEGORIES = [
    {
        "name": "gis",
        "title": "GIS Analysis",
        "description": "Spatial analysis over query results and geospatial assets.",
    },
]


# Upstream specs, data providers and libraries the catalog docs link to (VGI183).
CATALOG_REFERENCES_MD = (
    "\n\n## Sources and references\n\n"
    "- [Rasterio](https://rasterio.readthedocs.io/) on [GDAL](https://gdal.org/): reads and samples the "
    "DEM rasters.\n"
    "- [OGC GeoTIFF](https://www.ogc.org/standards/geotiff/): the georeferenced raster format expected for "
    "DEM inputs such as the bundled `demo://ridge.tif`.\n"
    "- [pyproj](https://pyproj4.github.io/pyproj/stable/) ([PROJ](https://proj.org/)): coordinate "
    "transforms from endpoint CRSs into the DEM's projected metre CRS."
)


def keywords_array(keywords: str) -> str:
    """Turn ``"a, b, c"`` into the JSON array string ``vgi.keywords`` requires."""
    return json.dumps([k.strip() for k in keywords.split(",") if k.strip()])


def object_tags(*, title: str, category: str, keywords: str, doc_llm: str, doc_md: str) -> dict[str, str]:
    """Build the standard per-object discovery tags."""
    if category not in {c["name"] for c in SCHEMA_CATEGORIES}:
        raise ValueError(f"unknown category {category!r}; add it to SCHEMA_CATEGORIES")
    return {
        "vgi.title": title,
        "vgi.category": category,
        "vgi.keywords": keywords_array(keywords),
        "vgi.doc_llm": doc_llm,
        "vgi.doc_md": doc_md,
    }


def column(name: str, type_: pa.DataType, comment: str, *, nullable: bool = True) -> pa.Field[Any]:
    """Build an Arrow field whose ``comment`` shows up in DuckDB's ``DESCRIBE`` and agent tools."""
    return pa.field(name, type_, nullable=nullable, metadata={b"comment": comment.encode()})


CATALOG_DOC_LLM = (
    "Sampled terrain visibility and DEM surfaces as DuckDB SQL functions. `terrain.main.visibility` "
    "takes a subquery of tower/building endpoint pairs (pair_id, source_x/y, target_x/y, "
    "source_height_m, target_height_m) and returns one line-of-sight assessment per pair: visible, "
    "minimum clearance, worst obstruction, a 3D WKB sightline and an explicit status (visible, blocked, "
    "outside_dem, nodata). `terrain.main.dem_cells(dem)` returns cell-centre elevation, slope and aspect "
    "for a north-up projected metre DEM. Cross join observers with dem_cells and pass the pairs to "
    "visibility for a viewshed. `terrain.main.ridge_tower_pairs` and the bundled `demo://ridge.tif` DEM "
    "are synthetic offline sample inputs. No credentials are needed."
)

CATALOG_DOC_MD = (
    "# VGI terrain worker\n\n"
    "**Terrain line-of-sight and viewsheds from DuckDB SQL.** Pass tower/building pairs from any "
    "query to `visibility` and get minimum clearance, the worst obstruction and a 3D sightline per "
    "pair, with earth curvature and refraction. `dem_cells` exposes a DEM's cell centres, elevation, "
    "slope and aspect as rows, so a viewshed is an ordinary SQL cross join.\n\n"
    "Distances and heights are metres; DEMs must be north-up in a projected metre CRS. Missing "
    "terrain yields unknown visibility rather than a clear line. A synthetic ridge DEM "
    "(`demo://ridge.tif`) and two sample tower pairs (`ridge_tower_pairs`) ship in the wheel, so every "
    "example runs offline. See the [VGI documentation](https://query.farm/vgi/docs/) to learn more."
)

AGENT_TEST_TASKS = [
    {
        "name": "gis_ridge_tower_pairs",
        "prompt": "Inspect the two tower heights. Use the bundled synthetic inputs and return the "
        "columns and ordering shown in its catalog example.",
    },
    {
        "name": "gis_visibility",
        "prompt": "A tall tower clears the ridge; a low tower is blocked. Use the bundled synthetic"
        " inputs and return the columns and ordering shown in its catalog example.",
    },
    {
        "name": "gis_dem_cells",
        "prompt": "Count cells and find the ridge elevation. Use the bundled synthetic inputs and "
        "return the columns and ordering shown in its catalog example.",
    },
    {
        "name": "gis_steep_cells_visible",
        "prompt": "Using the terrain worker's bundled ridge DEM (demo://ridge.tif) and the tower of the 'high' "
        "sample pair (its source position and its 80 m height), with receivers 2 m above ground, how many DEM "
        "cells with a slope steeper than 45 degrees can that tower see? Return one row with one BIGINT column "
        "named visible_steep_cells.",
    },
    {
        "name": "gis_min_clearing_height",
        "prompt": "Keeping everything else about the 'low' sample tower pair the same, what is the smallest "
        "whole-metre tower height (source_height_m) for which the terrain worker reports a clear line of "
        "sight over the ridge? Return one row with one INTEGER column named min_height_m.",
    },
]

CATALOG_TAGS = {
    "vgi.title": "Terrain analysis",
    "vgi.subtitle": "DEM visibility, viewsheds, slope and aspect from SQL.",
    "vgi.doc_llm": CATALOG_DOC_LLM,
    "vgi.doc_md": CATALOG_DOC_MD,
    "vgi.source_url": SOURCE_URL,
    "vgi.icon_url": "https://query.farm/media-kit/products/vgi/vgi-logo.png",
    "vgi.license": "0BSD",
    "vgi.author": "Query.Farm",
    "vgi.copyright": "Copyright 2026 Query.Farm LLC",
    "vgi.keywords": keywords_array("vgi, duckdb, terrain, DEM, visibility, viewshed, elevation"),
    "vgi.support_contact": f"{SOURCE_URL}/issues",
    "vgi.support_policy_url": f"{SOURCE_URL}#support",
    # Public analyst tasks for `vgi-lint simulate`; private graders live in vgi-agent-tests.yaml.
    "vgi.agent_test_tasks": json.dumps(AGENT_TEST_TASKS),
}
