"""Load the mock dataset into the database via the ETL service."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.database.session import SessionLocal, init_db  # noqa: E402
from app.services import ETLService  # noqa: E402


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        counts = ETLService(db).load()
    finally:
        db.close()
    for table, n in counts.items():
        print(f"{table:24s} {n}")


if __name__ == "__main__":
    main()
