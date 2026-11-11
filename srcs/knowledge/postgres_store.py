"""
File: postgres_store.py
Purpose: PostgreSQL backend for the structured store.
Category: Utility
Author: artdaq team
Depends: None
Exports: PostgresStore
Complexity: Low | Lines: 61
"""

from __future__ import annotations
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from .postgres_schema import SCHEMA
from .sql import AsyncpgConnection, PostgresDialect, SqlConnection
from .sql_store import SqlStructuredStore
if TYPE_CHECKING:
    import asyncpg
logger = logging.getLogger(__name__)
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
__all__ = ['ASYNCPG_AVAILABLE', 'PostgresStore']

class PostgresStore(SqlStructuredStore):
    _COLUMN_MIGRATIONS = ('ALTER TABLE investigations ADD COLUMN IF NOT EXISTS processing_tier INTEGER DEFAULT 3', 'ALTER TABLE investigations ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION', 'ALTER TABLE error_patterns ADD COLUMN IF NOT EXISTS user_verified BOOLEAN DEFAULT FALSE', "ALTER TABLE feedback_records ADD COLUMN IF NOT EXISTS feedback_source TEXT DEFAULT 'cli'")

    def __init__(self, host: str='localhost', port: int=5432, database: str='daq_analyzer', user: str='postgres', password: str='', min_connections: int=2, max_connections: int=10, ssl: bool=False):
        if not ASYNCPG_AVAILABLE:
            raise ImportError('asyncpg is required for PostgreSQL support. Install with: pip install asyncpg')
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.ssl = ssl
        self.dialect = PostgresDialect()
        self._pool: Any = None

    async def initialize(self) -> None:
        await self._ensure_initialized()

    async def _ensure_initialized(self) -> None:
        if self._pool is not None:
            return
        self._pool = await asyncpg.create_pool(host=self.host, port=self.port, database=self.database, user=self.user, password=self.password, min_size=self.min_connections, max_size=self.max_connections, ssl='require' if self.ssl else None)
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA)
            for migration in self._COLUMN_MIGRATIONS:
                await conn.execute(migration)
        logger.info('PostgreSQL store initialized: %s:%s/%s', self.host, self.port, self.database)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[SqlConnection]:
        await self._ensure_initialized()
        async with self._pool.acquire() as conn:
            yield AsyncpgConnection(conn, self.dialect)

    async def ensure_calibration_history_table(self) -> None:
        await self._ensure_initialized()