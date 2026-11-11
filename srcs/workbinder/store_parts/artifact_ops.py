"""
File: artifact_ops.py
Purpose: Artifact create/update/delete/restore and generic queries.
Category: Utility
Author: artdaq team
Depends: base
Exports: ArtifactOpsMixin
Complexity: High | Lines: 262
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
import aiosqlite
from srcs.models.base import generate_id
from ..artifacts import Artifact
from ._helpers import _json_serializer
from ._state import StoreState
if TYPE_CHECKING:
    from ..binder import WorkBinder
logger = logging.getLogger(__name__)

class ArtifactOpsMixin(StoreState):

    async def add_artifact(self, binder_id: str, artifact: Artifact) -> str:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            await self._save_artifact(conn, binder_id, artifact)
            await conn.execute('''
                INSERT INTO artifact_history
                (id, artifact_id, modified_by, modified_at, action, changes_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (generate_id(), artifact.id, artifact.created_by, datetime.now().isoformat(), 'create', json.dumps({'artifact': artifact.model_dump(mode='json')}, default=_json_serializer)))
            await conn.execute('UPDATE work_binders SET updated_at = ? WHERE id = ?', (datetime.now().isoformat(), binder_id))
            await conn.commit()
        return artifact.id

    async def update_artifact(self, artifact_id: str, updates: dict[str, Any], modified_by: str) -> bool:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM binder_artifacts WHERE id = ?', (artifact_id,)) as cursor:
                row = await cursor.fetchone()
            if not row:
                return False
            content = json.loads(row['content_json'])
            before = {}
            for key, value in updates.items():
                if key in content:
                    before[key] = content[key]
                    content[key] = value
                elif key == 'tags':
                    before[key] = json.loads(row['tags_json']) if row['tags_json'] else []
            await conn.execute('''
                UPDATE binder_artifacts
                SET content_json = ?, updated_at = ?, tags_json = ?
                WHERE id = ?
                ''', (json.dumps(content, default=_json_serializer), datetime.now().isoformat(), json.dumps(updates.get('tags', json.loads(row['tags_json'] or '[]'))), artifact_id))
            if 'tags' in updates:
                await conn.execute('DELETE FROM artifact_tags WHERE artifact_id = ?', (artifact_id,))
                for tag in updates['tags']:
                    await conn.execute('INSERT OR IGNORE INTO artifact_tags (artifact_id, tag) VALUES (?, ?)', (artifact_id, tag))
            await conn.execute('''
                INSERT INTO artifact_history
                (id, artifact_id, modified_by, modified_at, action, changes_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (generate_id(), artifact_id, modified_by, datetime.now().isoformat(), 'update', json.dumps({'before': before, 'after': updates}, default=_json_serializer)))
            await conn.commit()
        return True

    async def delete_artifact(self, artifact_id: str, deleted_by: str, reason: str | None=None) -> bool:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            result = await conn.execute('''
                UPDATE binder_artifacts
                SET is_deleted = TRUE, deleted_by = ?, deleted_reason = ?, updated_at = ?
                WHERE id = ?
                ''', (deleted_by, reason, datetime.now().isoformat(), artifact_id))
            if result.rowcount == 0:
                return False
            await conn.execute('''
                INSERT INTO artifact_history
                (id, artifact_id, modified_by, modified_at, action, changes_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (generate_id(), artifact_id, deleted_by, datetime.now().isoformat(), 'delete', json.dumps({'reason': reason}, default=_json_serializer)))
            await conn.commit()
        return True

    async def restore_artifact(self, artifact_id: str, restored_by: str) -> bool:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            result = await conn.execute('''
                UPDATE binder_artifacts
                SET is_deleted = FALSE, deleted_by = NULL, deleted_reason = NULL,
                    updated_at = ?
                WHERE id = ?
                ''', (datetime.now().isoformat(), artifact_id))
            if result.rowcount == 0:
                return False
            await conn.execute('''
                INSERT INTO artifact_history
                (id, artifact_id, modified_by, modified_at, action, changes_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ''', (generate_id(), artifact_id, restored_by, datetime.now().isoformat(), 'restore', json.dumps({}, default=_json_serializer)))
            await conn.commit()
        return True

    async def get_artifact_by_id(self, binder_id: str, artifact_id: str) -> Artifact | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM binder_artifacts WHERE id = ? AND binder_id = ?', (artifact_id, binder_id)) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_artifact(row)

    async def query_artifacts(self, binder_id: str, artifact_type: str | None=None, phase: int | None=None, function_name: str | None=None, tags: list[str] | None=None, priority: str | None=None, include_deleted: bool=False, limit: int=100, offset: int=0) -> list[Artifact]:
        await self._ensure_initialized()
        query = 'SELECT * FROM binder_artifacts WHERE binder_id = ?'
        params: list[Any] = [binder_id]
        if not include_deleted:
            query += ' AND is_deleted = FALSE'
        if artifact_type:
            query += ' AND artifact_type = ?'
            params.append(artifact_type)
        if phase is not None:
            query += ' AND phase = ?'
            params.append(phase)
        if function_name:
            query += ' AND function_name = ?'
            params.append(function_name)
        if priority:
            query += ' AND priority = ?'
            params.append(priority)
        if tags:
            tag_placeholders = ','.join('?' * len(tags))
            query += f'\n                AND id IN (\n                    SELECT artifact_id FROM artifact_tags\n                    WHERE tag IN ({tag_placeholders})\n                    GROUP BY artifact_id\n                    HAVING COUNT(DISTINCT tag) = ?\n                )\n            '
            params.extend(tags)
            params.append(len(tags))
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, params) as cursor:
                artifacts = []
                async for row in cursor:
                    artifact = self._row_to_artifact(row)
                    if artifact:
                        artifacts.append(artifact)
                return artifacts

    async def list_binders(self, status: str | None=None, limit: int=100) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        query = 'SELECT * FROM work_binders'
        params: list[Any] = []
        if status:
            query += ' WHERE status = ?'
            params.append(status)
        query += ' ORDER BY updated_at DESC LIMIT ?'
        params.append(limit)
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, params) as cursor:
                binders = []
                async for row in cursor:
                    binders.append({'id': row['id'], 'investigation_id': row['investigation_id'], 'created_at': row['created_at'], 'updated_at': row['updated_at'], 'status': row['status']})
                return binders

    async def get_artifact_count(self, binder_id: str) -> dict[str, int]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute('''
                SELECT artifact_type, COUNT(*) as count
                FROM binder_artifacts
                WHERE binder_id = ? AND is_deleted = FALSE
                GROUP BY artifact_type
                ''', (binder_id,)) as cursor:
                counts = {}
                async for row in cursor:
                    counts[row[0]] = row[1]
                return counts

    async def search_artifacts(self, binder_id: str, query: str, artifact_types: list[str] | None=None) -> list[Artifact]:
        await self._ensure_initialized()
        sql = '''
            SELECT * FROM binder_artifacts
            WHERE binder_id = ? AND is_deleted = FALSE
            AND content_json LIKE ?
        '''
        params: list[Any] = [binder_id, f'%{query}%']
        if artifact_types:
            placeholders = ','.join('?' * len(artifact_types))
            sql += f' AND artifact_type IN ({placeholders})'
            params.extend(artifact_types)
        sql += ' ORDER BY created_at DESC LIMIT 50'
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(sql, params) as cursor:
                artifacts = []
                async for row in cursor:
                    artifact = self._row_to_artifact(row)
                    if artifact:
                        artifacts.append(artifact)
                return artifacts

    async def load_for_resume(self, investigation_id: str) -> tuple[WorkBinder, int, dict[str, Any]]:
        binder = await self.load_binder_for_investigation(investigation_id)
        if not binder:
            raise ValueError(f'No binder found for investigation: {investigation_id}')
        if not binder.can_resume():
            raise ValueError(f'Investigation {investigation_id} is not in paused state')
        resume_phase, resume_context = binder.get_resume_point()
        return (binder, resume_phase, resume_context)

    async def list_resumable_investigations(self) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM work_binders WHERE status = 'paused' ORDER BY updated_at DESC") as cursor:
                binders = []
                async for row in cursor:
                    binders.append({'binder_id': row['id'], 'investigation_id': row['investigation_id'], 'created_at': row['created_at'], 'updated_at': row['updated_at'], 'status': row['status']})
                return binders

    async def get_investigation_summary(self, investigation_id: str) -> dict[str, Any] | None:
        binder = await self.load_binder_for_investigation(investigation_id)
        if not binder:
            return None
        state = binder.get_investigation_state()
        counts = binder.count_by_type()
        return {'binder_id': binder.id, 'investigation_id': binder.investigation_id, 'status': binder.status, 'current_phase': state.current_phase if state else 0, 'outcome': state.outcome if state else None, 'resume_count': state.resume_count if state else 0, 'artifact_counts': counts, 'created_at': binder.created_at.isoformat(), 'updated_at': binder.updated_at.isoformat()}

    async def delete_binder(self, binder_id: str, hard: bool=False) -> tuple[int, int]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            if hard:
                async with conn.execute('SELECT COUNT(*) FROM binder_artifacts WHERE binder_id = ?', (binder_id,)) as cursor:
                    row = await cursor.fetchone()
                    artifacts_count = row[0] if row else 0
                async with conn.execute('''SELECT COUNT(*) FROM artifact_history
                    WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)''', (binder_id,)) as cursor:
                    row = await cursor.fetchone()
                    history_count = row[0] if row else 0
                await conn.execute('''DELETE FROM artifact_tags
                    WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)''', (binder_id,))
                await conn.execute('''DELETE FROM artifact_annotations
                    WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)''', (binder_id,))
                await conn.execute('''DELETE FROM artifact_history
                    WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)''', (binder_id,))
                await conn.execute('DELETE FROM binder_artifacts WHERE binder_id = ?', (binder_id,))
                await conn.execute('DELETE FROM work_binders WHERE id = ?', (binder_id,))
                await conn.commit()
                return (artifacts_count, history_count)
            else:
                result = await conn.execute("""UPDATE binder_artifacts
                    SET is_deleted = TRUE, deleted_by = 'binder-inspect',
                        deleted_reason = 'Binder deleted', updated_at = ?
                    WHERE binder_id = ? AND is_deleted = FALSE""", (datetime.now().isoformat(), binder_id))
                artifacts_count = result.rowcount
                await conn.execute("UPDATE work_binders SET status = 'archived', updated_at = ? WHERE id = ?", (datetime.now().isoformat(), binder_id))
                await conn.commit()
                return (artifacts_count, 0)

    async def get_binder_id_for_investigation(self, investigation_id: str) -> str | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute('SELECT id FROM work_binders WHERE investigation_id = ? LIMIT 1', (investigation_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None