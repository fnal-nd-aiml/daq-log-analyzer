"""
File: dialect.py
Purpose: SQL dialect differences between the SQLite and PostgreSQL backends.
Category: Utility
Author: artdaq team
Depends: None
Exports: SqlDialect, SqliteDialect, PostgresDialect, _PLACEHOLDER
Complexity: Medium | Lines: 54
"""

from __future__ import annotations
import re
from abc import ABC, abstractmethod
_PLACEHOLDER = re.compile("'[^']*'|\\?")

class SqlDialect(ABC):
    name: str

    @abstractmethod
    def translate(self, sql: str) -> str:
        pass

    @abstractmethod
    def bool_literal(self, value: bool) -> str:
        pass

    @abstractmethod
    def upsert(self, table: str, columns: list[str], key: str='id') -> str:
        pass

class SqliteDialect(SqlDialect):
    name = 'sqlite'

    def translate(self, sql: str) -> str:
        return sql

    def bool_literal(self, value: bool) -> str:
        return 'TRUE' if value else 'FALSE'

    def upsert(self, table: str, columns: list[str], key: str='id') -> str:
        placeholders = ', '.join(('?' for _ in columns))
        return f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"

class PostgresDialect(SqlDialect):
    name = 'postgresql'

    def translate(self, sql: str) -> str:
        counter = iter(range(1, 10000))

        def replace(match: re.Match[str]) -> str:
            token = match.group(0)
            if token != '?':
                return token
            return f'${next(counter)}'
        return _PLACEHOLDER.sub(replace, sql)

    def bool_literal(self, value: bool) -> str:
        return 'TRUE' if value else 'FALSE'

    def upsert(self, table: str, columns: list[str], key: str='id') -> str:
        placeholders = ', '.join(('?' for _ in columns))
        updates = ', '.join((f'{c} = EXCLUDED.{c}' for c in columns if c != key))
        statement = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT ({key}) DO "
        return statement + (f'UPDATE SET {updates}' if updates else 'NOTHING')