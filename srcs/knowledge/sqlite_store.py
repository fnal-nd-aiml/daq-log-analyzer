"""
File: sqlite_store.py
Purpose: SQLite backend for the structured store.
Category: Utility
Author: artdaq team
Depends: None
Exports: SQLiteStore
Complexity: Low | Lines: 65
"""

from __future__ import annotations
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
import aiosqlite
from .sql import AiosqliteConnection, SqlConnection, SqliteDialect
from .sql_store import MAX_PATTERN_CANDIDATES, SqlStructuredStore
from .sqlite_schema import SCHEMA
logger = logging.getLogger(__name__)
__all__ = ['MAX_PATTERN_CANDIDATES', 'SQLiteStore']

class SQLiteStore(SqlStructuredStore):

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.dialect = SqliteDialect()
        self._initialized = False

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[SqlConnection]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield AiosqliteConnection(conn, self.dialect)

    async def close(self) -> None:
        pass

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.executescript(SCHEMA)
            await conn.commit()
            await self._run_migrations(conn)
        self._initialized = True

    async def _run_migrations(self, conn: aiosqlite.Connection) -> None:
        migrations = [('investigations', 'processing_tier', 'INTEGER DEFAULT 3'), ('investigations', 'confidence', 'REAL'), ('error_patterns', 'user_verified', 'BOOLEAN DEFAULT FALSE'), ('feedback_records', 'feedback_source', "TEXT DEFAULT 'cli'")]
        for table, column, definition in migrations:
            async with conn.execute(f'PRAGMA table_info({table})') as cursor:
                rows = await cursor.fetchall()
            existing = {row[1] for row in rows}
            if column not in existing:
                await conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
                await conn.commit()

    async def ensure_calibration_history_table(self) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS calibration_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT NOT NULL,
                    error_type TEXT,
                    recorded_at TIMESTAMP NOT NULL,
                    overall_bias REAL NOT NULL,
                    sample_size INTEGER NOT NULL,
                    overall_accuracy REAL NOT NULL,
                    buckets_json TEXT
                )
                ''')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_cal_history_model ON calibration_history(model_name, recorded_at)')
            await conn.commit()