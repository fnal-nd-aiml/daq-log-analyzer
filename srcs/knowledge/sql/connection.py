"""
File: connection.py
Purpose: Uniform async connection interface over aiosqlite and asyncpg.
Category: Utility
Author: artdaq team
Depends: None
Exports: SqlConnection, AiosqliteConnection, AsyncpgConnection
Complexity: Medium | Lines: 118
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any
from .dialect import SqlDialect

class SqlConnection(ABC):

    def __init__(self, dialect: SqlDialect) -> None:
        self.dialect = dialect

    @abstractmethod
    async def fetch_all(self, sql: str, params: Sequence[Any]=()) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    async def fetch_one(self, sql: str, params: Sequence[Any]=()) -> dict[str, Any] | None:
        pass

    @abstractmethod
    async def fetch_value(self, sql: str, params: Sequence[Any]=(), default: Any=None) -> Any:
        pass

    @abstractmethod
    async def execute(self, sql: str, params: Sequence[Any]=()) -> int:
        pass

    @abstractmethod
    async def execute_many(self, sql: str, param_sets: Sequence[Sequence[Any]]) -> None:
        pass

    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[None]:
        pass

class AiosqliteConnection(SqlConnection):

    def __init__(self, conn: Any, dialect: SqlDialect) -> None:
        super().__init__(dialect)
        self._conn = conn
        self._in_transaction = False

    async def fetch_all(self, sql: str, params: Sequence[Any]=()) -> list[dict[str, Any]]:
        async with self._conn.execute(self.dialect.translate(sql), tuple(params)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: Sequence[Any]=()) -> dict[str, Any] | None:
        async with self._conn.execute(self.dialect.translate(sql), tuple(params)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row is not None else None

    async def fetch_value(self, sql: str, params: Sequence[Any]=(), default: Any=None) -> Any:
        async with self._conn.execute(self.dialect.translate(sql), tuple(params)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    async def execute(self, sql: str, params: Sequence[Any]=()) -> int:
        cursor = await self._conn.execute(self.dialect.translate(sql), tuple(params))
        if not self._in_transaction:
            await self._conn.commit()
        return int(cursor.rowcount)

    async def execute_many(self, sql: str, param_sets: Sequence[Sequence[Any]]) -> None:
        await self._conn.executemany(self.dialect.translate(sql), [tuple(p) for p in param_sets])
        if not self._in_transaction:
            await self._conn.commit()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        await self._conn.execute('BEGIN')
        self._in_transaction = True
        try:
            yield
        except Exception:
            await self._conn.rollback()
            raise
        else:
            await self._conn.commit()
        finally:
            self._in_transaction = False

class AsyncpgConnection(SqlConnection):

    def __init__(self, conn: Any, dialect: SqlDialect) -> None:
        super().__init__(dialect)
        self._conn = conn

    async def fetch_all(self, sql: str, params: Sequence[Any]=()) -> list[dict[str, Any]]:
        rows = await self._conn.fetch(self.dialect.translate(sql), *params)
        return [dict(row) for row in rows]

    async def fetch_one(self, sql: str, params: Sequence[Any]=()) -> dict[str, Any] | None:
        row = await self._conn.fetchrow(self.dialect.translate(sql), *params)
        return dict(row) if row is not None else None

    async def fetch_value(self, sql: str, params: Sequence[Any]=(), default: Any=None) -> Any:
        value = await self._conn.fetchval(self.dialect.translate(sql), *params)
        return default if value is None else value

    async def execute(self, sql: str, params: Sequence[Any]=()) -> int:
        status = await self._conn.execute(self.dialect.translate(sql), *params)
        try:
            return int(str(status).rsplit(' ', 1)[-1])
        except (ValueError, IndexError):
            return 0

    async def execute_many(self, sql: str, param_sets: Sequence[Sequence[Any]]) -> None:
        await self._conn.executemany(self.dialect.translate(sql), [tuple(p) for p in param_sets])

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        async with self._conn.transaction():
            yield