"""
File: binder_io.py
Purpose: Saving, loading and validating whole binders.
Category: Utility
Author: artdaq team
Depends: None
Exports: BinderIoMixin
Complexity: Medium | Lines: 166
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING
import aiosqlite
from ..artifacts import Annotation, Artifact, ArtifactHistory, ArtifactType, AuditLogEntry, Priority
from ._helpers import _json_serializer
from ._state import StoreState
if TYPE_CHECKING:
    from ..binder import WorkBinder
logger = logging.getLogger(__name__)

class BinderIoMixin(StoreState):

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            async with aiosqlite.connect(self._db_path) as conn:
                await conn.executescript(self.SCHEMA)
                await conn.commit()
            self._initialized = True

    async def save_binder(self, binder: WorkBinder) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute('''
                INSERT OR REPLACE INTO work_binders
                (id, investigation_id, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?)
                ''', (binder.id, binder.investigation_id, binder.created_at.isoformat(), binder.updated_at.isoformat(), binder.status))
            for artifact in binder._artifacts.values():
                await self._save_artifact(conn, binder.id, artifact)
            for history in binder._history:
                await conn.execute('''
                    INSERT OR IGNORE INTO artifact_history
                    (id, artifact_id, modified_by, modified_at, action, changes_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ''', (history.id, history.artifact_id, history.modified_by, history.modified_at.isoformat(), history.action, json.dumps(history.changes, default=_json_serializer)))
            for entry in binder._audit_log:
                await conn.execute('''
                    INSERT OR IGNORE INTO binder_audit_log
                    (id, binder_id, persona_name, phase_number, timestamp,
                     access_sequence, operation_type, artifact_type, artifact_id,
                     method_name, result_count, success)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (entry.id, binder.id, entry.persona_name, entry.phase_number, entry.timestamp.isoformat(), entry.access_sequence, entry.operation_type, entry.artifact_type, entry.artifact_id, entry.method_name, entry.result_count, entry.success))
            await conn.commit()

    async def _save_artifact(self, conn: aiosqlite.Connection, binder_id: str, artifact: Artifact) -> None:
        content = artifact.model_dump(exclude={'id', 'artifact_type', 'created_by', 'created_at', 'updated_at', 'phase', 'function_name', 'priority', 'tags', 'is_deleted', 'deleted_by', 'deleted_reason'})
        await conn.execute('''
            INSERT OR REPLACE INTO binder_artifacts
            (id, binder_id, artifact_type, created_by, created_at, updated_at,
             phase, function_name, priority, tags_json, content_json,
             is_deleted, deleted_by, deleted_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (artifact.id, binder_id, artifact.artifact_type.value, artifact.created_by, artifact.created_at.isoformat(), artifact.updated_at.isoformat(), artifact.phase, artifact.function_name, artifact.priority.value, json.dumps(artifact.tags), json.dumps(content, default=_json_serializer), artifact.is_deleted, artifact.deleted_by, artifact.deleted_reason))
        await conn.execute('DELETE FROM artifact_tags WHERE artifact_id = ?', (artifact.id,))
        for tag in artifact.tags:
            await conn.execute('INSERT OR IGNORE INTO artifact_tags (artifact_id, tag) VALUES (?, ?)', (artifact.id, tag))
        if isinstance(artifact, Annotation):
            await conn.execute('''
                INSERT OR REPLACE INTO artifact_annotations
                (id, artifact_id, target_artifact_id, created_by, annotation_type,
                 content, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (artifact.id, artifact.id, artifact.target_artifact_id, artifact.created_by, artifact.annotation_type.value, artifact.annotation_content, artifact.created_at.isoformat()))

    async def load_binder(self, binder_id: str) -> WorkBinder | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT * FROM work_binders WHERE id = ?', (binder_id,)) as cursor:
                row = await cursor.fetchone()
            if not row:
                return None
            from ..binder import WorkBinder
            binder = WorkBinder(id=row['id'], investigation_id=row['investigation_id'], created_at=datetime.fromisoformat(row['created_at']), updated_at=datetime.fromisoformat(row['updated_at']), status=row['status'])
            async with conn.execute('SELECT * FROM binder_artifacts WHERE binder_id = ?', (binder_id,)) as cursor:
                async for artifact_row in cursor:
                    artifact = self._row_to_artifact(artifact_row)
                    if artifact:
                        binder.add_artifact(artifact, record_history=False)
            async with conn.execute('''
                SELECT * FROM artifact_history
                WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)
                ORDER BY modified_at
                ''', (binder_id,)) as cursor:
                async for history_row in cursor:
                    binder._history.append(ArtifactHistory(id=str(history_row['id']), artifact_id=history_row['artifact_id'], modified_by=history_row['modified_by'], modified_at=datetime.fromisoformat(history_row['modified_at']), action=history_row['action'], changes=json.loads(history_row['changes_json'])))
            async with conn.execute('''
                SELECT * FROM binder_audit_log
                WHERE binder_id = ?
                ORDER BY access_sequence
                ''', (binder_id,)) as cursor:
                max_sequence = 0
                async for audit_row in cursor:
                    entry = AuditLogEntry(id=audit_row['id'], persona_name=audit_row['persona_name'], phase_number=audit_row['phase_number'], timestamp=datetime.fromisoformat(audit_row['timestamp']), access_sequence=audit_row['access_sequence'], operation_type=audit_row['operation_type'], artifact_type=audit_row['artifact_type'], artifact_id=audit_row['artifact_id'], method_name=audit_row['method_name'], result_count=audit_row['result_count'], success=bool(audit_row['success']))
                    binder._audit_log.append(entry)
                    max_sequence = max(max_sequence, entry.access_sequence)
                binder._access_sequence = max_sequence
            return binder

    async def load_binder_for_investigation(self, investigation_id: str) -> WorkBinder | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute('SELECT id FROM work_binders WHERE investigation_id = ? LIMIT 1', (investigation_id,)) as cursor:
                row = await cursor.fetchone()
        if row:
            return await self.load_binder(row[0])
        return None

    def _row_to_artifact(self, row: aiosqlite.Row) -> Artifact | None:
        artifact_type = ArtifactType(row['artifact_type'])
        artifact_class = self.ARTIFACT_CLASSES.get(artifact_type)
        if not artifact_class:
            logger.warning(f'Unknown artifact type: {artifact_type}')
            return None
        content = json.loads(row['content_json'])
        content.update({'id': row['id'], 'artifact_type': artifact_type, 'created_by': row['created_by'], 'created_at': datetime.fromisoformat(row['created_at']), 'updated_at': datetime.fromisoformat(row['updated_at']), 'phase': row['phase'], 'function_name': row['function_name'], 'priority': Priority(row['priority']), 'tags': json.loads(row['tags_json']) if row['tags_json'] else [], 'is_deleted': bool(row['is_deleted']), 'deleted_by': row['deleted_by'], 'deleted_reason': row['deleted_reason']})
        artifact: Artifact = artifact_class.model_validate(content)
        return artifact

    async def validate_references(self, binder_id: str) -> list[str]:
        await self._ensure_initialized()
        errors: list[str] = []
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute('SELECT id FROM binder_artifacts WHERE binder_id = ? AND is_deleted = FALSE', (binder_id,)) as cursor:
                valid_ids = {row['id'] async for row in cursor}
            async with conn.execute('SELECT id, artifact_type, content_json FROM binder_artifacts WHERE binder_id = ? AND is_deleted = FALSE', (binder_id,)) as cursor:
                async for row in cursor:
                    artifact_id = row['id']
                    artifact_type = row['artifact_type']
                    content = json.loads(row['content_json'])
                    if artifact_type == 'hypothesis_artifact':
                        for ev_id in content.get('supporting_evidence_ids', []):
                            if ev_id and ev_id not in valid_ids:
                                errors.append(f"Hypothesis {artifact_id}: supporting_evidence_ids references non-existent artifact '{ev_id}'")
                        for ev_id in content.get('contradicting_evidence_ids', []):
                            if ev_id and ev_id not in valid_ids:
                                errors.append(f"Hypothesis {artifact_id}: contradicting_evidence_ids references non-existent artifact '{ev_id}'")
                    elif artifact_type == 'evidence_artifact':
                        target_hyp = content.get('targets_hypothesis_id')
                        if target_hyp and target_hyp not in valid_ids:
                            errors.append(f"Evidence {artifact_id}: targets_hypothesis_id references non-existent artifact '{target_hyp}'")
                    elif artifact_type == 'causal_chain':
                        hyp_id = content.get('hypothesis_id')
                        if hyp_id and hyp_id not in valid_ids:
                            errors.append(f"CausalChain {artifact_id}: hypothesis_id references non-existent artifact '{hyp_id}'")
                        for step in content.get('steps', []):
                            for ev_id in step.get('evidence_ids', []):
                                if ev_id and ev_id not in valid_ids:
                                    errors.append(f"CausalChain {artifact_id} step: evidence_ids references non-existent artifact '{ev_id}'")
                    elif artifact_type == 'challenge':
                        target_hyp = content.get('target_hypothesis_id')
                        if target_hyp and target_hyp not in valid_ids:
                            errors.append(f"Challenge {artifact_id}: target_hypothesis_id references non-existent artifact '{target_hyp}'")
                    elif artifact_type == 'annotation':
                        target = content.get('target_artifact_id')
                        if target and target not in valid_ids:
                            errors.append(f"Annotation {artifact_id}: target_artifact_id references non-existent artifact '{target}'")
        if errors:
            error_msg = f"Found {len(errors)} invalid artifact reference(s) in binder '{binder_id}':\n" + '\n'.join((f'  - {e}' for e in errors))
            raise ValueError(error_msg)
        return errors