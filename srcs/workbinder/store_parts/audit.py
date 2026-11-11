"""
File: audit.py
Purpose: Audit log retrieval.
Category: Utility
Author: artdaq team
Depends: None
Exports: AuditQueriesMixin
Complexity: Low | Lines: 43
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
import aiosqlite
from ..artifacts import AuditLogEntry
from ._state import StoreState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class AuditQueriesMixin(StoreState):

    async def get_audit_log(self, binder_id: str, persona_name: str | None=None, phase_number: int | None=None, operation_type: str | None=None, limit: int=100) -> list[AuditLogEntry]:
        await self._ensure_initialized()
        query = 'SELECT * FROM binder_audit_log WHERE binder_id = ?'
        params: list[Any] = [binder_id]
        if persona_name:
            query += ' AND persona_name = ?'
            params.append(persona_name)
        if phase_number is not None:
            query += ' AND phase_number = ?'
            params.append(phase_number)
        if operation_type:
            query += ' AND operation_type = ?'
            params.append(operation_type)
        query += ' ORDER BY access_sequence LIMIT ?'
        params.append(limit)
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, params) as cursor:
                entries = []
                async for row in cursor:
                    entry = AuditLogEntry(id=row['id'], persona_name=row['persona_name'], phase_number=row['phase_number'], timestamp=datetime.fromisoformat(row['timestamp']), access_sequence=row['access_sequence'], operation_type=row['operation_type'], artifact_type=row['artifact_type'], artifact_id=row['artifact_id'], method_name=row['method_name'], result_count=row['result_count'], success=bool(row['success']))
                    entries.append(entry)
                return entries

    async def get_audit_log_count(self, binder_id: str) -> int:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute('SELECT COUNT(*) FROM binder_audit_log WHERE binder_id = ?', (binder_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0