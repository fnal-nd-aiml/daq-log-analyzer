"""
File: calibration.py
Purpose: Read-only queries over model calibration records.
Category: Utility
Author: artdaq team
Depends: None
Exports: CalibrationQueriesMixin
Complexity: Low | Lines: 41
"""

from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING, Any
import aiosqlite
from ._state import StoreState
if TYPE_CHECKING:
    pass
logger = logging.getLogger(__name__)

class CalibrationQueriesMixin(StoreState):

    async def list_calibrations(self, limit: int=50) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('''SELECT * FROM model_calibration
                ORDER BY sample_size DESC
                LIMIT ?''', (limit,)) as cursor:
                calibrations = []
                async for row in cursor:
                    buckets = json.loads(row['buckets_json']) if row['buckets_json'] else {}
                    calibrations.append({'id': row['id'], 'model_name': row['model_name'], 'error_type': row['error_type'], 'overall_bias': row['overall_bias'], 'sample_size': row['sample_size'], 'bucket_count': len(buckets), 'last_updated': row['last_updated']})
                return calibrations

    async def get_calibration(self, model: str, error_type: str | None=None) -> dict[str, Any] | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if error_type:
                query = 'SELECT * FROM model_calibration WHERE model_name = ? AND error_type = ?'
                params: tuple[str, ...] = (model, error_type)
            else:
                query = 'SELECT * FROM model_calibration WHERE model_name = ? AND error_type IS NULL'
                params = (model,)
            async with conn.execute(query, params) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                buckets = json.loads(row['buckets_json']) if row['buckets_json'] else {}
                return {'id': row['id'], 'model_name': row['model_name'], 'error_type': row['error_type'], 'overall_bias': row['overall_bias'], 'sample_size': row['sample_size'], 'buckets': buckets, 'last_updated': row['last_updated']}