"""Operator entry points for work that has no user sitting in front of it.

    python -m app.cli import-packages --project 1 --root /app/uploads/extracted
    python -m app.cli import-packages --project 1 --root ... --limit 3 --dry-run

Importing a corpus extracted on another machine is a one-off per batch of papers, done by
whoever has shell access to the container. Putting it behind an HTTP route would mean
authenticating a request whose payload is "read this directory on your own filesystem",
which the API has no business accepting.

Ingestion stays on the API, where it belongs: it is per project, per user, and produces a
job the frontend follows.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from shared.db.database import SessionLocal
from shared.db.models import Project
from shared.uow import unit_of_work

from app.services import package_import

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _import_packages(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if not root.is_dir():
        print(f"No such directory: {root}", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        if not db.query(Project).filter(Project.id == args.project).first():
            print(f"No project with id {args.project}", file=sys.stderr)
            return 2

        if args.dry_run:
            # Reads and validates every package without writing, so a malformed corpus is
            # discovered before any of it is registered.
            directories = package_import.discover(root)[:args.limit]
            report = {"found": len(directories), "papers": [], "failed": []}
            for directory in directories:
                try:
                    package, stamped = package_import.read_package(directory)
                    report["papers"].append({
                        "paper": directory.name,
                        "observations": package["gate_report"].get("observations", 0),
                        "tables": len(package.get("tables") or []),
                        "figures": len(package.get("figures") or []),
                        "needs_version_stamp": stamped,
                    })
                except Exception as exc:
                    report["failed"].append({"paper": directory.name, "reason": str(exc)[:300]})
            print(json.dumps(report, indent=2))
            return 1 if report["failed"] else 0

        with unit_of_work(db):
            result = package_import.import_root(db, args.project, root, args.limit)
        print(json.dumps(result.as_dict(), indent=2))
        return 1 if result.failed else 0
    finally:
        db.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    importer = commands.add_parser(
        "import-packages",
        help="register extraction packages produced elsewhere so they can be ingested")
    importer.add_argument("--project", type=int, required=True)
    importer.add_argument("--root", required=True,
                          help="directory holding one sub-directory per paper")
    importer.add_argument("--limit", type=int, default=None,
                          help="register only the first N, for a trial run")
    importer.add_argument("--dry-run", action="store_true",
                          help="validate and report without writing anything")
    importer.set_defaults(handler=_import_packages)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
