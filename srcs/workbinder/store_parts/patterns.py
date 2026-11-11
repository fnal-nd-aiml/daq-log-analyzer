"""
File: patterns.py
Purpose: Read-only queries over learned error patterns.
Category: Utility
Author: artdaq team
Depends: None
Exports: PatternQueriesMixin
Complexity: Medium | Lines: 90
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any
import aiosqlite
from ._state import StoreState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class PatternQueriesMixin(StoreState):

    async def list_patterns(self, active_only: bool=True, min_confidence: float | None=None, min_times_seen: int | None=None, limit: int=50, offset: int=0) -> tuple[list[dict[str, Any]], int]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            conditions = []
            params: list[Any] = []
            if active_only:
                conditions.append('is_active = TRUE')
            if min_confidence is not None:
                conditions.append('pattern_confidence >= ?')
                params.append(min_confidence)
            if min_times_seen is not None:
                conditions.append('times_seen >= ?')
                params.append(min_times_seen)
            where_clause = ' AND '.join(conditions) if conditions else '1=1'
            count_query = f'SELECT COUNT(*) FROM error_patterns WHERE {where_clause}'
            async with conn.execute(count_query, params) as cursor:
                row = await cursor.fetchone()
                total = row[0] if row else 0
            query = f'\n                SELECT * FROM error_patterns\n                WHERE {where_clause}\n                ORDER BY pattern_confidence DESC, times_seen DESC\n                LIMIT ? OFFSET ?\n            '
            params.extend([limit, offset])
            async with conn.execute(query, params) as cursor:
                patterns = []
                async for row in cursor:
                    patterns.append({'id': row['id'], 'signature_function': row['signature_function'], 'signature_message_pattern': row['signature_message_pattern'], 'signature_level': row['signature_level'], 'pattern_confidence': row['pattern_confidence'], 'times_seen': row['times_seen'], 'times_correct': row['times_correct'], 'times_incorrect': row['times_incorrect'], 'is_active': bool(row['is_active']), 'first_seen': row['first_seen'], 'last_seen': row['last_seen']})
        return (patterns, total)

    async def get_pattern(self, pattern_id: str) -> dict[str, Any] | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM error_patterns WHERE id = ?', (pattern_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                root_causes = []
                async with conn.execute('''SELECT * FROM root_cause_patterns
                    WHERE error_pattern_id = ?
                    ORDER BY frequency DESC''', (pattern_id,)) as rc_cursor:
                    async for rc_row in rc_cursor:
                        root_causes.append({'id': rc_row['id'], 'description': rc_row['description'], 'frequency': rc_row['frequency'], 'typical_fix': rc_row['typical_fix']})
                return {'id': row['id'], 'signature_function': row['signature_function'], 'signature_message_pattern': row['signature_message_pattern'], 'signature_level': row['signature_level'], 'pattern_confidence': row['pattern_confidence'], 'times_seen': row['times_seen'], 'times_correct': row['times_correct'], 'times_incorrect': row['times_incorrect'], 'is_active': bool(row['is_active']), 'first_seen': row['first_seen'], 'last_seen': row['last_seen'], 'root_causes': root_causes}

    async def get_pattern_statistics(self) -> dict[str, Any]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            stats: dict[str, Any] = {}
            async with conn.execute('SELECT COUNT(*) FROM error_patterns') as cursor:
                row = await cursor.fetchone()
                stats['total_patterns'] = row[0] if row else 0
            async with conn.execute('SELECT COUNT(*) FROM error_patterns WHERE is_active = TRUE') as cursor:
                row = await cursor.fetchone()
                stats['active_patterns'] = row[0] if row else 0
            async with conn.execute('SELECT AVG(pattern_confidence) FROM error_patterns WHERE is_active = TRUE') as cursor:
                row = await cursor.fetchone()
                result = row[0] if row else None
                stats['average_confidence'] = result if result else 0.0
            async with conn.execute('''
                SELECT
                    SUM(CASE WHEN times_correct > times_incorrect THEN 1 ELSE 0 END),
                    SUM(CASE WHEN times_correct <= times_incorrect THEN 1 ELSE 0 END)
                FROM error_patterns
                WHERE is_active = TRUE AND times_seen >= 5
                ''') as cursor:
                row = await cursor.fetchone()
                if row:
                    stats['high_accuracy_patterns'] = row[0] if row[0] else 0
                    stats['low_accuracy_patterns'] = row[1] if row[1] else 0
                else:
                    stats['high_accuracy_patterns'] = 0
                    stats['low_accuracy_patterns'] = 0
            async with conn.execute('SELECT COUNT(*) FROM root_cause_patterns') as cursor:
                row = await cursor.fetchone()
                stats['root_cause_patterns'] = row[0] if row else 0
            async with conn.execute('SELECT SUM(times_seen) FROM error_patterns WHERE is_active = TRUE') as cursor:
                row = await cursor.fetchone()
                result = row[0] if row else None
                stats['total_pattern_matches'] = result if result else 0
        return stats