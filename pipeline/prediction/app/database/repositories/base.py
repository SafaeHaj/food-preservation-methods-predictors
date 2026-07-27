"""Generic repository with the CRUD operations shared by every entity."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: Session) -> None:
        self.db = db

    def list(self) -> list[ModelT]:
        return list(self.db.scalars(select(self.model)).all())

    def get(self, ident: object) -> ModelT | None:
        """Fetch by primary key (a tuple for composite keys)."""
        return self.db.get(self.model, ident)

    def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        return obj

    def bulk_insert(self, objs: Iterable[ModelT]) -> None:
        self.db.add_all(list(objs))

    def count(self) -> int:
        return int(self.db.scalar(select(func.count()).select_from(self.model)) or 0)

    def delete_all(self) -> None:
        self.db.query(self.model).delete()
