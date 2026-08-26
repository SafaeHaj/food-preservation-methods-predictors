"""Operator entry points for work that has no user sitting in front of it.

    python -m app.cli import-packages --project 1 --root /app/uploads/extracted
    python -m app.cli import-packages --project 1 --root ... --limit 3 --dry-run
    python -m app.cli enrich-ingredients --provider pubchem --limit 20
    python -m app.cli enrich-matrices --limit 10

Importing a corpus extracted on another machine is a one-off per batch of papers, done by
whoever has shell access to the container. Putting it behind an HTTP route would mean
authenticating a request whose payload is "read this directory on your own filesystem",
which the API has no business accepting.

Ingestion stays on the API, where it belongs: it is per project, per user, and produces a
job the frontend follows.

Enrichment is the same class of job: corpus-wide, no project in the request, run by whoever
has shell access whenever a provider quota allows it -- not something a user waits on.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from shared.config import get_processing_settings
from shared.db.database import SessionLocal
from shared.db.models import Project
from shared.uow import unit_of_work

from app.services import enrichment_service, package_import
from app.services.enrichment import PubChemClient, UsdaClient

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


def _enrich_ingredients(args: argparse.Namespace) -> int:
    settings = get_processing_settings()
    client = PubChemClient(settings.PUBCHEM_BASE_URL, timeout=settings.ENRICHMENT_TIMEOUT_SECONDS)

    db = SessionLocal()
    try:
        with unit_of_work(db):
            report = enrichment_service.enrich_ingredients(db, client, limit=args.limit)
        print(json.dumps(report, indent=2))
        return 1 if report["errors"] else 0
    finally:
        db.close()


def _enrich_matrices(args: argparse.Namespace) -> int:
    settings = get_processing_settings()
    if not settings.USDA_FDC_API_KEY:
        print("PROCESSING_USDA_FDC_API_KEY is not set", file=sys.stderr)
        return 2
    client = UsdaClient(settings.USDA_BASE_URL, settings.USDA_FDC_API_KEY,
                        timeout=settings.ENRICHMENT_TIMEOUT_SECONDS)

    db = SessionLocal()
    try:
        with unit_of_work(db):
            report = enrichment_service.enrich_matrices(db, client, limit=args.limit)
        print(json.dumps(report, indent=2))
        return 1 if report["errors"] else 0
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

    enrich_ingredients = commands.add_parser(
        "enrich-ingredients",
        help="fill ingredient_molecular_features from PubChem, corpus-wide")
    enrich_ingredients.add_argument("--limit", type=int, default=None,
                                    help="attempt at most N ingredients, for a trial run")
    enrich_ingredients.set_defaults(handler=_enrich_ingredients)

    enrich_matrices = commands.add_parser(
        "enrich-matrices",
        help="fill matrix_profiles composition from USDA FoodData Central, corpus-wide")
    enrich_matrices.add_argument("--limit", type=int, default=None,
                                 help="attempt at most N matrices, for a trial run")
    enrich_matrices.set_defaults(handler=_enrich_matrices)

    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
