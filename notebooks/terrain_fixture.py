"""Explicit synthetic loopback inventory for the worker's starter API recipe."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

ITEMS = (
    {"id": 101, "name": "Hand level", "category": "survey", "price": 20.0},
    {"id": 102, "name": "Field notebook", "category": "supplies", "price": 35.0},
    {"id": 103, "name": "Rangefinder", "category": "survey", "price": 50.0},
    {"id": 104, "name": "Tripod", "category": "mounting", "price": 75.0},
    {"id": 105, "name": "Receiver", "category": "electronics", "price": 100.0},
    {"id": 106, "name": "Protective case", "category": "supplies", "price": 140.0},
)


class SyntheticInventory:
    """Serve only authored local data; reject credentials and record sanitized requests."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self._previous_token = os.environ.pop("TERRAIN_API_TOKEN", None)
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlsplit(self.path)
                query = parse_qs(parsed.query)
                authorized = self.headers.get("Authorization") is not None
                if parsed.path != "/v1/items" or authorized or set(query) != {"page", "page_size"}:
                    self.send_error(400, "Only the unauthenticated synthetic items route is available")
                    return
                try:
                    page = int(query["page"][0])
                    size = int(query["page_size"][0])
                    if page < 1 or not 1 <= size <= 1000:
                        raise ValueError
                except (KeyError, ValueError):
                    self.send_error(400, "Invalid pagination")
                    return
                start = (page - 1) * size
                rows = ITEMS[start : start + size]
                fixture.requests.append(
                    {"page": page, "page_size": size, "item_ids": [r["id"] for r in rows], "credential_present": False}
                )
                body = json.dumps(
                    {"items": rows, "next_page": page + 1 if start + size < len(ITEMS) else None}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"

    def close(self) -> None:
        """Stop local transport and restore the caller's previous environment, without logging it."""
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
        if self._previous_token is None:
            os.environ.pop("TERRAIN_API_TOKEN", None)
        else:
            os.environ["TERRAIN_API_TOKEN"] = self._previous_token
