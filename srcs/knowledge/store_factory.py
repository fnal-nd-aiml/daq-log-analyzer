"""
File: store_factory.py
Purpose: Factory for creating structured store backends.
Category: Utility
Author: artdaq team
Depends: None
Exports: create_structured_store, get_backend_info
Complexity: Low | Lines: 58
"""

import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .base import StorageConfig
from .store_interface import StructuredStore
logger = logging.getLogger(__name__)

async def create_structured_store(config: 'StorageConfig') -> StructuredStore:
    from .base import DatabaseBackend
    backend = config.backend
    if isinstance(backend, str):
        backend = DatabaseBackend(backend)
    if backend == DatabaseBackend.SQLITE:
        from .sqlite_store import SQLiteStore
        sqlite_store = SQLiteStore(config.sqlite_path)
        await sqlite_store.initialize()
        logger.info(f'Using SQLite backend: {config.sqlite_path}')
        return sqlite_store
    elif backend == DatabaseBackend.POSTGRESQL:
        if config.postgres is None:
            raise ValueError("PostgreSQL configuration required when backend is 'postgresql'. Add 'postgres' section to storage config.")
        try:
            from .postgres_store import PostgresStore
            pg_store = PostgresStore(host=config.postgres.host, port=config.postgres.port, database=config.postgres.database, user=config.postgres.user, password=config.postgres.get_password(), min_connections=config.postgres.min_connections, max_connections=config.postgres.max_connections, ssl=config.postgres.ssl)
            await pg_store.initialize()
            logger.info(f'Using PostgreSQL backend: {config.postgres.host}:{config.postgres.port}/{config.postgres.database}')
            return pg_store
        except ImportError as e:
            logger.warning(f'PostgreSQL driver not available: {e}. Install with: pip install asyncpg')
            return await _fallback_to_sqlite(config)
        except Exception as e:
            logger.warning(f'PostgreSQL connection failed: {e}. Falling back to SQLite.')
            return await _fallback_to_sqlite(config)
    else:
        raise ValueError(f"Unknown database backend: {backend}. Use 'sqlite' or 'postgresql'.")

async def _fallback_to_sqlite(config: 'StorageConfig') -> StructuredStore:
    from .sqlite_store import SQLiteStore
    logger.info(f'Falling back to SQLite backend: {config.sqlite_path}')
    store = SQLiteStore(config.sqlite_path)
    await store.initialize()
    return store

def get_backend_info(config: 'StorageConfig') -> dict[str, str | int | bool]:
    from .base import DatabaseBackend
    backend = config.backend
    if isinstance(backend, str):
        backend = DatabaseBackend(backend)
    info: dict[str, str | int | bool] = {'backend': backend.value, 'backend_display': 'SQLite' if backend == DatabaseBackend.SQLITE else 'PostgreSQL'}
    if backend == DatabaseBackend.SQLITE:
        info['path'] = config.sqlite_path
    elif backend == DatabaseBackend.POSTGRESQL and config.postgres:
        info['host'] = config.postgres.host
        info['port'] = config.postgres.port
        info['database'] = config.postgres.database
        info['user'] = config.postgres.user
        info['ssl'] = config.postgres.ssl
    return info