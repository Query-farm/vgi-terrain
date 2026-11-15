"""Shared fixtures: a worker client launched the way DuckDB launches it."""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest
from vgi.client import Client


@pytest.fixture(scope="session")
def client() -> Iterator[Client]:
    """A client that launches the worker as a subprocess, the way DuckDB does."""
    with Client([sys.executable, "-m", "terrain_worker.worker"]) as c:
        yield c
