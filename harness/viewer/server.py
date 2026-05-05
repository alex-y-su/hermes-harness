from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from harness import db
from harness.factory import factory_path
from harness.viewer.data import assignment_detail, dashboard, graph, hub_config, team_detail


class ViewerConfig:
    def __init__(self, *, factory: Path, db_path: Path) -> None:
        self.factory = factory
        self.db_path = db_path


class ViewerHandler(BaseHTTPRequestHandler):
    server_version = "HermesViewer/0.1"

    @property
    def config(self) -> ViewerConfig:
        return self.server.config  # type: ignore[attr-defined, return-value]

    def log_message(self, fmt: str, *args: Any) -> None:
        if os.getenv("HARNESS_VIEWER_QUIET"):
            return
        super().log_message(fmt, *args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._json({"ok": True})
            return
        if parsed.path.startswith("/api/"):
            self._api(parsed.path)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _api(self, path: str) -> None:
        try:
            if path == "/api/dashboard":
                self._json(dashboard(self.config.factory, self.config.db_path))
                return
            if path == "/api/graph":
                self._json(graph(self.config.factory, self.config.db_path))
                return
            if path == "/api/config":
                self._json(hub_config(self.config.factory))
                return
            if path.startswith("/api/teams/"):
                team_name = unquote(path.removeprefix("/api/teams/"))
                detail = team_detail(self.config.factory, self.config.db_path, team_name)
                if detail is None:
                    self.send_error(HTTPStatus.NOT_FOUND, "unknown team")
                    return
                self._json(detail)
                return
            if path.startswith("/api/assignments/"):
                assignment_id = unquote(path.removeprefix("/api/assignments/"))
                detail = assignment_detail(self.config.factory, self.config.db_path, assignment_id)
                if detail is None:
                    self.send_error(HTTPStatus.NOT_FOUND, "unknown assignment")
                    return
                self._json(detail)
                return
        except Exception as error:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _json(self, data: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(data, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class ViewerServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], config: ViewerConfig) -> None:
        self.config = config
        super().__init__(server_address, ViewerHandler)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the read-only Hermes hub JSON API.")
    parser.add_argument("--factory", default=os.getenv("HARNESS_FACTORY", "factory"), help="Hermes factory path")
    parser.add_argument("--db", default=None, help="SQLite database path; defaults to <factory>/harness.sqlite3")
    parser.add_argument("--host", default=os.getenv("HARNESS_VIEWER_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("HARNESS_VIEWER_PORT", "8090")))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    factory = factory_path(args.factory)
    db_path = Path(args.db).resolve() if args.db else db.default_db_path(factory)
    db.init_db(db_path)
    config = ViewerConfig(factory=factory, db_path=db_path)
    server = ViewerServer((args.host, args.port), config)
    print(f"Hermes hub viewer listening on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
