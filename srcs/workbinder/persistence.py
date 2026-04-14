"""
File: persistence.py
Purpose: SQLite persistence for Work Binders.
Category: Utility
Author: artdaq team
Depends: base
Exports: BinderStore
Complexity: High | Lines: 1320
"""

from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any
import aiosqlite
from srcs.models.base import generate_id
from .artifacts import (
    Annotation,
    Artifact,
    ArtifactHistory,
    ArtifactType,
    AuditLogEntry,
    BoardReaderIdentificationArtifact,
    CallGraphNode,
    CausalChainArtifact,
    ChallengeArtifact,
    CodeSnippet,
    ConclusionArtifact,
    ErrorContextArtifact,
    EvidenceArtifact,
    FeedbackArtifact,
    Finding,
    FlowConfigArtifact,
    FunctionSummaryArtifact,
    HypothesisArtifact,
    InvestigationStateArtifact,
    LLMRequestArtifact,
    LLMResponseArtifact,
    LogBundleArtifact,
    MergedTimelineArtifact,
    PersonaContributionArtifact,
    PhaseStateArtifact,
    Priority,
    SourceLocationArtifact,
)
from .binder import WorkBinder

logger = logging.getLogger(__name__)


def _json_serializer(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "value"):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class BinderStore:
    SCHEMA = """
    -- Work binders table
    CREATE TABLE IF NOT EXISTS work_binders (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        status TEXT DEFAULT 'active'
    );

    -- Artifacts table (polymorphic with soft delete)
    CREATE TABLE IF NOT EXISTS binder_artifacts (
        id TEXT PRIMARY KEY,
        binder_id TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        created_by TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        phase INTEGER,
        function_name TEXT,
        priority TEXT DEFAULT 'normal',
        tags_json TEXT,
        content_json TEXT NOT NULL,
        is_deleted BOOLEAN DEFAULT FALSE,
        deleted_by TEXT,
        deleted_reason TEXT,
        FOREIGN KEY (binder_id) REFERENCES work_binders(id) ON DELETE CASCADE
    );

    -- Artifact history table (tracks all modifications)
    CREATE TABLE IF NOT EXISTS artifact_history (
        id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL,
        modified_by TEXT NOT NULL,
        modified_at TIMESTAMP NOT NULL,
        action TEXT NOT NULL,
        changes_json TEXT NOT NULL,
        FOREIGN KEY (artifact_id) REFERENCES binder_artifacts(id) ON DELETE CASCADE
    );

    -- Tags table (many-to-many for efficient tag queries)
    CREATE TABLE IF NOT EXISTS artifact_tags (
        artifact_id TEXT NOT NULL,
        tag TEXT NOT NULL,
        PRIMARY KEY (artifact_id, tag),
        FOREIGN KEY (artifact_id) REFERENCES binder_artifacts(id) ON DELETE CASCADE
    );

    -- Annotations table (separate for efficient queries)
    CREATE TABLE IF NOT EXISTS artifact_annotations (
        id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL,
        target_artifact_id TEXT NOT NULL,
        created_by TEXT NOT NULL,
        annotation_type TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        FOREIGN KEY (artifact_id) REFERENCES binder_artifacts(id) ON DELETE CASCADE
    );

    -- Audit log table (tracks all artifact access for traceability)
    CREATE TABLE IF NOT EXISTS binder_audit_log (
        id TEXT PRIMARY KEY,
        binder_id TEXT NOT NULL,
        persona_name TEXT NOT NULL,
        phase_number INTEGER,
        timestamp TIMESTAMP NOT NULL,
        access_sequence INTEGER NOT NULL,
        operation_type TEXT NOT NULL,
        artifact_type TEXT NOT NULL,
        artifact_id TEXT,
        method_name TEXT NOT NULL,
        result_count INTEGER DEFAULT 1,
        success BOOLEAN DEFAULT TRUE,
        FOREIGN KEY (binder_id) REFERENCES work_binders(id) ON DELETE CASCADE
    );

    -- Indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_binder_artifacts_binder
        ON binder_artifacts(binder_id);
    CREATE INDEX IF NOT EXISTS idx_binder_artifacts_type
        ON binder_artifacts(artifact_type);
    CREATE INDEX IF NOT EXISTS idx_binder_artifacts_phase
        ON binder_artifacts(phase);
    CREATE INDEX IF NOT EXISTS idx_binder_artifacts_function
        ON binder_artifacts(function_name);
    CREATE INDEX IF NOT EXISTS idx_artifact_tags_tag
        ON artifact_tags(tag);
    CREATE INDEX IF NOT EXISTS idx_binders_investigation
        ON work_binders(investigation_id);
    CREATE INDEX IF NOT EXISTS idx_binders_status
        ON work_binders(status);
    CREATE INDEX IF NOT EXISTS idx_annotations_target
        ON artifact_annotations(target_artifact_id);
    CREATE INDEX IF NOT EXISTS idx_audit_log_binder
        ON binder_audit_log(binder_id);
    CREATE INDEX IF NOT EXISTS idx_audit_log_persona
        ON binder_audit_log(persona_name);
    CREATE INDEX IF NOT EXISTS idx_audit_log_phase
        ON binder_audit_log(phase_number);
    CREATE INDEX IF NOT EXISTS idx_audit_log_sequence
        ON binder_audit_log(binder_id, access_sequence);
    """
    ARTIFACT_CLASSES: dict[ArtifactType, type[Artifact]] = {
        ArtifactType.CALL_GRAPH: CallGraphNode,
        ArtifactType.CODE_SNIPPET: CodeSnippet,
        ArtifactType.FINDING: Finding,
        ArtifactType.ANNOTATION: Annotation,
        ArtifactType.SOURCE_LOCATION: SourceLocationArtifact,
        ArtifactType.ERROR_CONTEXT: ErrorContextArtifact,
        ArtifactType.LLM_REQUEST: LLMRequestArtifact,
        ArtifactType.LLM_RESPONSE: LLMResponseArtifact,
        ArtifactType.FLOW_CONFIG: FlowConfigArtifact,
        ArtifactType.PHASE_STATE: PhaseStateArtifact,
        ArtifactType.INVESTIGATION_STATE: InvestigationStateArtifact,
        ArtifactType.PERSONA_CONTRIBUTION: PersonaContributionArtifact,
        ArtifactType.HYPOTHESIS_ARTIFACT: HypothesisArtifact,
        ArtifactType.EVIDENCE_ARTIFACT: EvidenceArtifact,
        ArtifactType.CAUSAL_CHAIN: CausalChainArtifact,
        ArtifactType.CHALLENGE: ChallengeArtifact,
        ArtifactType.CONCLUSION: ConclusionArtifact,
        ArtifactType.FUNCTION_SUMMARY: FunctionSummaryArtifact,
        ArtifactType.LOG_BUNDLE: LogBundleArtifact,
        ArtifactType.MERGED_TIMELINE: MergedTimelineArtifact,
        ArtifactType.BOARDREADER_IDENTIFICATION: BoardReaderIdentificationArtifact,
        ArtifactType.FEEDBACK: FeedbackArtifact,
    }

    def __init__(self, db_path: Path | str):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            async with aiosqlite.connect(self._db_path) as conn:
                await conn.executescript(self.SCHEMA)
                await conn.commit()
            self._initialized = True

    async def save_binder(self, binder: WorkBinder) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO work_binders
                (id, investigation_id, created_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    binder.id,
                    binder.investigation_id,
                    binder.created_at.isoformat(),
                    binder.updated_at.isoformat(),
                    binder.status,
                ),
            )
            for artifact in binder._artifacts.values():
                await self._save_artifact(conn, binder.id, artifact)
            for history in binder._history:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO artifact_history
                    (id, artifact_id, modified_by, modified_at, action, changes_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        history.id,
                        history.artifact_id,
                        history.modified_by,
                        history.modified_at.isoformat(),
                        history.action,
                        json.dumps(history.changes, default=_json_serializer),
                    ),
                )
            for entry in binder._audit_log:
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO binder_audit_log
                    (id, binder_id, persona_name, phase_number, timestamp,
                     access_sequence, operation_type, artifact_type, artifact_id,
                     method_name, result_count, success)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        binder.id,
                        entry.persona_name,
                        entry.phase_number,
                        entry.timestamp.isoformat(),
                        entry.access_sequence,
                        entry.operation_type,
                        entry.artifact_type,
                        entry.artifact_id,
                        entry.method_name,
                        entry.result_count,
                        entry.success,
                    ),
                )
            await conn.commit()

    async def _save_artifact(self, conn: aiosqlite.Connection, binder_id: str, artifact: Artifact) -> None:
        content = artifact.model_dump(
            exclude={
                "id",
                "artifact_type",
                "created_by",
                "created_at",
                "updated_at",
                "phase",
                "function_name",
                "priority",
                "tags",
                "is_deleted",
                "deleted_by",
                "deleted_reason",
            }
        )
        await conn.execute(
            """
            INSERT OR REPLACE INTO binder_artifacts
            (id, binder_id, artifact_type, created_by, created_at, updated_at,
             phase, function_name, priority, tags_json, content_json,
             is_deleted, deleted_by, deleted_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.id,
                binder_id,
                artifact.artifact_type.value,
                artifact.created_by,
                artifact.created_at.isoformat(),
                artifact.updated_at.isoformat(),
                artifact.phase,
                artifact.function_name,
                artifact.priority.value,
                json.dumps(artifact.tags),
                json.dumps(content, default=_json_serializer),
                artifact.is_deleted,
                artifact.deleted_by,
                artifact.deleted_reason,
            ),
        )
        await conn.execute("DELETE FROM artifact_tags WHERE artifact_id = ?", (artifact.id,))
        for tag in artifact.tags:
            await conn.execute(
                "INSERT OR IGNORE INTO artifact_tags (artifact_id, tag) VALUES (?, ?)", (artifact.id, tag)
            )
        if isinstance(artifact, Annotation):
            await conn.execute(
                """
                INSERT OR REPLACE INTO artifact_annotations
                (id, artifact_id, target_artifact_id, created_by, annotation_type,
                 content, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.id,
                    artifact.id,
                    artifact.target_artifact_id,
                    artifact.created_by,
                    artifact.annotation_type.value,
                    artifact.annotation_content,
                    artifact.created_at.isoformat(),
                ),
            )

    async def load_binder(self, binder_id: str) -> WorkBinder | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM work_binders WHERE id = ?", (binder_id,)) as cursor:
                row = await cursor.fetchone()
            if not row:
                return None
            binder = WorkBinder(
                id=row["id"],
                investigation_id=row["investigation_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                status=row["status"],
            )
            async with conn.execute("SELECT * FROM binder_artifacts WHERE binder_id = ?", (binder_id,)) as cursor:
                async for artifact_row in cursor:
                    artifact = self._row_to_artifact(artifact_row)
                    if artifact:
                        binder.add_artifact(artifact, record_history=False)
            async with conn.execute(
                """
                SELECT * FROM artifact_history
                WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)
                ORDER BY modified_at
                """,
                (binder_id,),
            ) as cursor:
                async for history_row in cursor:
                    binder._history.append(
                        ArtifactHistory(
                            id=str(history_row["id"]),
                            artifact_id=history_row["artifact_id"],
                            modified_by=history_row["modified_by"],
                            modified_at=datetime.fromisoformat(history_row["modified_at"]),
                            action=history_row["action"],
                            changes=json.loads(history_row["changes_json"]),
                        )
                    )
            async with conn.execute(
                """
                SELECT * FROM binder_audit_log
                WHERE binder_id = ?
                ORDER BY access_sequence
                """,
                (binder_id,),
            ) as cursor:
                max_sequence = 0
                async for audit_row in cursor:
                    entry = AuditLogEntry(
                        id=audit_row["id"],
                        persona_name=audit_row["persona_name"],
                        phase_number=audit_row["phase_number"],
                        timestamp=datetime.fromisoformat(audit_row["timestamp"]),
                        access_sequence=audit_row["access_sequence"],
                        operation_type=audit_row["operation_type"],
                        artifact_type=audit_row["artifact_type"],
                        artifact_id=audit_row["artifact_id"],
                        method_name=audit_row["method_name"],
                        result_count=audit_row["result_count"],
                        success=bool(audit_row["success"]),
                    )
                    binder._audit_log.append(entry)
                    max_sequence = max(max_sequence, entry.access_sequence)
                binder._access_sequence = max_sequence
            return binder

    async def load_binder_for_investigation(self, investigation_id: str) -> WorkBinder | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute(
                "SELECT id FROM work_binders WHERE investigation_id = ? LIMIT 1", (investigation_id,)
            ) as cursor:
                row = await cursor.fetchone()
        if row:
            return await self.load_binder(row[0])
        return None

    def _row_to_artifact(self, row: aiosqlite.Row) -> Artifact | None:
        artifact_type = ArtifactType(row["artifact_type"])
        artifact_class = self.ARTIFACT_CLASSES.get(artifact_type)
        if not artifact_class:
            logger.warning(f"Unknown artifact type: {artifact_type}")
            return None
        content = json.loads(row["content_json"])
        content.update(
            {
                "id": row["id"],
                "artifact_type": artifact_type,
                "created_by": row["created_by"],
                "created_at": datetime.fromisoformat(row["created_at"]),
                "updated_at": datetime.fromisoformat(row["updated_at"]),
                "phase": row["phase"],
                "function_name": row["function_name"],
                "priority": Priority(row["priority"]),
                "tags": json.loads(row["tags_json"]) if row["tags_json"] else [],
                "is_deleted": bool(row["is_deleted"]),
                "deleted_by": row["deleted_by"],
                "deleted_reason": row["deleted_reason"],
            }
        )
        return artifact_class.model_validate(content)

    async def validate_references(self, binder_id: str) -> list[str]:
        await self._ensure_initialized()
        errors: list[str] = []
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT id FROM binder_artifacts WHERE binder_id = ? AND is_deleted = FALSE", (binder_id,)
            ) as cursor:
                valid_ids = {row["id"] async for row in cursor}
            async with conn.execute(
                "SELECT id, artifact_type, content_json FROM binder_artifacts WHERE binder_id = ? AND is_deleted = FALSE",
                (binder_id,),
            ) as cursor:
                async for row in cursor:
                    artifact_id = row["id"]
                    artifact_type = row["artifact_type"]
                    content = json.loads(row["content_json"])
                    if artifact_type == "hypothesis_artifact":
                        for ev_id in content.get("supporting_evidence_ids", []):
                            if ev_id and ev_id not in valid_ids:
                                errors.append(
                                    f"Hypothesis {artifact_id}: supporting_evidence_ids references non-existent artifact '{ev_id}'"
                                )
                        for ev_id in content.get("contradicting_evidence_ids", []):
                            if ev_id and ev_id not in valid_ids:
                                errors.append(
                                    f"Hypothesis {artifact_id}: contradicting_evidence_ids references non-existent artifact '{ev_id}'"
                                )
                    elif artifact_type == "evidence_artifact":
                        target_hyp = content.get("targets_hypothesis_id")
                        if target_hyp and target_hyp not in valid_ids:
                            errors.append(
                                f"Evidence {artifact_id}: targets_hypothesis_id references non-existent artifact '{target_hyp}'"
                            )
                    elif artifact_type == "causal_chain":
                        hyp_id = content.get("hypothesis_id")
                        if hyp_id and hyp_id not in valid_ids:
                            errors.append(
                                f"CausalChain {artifact_id}: hypothesis_id references non-existent artifact '{hyp_id}'"
                            )
                        for step in content.get("steps", []):
                            for ev_id in step.get("evidence_ids", []):
                                if ev_id and ev_id not in valid_ids:
                                    errors.append(
                                        f"CausalChain {artifact_id} step: evidence_ids references non-existent artifact '{ev_id}'"
                                    )
                    elif artifact_type == "challenge":
                        target_hyp = content.get("target_hypothesis_id")
                        if target_hyp and target_hyp not in valid_ids:
                            errors.append(
                                f"Challenge {artifact_id}: target_hypothesis_id references non-existent artifact '{target_hyp}'"
                            )
                    elif artifact_type == "annotation":
                        target = content.get("target_artifact_id")
                        if target and target not in valid_ids:
                            errors.append(
                                f"Annotation {artifact_id}: target_artifact_id references non-existent artifact '{target}'"
                            )
        if errors:
            error_msg = f"Found {len(errors)} invalid artifact reference(s) in binder '{binder_id}':\n" + "\n".join(
                (f"  - {e}" for e in errors)
            )
            raise ValueError(error_msg)
        return errors

    async def add_artifact(self, binder_id: str, artifact: Artifact) -> str:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            await self._save_artifact(conn, binder_id, artifact)
            await conn.execute(
                """
                INSERT INTO artifact_history
                (id, artifact_id, modified_by, modified_at, action, changes_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    generate_id(),
                    artifact.id,
                    artifact.created_by,
                    datetime.now().isoformat(),
                    "create",
                    json.dumps({"artifact": artifact.model_dump(mode="json")}, default=_json_serializer),
                ),
            )
            await conn.execute(
                "UPDATE work_binders SET updated_at = ? WHERE id = ?", (datetime.now().isoformat(), binder_id)
            )
            await conn.commit()
        return artifact.id

    async def update_artifact(self, artifact_id: str, updates: dict[str, Any], modified_by: str) -> bool:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM binder_artifacts WHERE id = ?", (artifact_id,)) as cursor:
                row = await cursor.fetchone()
            if not row:
                return False
            content = json.loads(row["content_json"])
            before = {}
            for key, value in updates.items():
                if key in content:
                    before[key] = content[key]
                    content[key] = value
                elif key == "tags":
                    before[key] = json.loads(row["tags_json"]) if row["tags_json"] else []
            await conn.execute(
                """
                UPDATE binder_artifacts
                SET content_json = ?, updated_at = ?, tags_json = ?
                WHERE id = ?
                """,
                (
                    json.dumps(content, default=_json_serializer),
                    datetime.now().isoformat(),
                    json.dumps(updates.get("tags", json.loads(row["tags_json"] or "[]"))),
                    artifact_id,
                ),
            )
            if "tags" in updates:
                await conn.execute("DELETE FROM artifact_tags WHERE artifact_id = ?", (artifact_id,))
                for tag in updates["tags"]:
                    await conn.execute(
                        "INSERT OR IGNORE INTO artifact_tags (artifact_id, tag) VALUES (?, ?)", (artifact_id, tag)
                    )
            await conn.execute(
                """
                INSERT INTO artifact_history
                (id, artifact_id, modified_by, modified_at, action, changes_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    generate_id(),
                    artifact_id,
                    modified_by,
                    datetime.now().isoformat(),
                    "update",
                    json.dumps({"before": before, "after": updates}, default=_json_serializer),
                ),
            )
            await conn.commit()
        return True

    async def delete_artifact(self, artifact_id: str, deleted_by: str, reason: str | None = None) -> bool:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            result = await conn.execute(
                """
                UPDATE binder_artifacts
                SET is_deleted = TRUE, deleted_by = ?, deleted_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (deleted_by, reason, datetime.now().isoformat(), artifact_id),
            )
            if result.rowcount == 0:
                return False
            await conn.execute(
                """
                INSERT INTO artifact_history
                (id, artifact_id, modified_by, modified_at, action, changes_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    generate_id(),
                    artifact_id,
                    deleted_by,
                    datetime.now().isoformat(),
                    "delete",
                    json.dumps({"reason": reason}, default=_json_serializer),
                ),
            )
            await conn.commit()
        return True

    async def restore_artifact(self, artifact_id: str, restored_by: str) -> bool:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            result = await conn.execute(
                """
                UPDATE binder_artifacts
                SET is_deleted = FALSE, deleted_by = NULL, deleted_reason = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), artifact_id),
            )
            if result.rowcount == 0:
                return False
            await conn.execute(
                """
                INSERT INTO artifact_history
                (id, artifact_id, modified_by, modified_at, action, changes_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    generate_id(),
                    artifact_id,
                    restored_by,
                    datetime.now().isoformat(),
                    "restore",
                    json.dumps({}, default=_json_serializer),
                ),
            )
            await conn.commit()
        return True

    async def get_artifact_by_id(self, binder_id: str, artifact_id: str) -> Artifact | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM binder_artifacts WHERE id = ? AND binder_id = ?", (artifact_id, binder_id)
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_artifact(row)

    async def query_artifacts(
        self,
        binder_id: str,
        artifact_type: str | None = None,
        phase: int | None = None,
        function_name: str | None = None,
        tags: list[str] | None = None,
        priority: str | None = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Artifact]:
        await self._ensure_initialized()
        query = "SELECT * FROM binder_artifacts WHERE binder_id = ?"
        params: list[Any] = [binder_id]
        if not include_deleted:
            query += " AND is_deleted = FALSE"
        if artifact_type:
            query += " AND artifact_type = ?"
            params.append(artifact_type)
        if phase is not None:
            query += " AND phase = ?"
            params.append(phase)
        if function_name:
            query += " AND function_name = ?"
            params.append(function_name)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if tags:
            tag_placeholders = ",".join("?" * len(tags))
            query += f"\n                AND id IN (\n                    SELECT artifact_id FROM artifact_tags\n                    WHERE tag IN ({tag_placeholders})\n                    GROUP BY artifact_id\n                    HAVING COUNT(DISTINCT tag) = ?\n                )\n            "
            params.extend(tags)
            params.append(len(tags))
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
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

    async def list_binders(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        query = "SELECT * FROM work_binders"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, params) as cursor:
                binders = []
                async for row in cursor:
                    binders.append(
                        {
                            "id": row["id"],
                            "investigation_id": row["investigation_id"],
                            "created_at": row["created_at"],
                            "updated_at": row["updated_at"],
                            "status": row["status"],
                        }
                    )
                return binders

    async def get_artifact_count(self, binder_id: str) -> dict[str, int]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute(
                """
                SELECT artifact_type, COUNT(*) as count
                FROM binder_artifacts
                WHERE binder_id = ? AND is_deleted = FALSE
                GROUP BY artifact_type
                """,
                (binder_id,),
            ) as cursor:
                counts = {}
                async for row in cursor:
                    counts[row[0]] = row[1]
                return counts

    async def search_artifacts(
        self, binder_id: str, query: str, artifact_types: list[str] | None = None
    ) -> list[Artifact]:
        await self._ensure_initialized()
        sql = """
            SELECT * FROM binder_artifacts
            WHERE binder_id = ? AND is_deleted = FALSE
            AND content_json LIKE ?
        """
        params: list[Any] = [binder_id, f"%{query}%"]
        if artifact_types:
            placeholders = ",".join("?" * len(artifact_types))
            sql += f" AND artifact_type IN ({placeholders})"
            params.extend(artifact_types)
        sql += " ORDER BY created_at DESC LIMIT 50"
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
            raise ValueError(f"No binder found for investigation: {investigation_id}")
        if not binder.can_resume():
            raise ValueError(f"Investigation {investigation_id} is not in paused state")
        resume_phase, resume_context = binder.get_resume_point()
        return (binder, resume_phase, resume_context)

    async def list_resumable_investigations(self) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM work_binders WHERE status = 'paused' ORDER BY updated_at DESC"
            ) as cursor:
                binders = []
                async for row in cursor:
                    binders.append(
                        {
                            "binder_id": row["id"],
                            "investigation_id": row["investigation_id"],
                            "created_at": row["created_at"],
                            "updated_at": row["updated_at"],
                            "status": row["status"],
                        }
                    )
                return binders

    async def get_investigation_summary(self, investigation_id: str) -> dict[str, Any] | None:
        binder = await self.load_binder_for_investigation(investigation_id)
        if not binder:
            return None
        state = binder.get_investigation_state()
        counts = binder.count_by_type()
        return {
            "binder_id": binder.id,
            "investigation_id": binder.investigation_id,
            "status": binder.status,
            "current_phase": state.current_phase if state else 0,
            "outcome": state.outcome if state else None,
            "resume_count": state.resume_count if state else 0,
            "artifact_counts": counts,
            "created_at": binder.created_at.isoformat(),
            "updated_at": binder.updated_at.isoformat(),
        }

    async def delete_binder(self, binder_id: str, hard: bool = False) -> tuple[int, int]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            if hard:
                async with conn.execute(
                    "SELECT COUNT(*) FROM binder_artifacts WHERE binder_id = ?", (binder_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    artifacts_count = row[0] if row else 0
                async with conn.execute(
                    """SELECT COUNT(*) FROM artifact_history
                    WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)""",
                    (binder_id,),
                ) as cursor:
                    row = await cursor.fetchone()
                    history_count = row[0] if row else 0
                await conn.execute(
                    """DELETE FROM artifact_tags
                    WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)""",
                    (binder_id,),
                )
                await conn.execute(
                    """DELETE FROM artifact_annotations
                    WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)""",
                    (binder_id,),
                )
                await conn.execute(
                    """DELETE FROM artifact_history
                    WHERE artifact_id IN (SELECT id FROM binder_artifacts WHERE binder_id = ?)""",
                    (binder_id,),
                )
                await conn.execute("DELETE FROM binder_artifacts WHERE binder_id = ?", (binder_id,))
                await conn.execute("DELETE FROM work_binders WHERE id = ?", (binder_id,))
                await conn.commit()
                return (artifacts_count, history_count)
            else:
                result = await conn.execute(
                    """UPDATE binder_artifacts
                    SET is_deleted = TRUE, deleted_by = 'binder-inspect',
                        deleted_reason = 'Binder deleted', updated_at = ?
                    WHERE binder_id = ? AND is_deleted = FALSE""",
                    (datetime.now().isoformat(), binder_id),
                )
                artifacts_count = result.rowcount
                await conn.execute(
                    "UPDATE work_binders SET status = 'archived', updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), binder_id),
                )
                await conn.commit()
                return (artifacts_count, 0)

    async def get_binder_id_for_investigation(self, investigation_id: str) -> str | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute(
                "SELECT id FROM work_binders WHERE investigation_id = ? LIMIT 1", (investigation_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def get_audit_log(
        self,
        binder_id: str,
        persona_name: str | None = None,
        phase_number: int | None = None,
        operation_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        await self._ensure_initialized()
        query = "SELECT * FROM binder_audit_log WHERE binder_id = ?"
        params: list[Any] = [binder_id]
        if persona_name:
            query += " AND persona_name = ?"
            params.append(persona_name)
        if phase_number is not None:
            query += " AND phase_number = ?"
            params.append(phase_number)
        if operation_type:
            query += " AND operation_type = ?"
            params.append(operation_type)
        query += " ORDER BY access_sequence LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(query, params) as cursor:
                entries = []
                async for row in cursor:
                    entry = AuditLogEntry(
                        id=row["id"],
                        persona_name=row["persona_name"],
                        phase_number=row["phase_number"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        access_sequence=row["access_sequence"],
                        operation_type=row["operation_type"],
                        artifact_type=row["artifact_type"],
                        artifact_id=row["artifact_id"],
                        method_name=row["method_name"],
                        result_count=row["result_count"],
                        success=bool(row["success"]),
                    )
                    entries.append(entry)
                return entries

    async def get_audit_log_count(self, binder_id: str) -> int:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM binder_audit_log WHERE binder_id = ?", (binder_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def list_patterns(
        self,
        active_only: bool = True,
        min_confidence: float | None = None,
        min_times_seen: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            conditions = []
            params: list[Any] = []
            if active_only:
                conditions.append("is_active = TRUE")
            if min_confidence is not None:
                conditions.append("pattern_confidence >= ?")
                params.append(min_confidence)
            if min_times_seen is not None:
                conditions.append("times_seen >= ?")
                params.append(min_times_seen)
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            count_query = f"SELECT COUNT(*) FROM error_patterns WHERE {where_clause}"
            async with conn.execute(count_query, params) as cursor:
                row = await cursor.fetchone()
                total = row[0] if row else 0
            query = f"\n                SELECT * FROM error_patterns\n                WHERE {where_clause}\n                ORDER BY pattern_confidence DESC, times_seen DESC\n                LIMIT ? OFFSET ?\n            "
            params.extend([limit, offset])
            async with conn.execute(query, params) as cursor:
                patterns = []
                async for row in cursor:
                    patterns.append(
                        {
                            "id": row["id"],
                            "signature_function": row["signature_function"],
                            "signature_message_pattern": row["signature_message_pattern"],
                            "signature_level": row["signature_level"],
                            "pattern_confidence": row["pattern_confidence"],
                            "times_seen": row["times_seen"],
                            "times_correct": row["times_correct"],
                            "times_incorrect": row["times_incorrect"],
                            "is_active": bool(row["is_active"]),
                            "first_seen": row["first_seen"],
                            "last_seen": row["last_seen"],
                        }
                    )
        return (patterns, total)

    async def get_pattern(self, pattern_id: str) -> dict[str, Any] | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM error_patterns WHERE id = ?", (pattern_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                root_causes = []
                async with conn.execute(
                    """SELECT * FROM root_cause_patterns
                    WHERE error_pattern_id = ?
                    ORDER BY frequency DESC""",
                    (pattern_id,),
                ) as rc_cursor:
                    async for rc_row in rc_cursor:
                        root_causes.append(
                            {
                                "id": rc_row["id"],
                                "description": rc_row["description"],
                                "frequency": rc_row["frequency"],
                                "typical_fix": rc_row["typical_fix"],
                            }
                        )
                return {
                    "id": row["id"],
                    "signature_function": row["signature_function"],
                    "signature_message_pattern": row["signature_message_pattern"],
                    "signature_level": row["signature_level"],
                    "pattern_confidence": row["pattern_confidence"],
                    "times_seen": row["times_seen"],
                    "times_correct": row["times_correct"],
                    "times_incorrect": row["times_incorrect"],
                    "is_active": bool(row["is_active"]),
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "root_causes": root_causes,
                }

    async def get_pattern_statistics(self) -> dict[str, Any]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            stats: dict[str, Any] = {}
            async with conn.execute("SELECT COUNT(*) FROM error_patterns") as cursor:
                row = await cursor.fetchone()
                stats["total_patterns"] = row[0] if row else 0
            async with conn.execute("SELECT COUNT(*) FROM error_patterns WHERE is_active = TRUE") as cursor:
                row = await cursor.fetchone()
                stats["active_patterns"] = row[0] if row else 0
            async with conn.execute(
                "SELECT AVG(pattern_confidence) FROM error_patterns WHERE is_active = TRUE"
            ) as cursor:
                row = await cursor.fetchone()
                result = row[0] if row else None
                stats["average_confidence"] = result if result else 0.0
            async with conn.execute(
                """
                SELECT
                    SUM(CASE WHEN times_correct > times_incorrect THEN 1 ELSE 0 END),
                    SUM(CASE WHEN times_correct <= times_incorrect THEN 1 ELSE 0 END)
                FROM error_patterns
                WHERE is_active = TRUE AND times_seen >= 5
                """
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    stats["high_accuracy_patterns"] = row[0] if row[0] else 0
                    stats["low_accuracy_patterns"] = row[1] if row[1] else 0
                else:
                    stats["high_accuracy_patterns"] = 0
                    stats["low_accuracy_patterns"] = 0
            async with conn.execute("SELECT COUNT(*) FROM root_cause_patterns") as cursor:
                row = await cursor.fetchone()
                stats["root_cause_patterns"] = row[0] if row else 0
            async with conn.execute("SELECT SUM(times_seen) FROM error_patterns WHERE is_active = TRUE") as cursor:
                row = await cursor.fetchone()
                result = row[0] if row else None
                stats["total_pattern_matches"] = result if result else 0
        return stats

    async def list_calibrations(self, limit: int = 50) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """SELECT * FROM model_calibration
                ORDER BY sample_size DESC
                LIMIT ?""",
                (limit,),
            ) as cursor:
                calibrations = []
                async for row in cursor:
                    buckets = json.loads(row["buckets_json"]) if row["buckets_json"] else {}
                    calibrations.append(
                        {
                            "id": row["id"],
                            "model_name": row["model_name"],
                            "error_type": row["error_type"],
                            "overall_bias": row["overall_bias"],
                            "sample_size": row["sample_size"],
                            "bucket_count": len(buckets),
                            "last_updated": row["last_updated"],
                        }
                    )
                return calibrations

    async def get_calibration(self, model: str, error_type: str | None = None) -> dict[str, Any] | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self._db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if error_type:
                query = "SELECT * FROM model_calibration WHERE model_name = ? AND error_type = ?"
                params: tuple[str, ...] = (model, error_type)
            else:
                query = "SELECT * FROM model_calibration WHERE model_name = ? AND error_type IS NULL"
                params = (model,)
            async with conn.execute(query, params) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                buckets = json.loads(row["buckets_json"]) if row["buckets_json"] else {}
                return {
                    "id": row["id"],
                    "model_name": row["model_name"],
                    "error_type": row["error_type"],
                    "overall_bias": row["overall_bias"],
                    "sample_size": row["sample_size"],
                    "buckets": buckets,
                    "last_updated": row["last_updated"],
                }

    async def get_hypotheses(
        self, binder_id: str, min_score: float | None = None, source: str | None = None, limit: int = 50
    ) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type="hypothesis_artifact", limit=limit)
        result = []
        for artifact in artifacts:
            if hasattr(artifact, "score") and min_score is not None:
                if artifact.score < min_score:
                    continue
            if hasattr(artifact, "source") and source is not None:
                if artifact.source != source:
                    continue
            result.append(artifact)
        return result

    async def get_evidence_items(
        self, binder_id: str, evidence_type: str | None = None, strength: str | None = None, limit: int = 100
    ) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type="evidence_artifact", limit=limit)
        result = []
        for artifact in artifacts:
            if hasattr(artifact, "evidence_type") and evidence_type is not None:
                if artifact.evidence_type != evidence_type:
                    continue
            if hasattr(artifact, "strength") and strength is not None:
                if artifact.strength != strength:
                    continue
            result.append(artifact)
        return result

    async def get_causal_chains(
        self, binder_id: str, hypothesis_id: str | None = None, limit: int = 20
    ) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type="causal_chain", limit=limit)
        if hypothesis_id is not None:
            result = []
            for artifact in artifacts:
                if hasattr(artifact, "hypothesis_id"):
                    if artifact.hypothesis_id == hypothesis_id:
                        result.append(artifact)
            return result
        return artifacts

    async def get_challenges(
        self, binder_id: str, resolved: bool | None = None, severity: str | None = None, limit: int = 50
    ) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type="challenge", limit=limit)
        result = []
        for artifact in artifacts:
            if resolved is not None and hasattr(artifact, "resolved"):
                if artifact.resolved != resolved:
                    continue
            if severity is not None and hasattr(artifact, "severity"):
                if artifact.severity != severity:
                    continue
            result.append(artifact)
        return result

    async def get_llm_requests(
        self,
        binder_id: str,
        persona: str | None = None,
        phase: int | None = None,
        prompt_key: str | None = None,
        limit: int = 100,
    ) -> list[Artifact]:
        artifacts = await self.query_artifacts(
            binder_id=binder_id, artifact_type="llm_request", phase=phase, limit=limit
        )
        result = []
        for artifact in artifacts:
            if persona is not None and hasattr(artifact, "persona"):
                if artifact.persona != persona:
                    continue
            if prompt_key is not None and hasattr(artifact, "prompt_key"):
                if artifact.prompt_key != prompt_key:
                    continue
            result.append(artifact)
        return result

    async def get_llm_responses(
        self,
        binder_id: str,
        request_id: str | None = None,
        phase: int | None = None,
        parse_success: bool | None = None,
        limit: int = 100,
    ) -> list[Artifact]:
        artifacts = await self.query_artifacts(
            binder_id=binder_id, artifact_type="llm_response", phase=phase, limit=limit
        )
        result = []
        for artifact in artifacts:
            if request_id is not None and hasattr(artifact, "request_id"):
                if artifact.request_id != request_id:
                    continue
            if parse_success is not None and hasattr(artifact, "parse_success"):
                if artifact.parse_success != parse_success:
                    continue
            result.append(artifact)
        return result

    async def get_llm_exchanges(
        self, binder_id: str, phase: int | None = None
    ) -> list[tuple[Artifact, Artifact | None]]:
        requests = await self.get_llm_requests(binder_id, phase=phase, limit=500)
        responses = await self.get_llm_responses(binder_id, phase=phase, limit=500)
        response_map: dict[str, Artifact] = {}
        for resp in responses:
            if hasattr(resp, "request_id") and resp.request_id:
                response_map[resp.request_id] = resp
        exchanges: list[tuple[Artifact, Artifact | None]] = []
        for req in requests:
            matched_resp: Artifact | None = response_map.get(req.id)
            exchanges.append((req, matched_resp))
        return exchanges

    async def get_llm_statistics(self, binder_id: str) -> dict[str, Any]:
        requests = await self.get_llm_requests(binder_id, limit=1000)
        responses = await self.get_llm_responses(binder_id, limit=1000)
        by_persona: dict[str, int] = {}
        by_phase: dict[int, int] = {}
        total_tokens = 0
        total_latency = 0.0
        parse_successes = 0
        parse_failures = 0
        for req in requests:
            if hasattr(req, "persona"):
                by_persona[req.persona] = by_persona.get(req.persona, 0) + 1
            if req.phase is not None:
                by_phase[req.phase] = by_phase.get(req.phase, 0) + 1
        for resp in responses:
            if hasattr(resp, "tokens_used") and resp.tokens_used:
                total_tokens += resp.tokens_used
            if hasattr(resp, "latency_ms") and resp.latency_ms:
                total_latency += resp.latency_ms
            if hasattr(resp, "parse_success"):
                if resp.parse_success:
                    parse_successes += 1
                else:
                    parse_failures += 1
        return {
            "total_requests": len(requests),
            "total_responses": len(responses),
            "total_tokens_used": total_tokens,
            "total_latency_ms": total_latency,
            "average_latency_ms": total_latency / len(responses) if responses else 0,
            "by_persona": by_persona,
            "by_phase": {str(k): v for k, v in sorted(by_phase.items())},
            "parse_successes": parse_successes,
            "parse_failures": parse_failures,
        }

    async def get_investigation_state_artifact(self, binder_id: str) -> Artifact | None:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type="investigation_state", limit=1)
        return artifacts[0] if artifacts else None

    async def get_phase_states(self, binder_id: str, status: str | None = None) -> list[Artifact]:
        artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type="phase_state", limit=20)
        if status is not None:
            result = []
            for artifact in artifacts:
                if hasattr(artifact, "status") and artifact.status == status:
                    result.append(artifact)
            return result
        return artifacts

    async def list_investigations_with_state(
        self, outcome: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        binders = await self.list_binders(status=status, limit=limit)
        results = []
        for binder_info in binders:
            binder_id = binder_info["id"]
            state = await self.get_investigation_state_artifact(binder_id)
            state_info: dict[str, Any] = {
                "binder_id": binder_id,
                "investigation_id": binder_info["investigation_id"],
                "binder_status": binder_info["status"],
                "created_at": binder_info["created_at"],
                "updated_at": binder_info["updated_at"],
            }
            if state:
                if hasattr(state, "current_phase"):
                    state_info["current_phase"] = state.current_phase
                if hasattr(state, "status"):
                    state_info["investigation_status"] = state.status
                if hasattr(state, "outcome"):
                    state_info["outcome"] = state.outcome
            if outcome is not None:
                if state_info.get("outcome") != outcome:
                    continue
            results.append(state_info)
        return results

    async def get_similar_investigations(
        self, error_function: str | None = None, error_message_pattern: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        all_binders = await self.list_binders(limit=200)
        similar = []
        for binder_info in all_binders:
            binder_id = binder_info["id"]
            artifacts = await self.query_artifacts(binder_id=binder_id, artifact_type="error_context", limit=1)
            if not artifacts:
                continue
            artifact = artifacts[0]
            match_score = 0.0
            if error_function and hasattr(artifact, "error_function"):
                if artifact.error_function == error_function:
                    match_score += 0.5
                elif error_function in str(getattr(artifact, "error_function", "")):
                    match_score += 0.25
            if error_message_pattern and hasattr(artifact, "error_message"):
                if error_message_pattern in str(getattr(artifact, "error_message", "")):
                    match_score += 0.5
            if match_score > 0:
                similar.append(
                    {
                        "binder_id": binder_id,
                        "investigation_id": binder_info["investigation_id"],
                        "match_score": match_score,
                        "created_at": binder_info["created_at"],
                    }
                )
        similar.sort(key=lambda x: x["match_score"], reverse=True)
        return similar[:limit]
