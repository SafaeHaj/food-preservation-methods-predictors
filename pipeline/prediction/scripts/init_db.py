"""Create the database schema (dev convenience). Prefer `alembic upgrade head` for real use."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.database.session import init_db  # noqa: E402


def main() -> None:
    init_db()
    print("schema created")


if __name__ == "__main__":
    main()
