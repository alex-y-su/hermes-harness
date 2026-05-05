from __future__ import annotations

import argparse
import os
from pathlib import Path

from harness import db
from harness.factory import factory_path


def add_factory_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--factory",
        default=os.getenv("HARNESS_FACTORY") or os.getenv("FACTORY_DIR", "factory"),
        help="Hermes factory path",
    )
    parser.add_argument("--db", default=None, help="SQLite database path; defaults to <factory>/harness.sqlite3")


def paths(args: argparse.Namespace) -> tuple[Path, Path]:
    factory = factory_path(args.factory)
    db_path = Path(args.db).resolve() if args.db else db.default_db_path(factory)
    db.init_db(db_path)
    return factory, db_path
