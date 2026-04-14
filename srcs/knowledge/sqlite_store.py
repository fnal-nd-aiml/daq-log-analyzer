"""
File: sqlite_store.py
Purpose: SQLite storage for structured data.
Category: Utility
Author: artdaq team
Depends: models
Exports: SQLiteStore
Complexity: High | Lines: 837
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
import aiosqlite
from srcs.models import (
    CalibrationBucket,
    CalibrationData,
    ErrorPattern,
    ErrorSignature,
    Investigation,
    Log,
    PatternMatch,
    RootCausePattern,
)
from .sqlite_analytics import SQLiteAnalyticsMixin
from .sqlite_helpers import row_to_calibration, row_to_investigation, row_to_pattern, row_to_root_cause
from .sqlite_schema import SCHEMA
from .store_interface import StructuredStore

logger = logging.getLogger(__name__)


class SQLiteStore(SQLiteAnalyticsMixin, StructuredStore):

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def initialize(self) -> None:
        await self._ensure_initialized()

    async def close(self) -> None:
        pass

    async def _ensure_initialized(self) -> None:
        if not self._initialized:
            async with aiosqlite.connect(self.db_path) as conn:
                await conn.executescript(SCHEMA)
                await conn.commit()
                await self._run_migrations(conn)
            self._initialized = True

    async def _run_migrations(self, conn: aiosqlite.Connection) -> None:
        async with conn.execute("PRAGMA table_info(investigations)") as cursor:
            rows = await cursor.fetchall()
            existing_columns = {row[1] for row in rows}
        if "processing_tier" not in existing_columns:
            await conn.execute("ALTER TABLE investigations ADD COLUMN processing_tier INTEGER DEFAULT 3")
            await conn.commit()
        async with conn.execute("PRAGMA table_info(error_patterns)") as cursor:
            rows = await cursor.fetchall()
            pattern_columns = {row[1] for row in rows}
        if "user_verified" not in pattern_columns:
            await conn.execute("ALTER TABLE error_patterns ADD COLUMN user_verified BOOLEAN DEFAULT FALSE")
            await conn.commit()
        async with conn.execute("PRAGMA table_info(feedback_records)") as cursor:
            rows = await cursor.fetchall()
            feedback_columns = {row[1] for row in rows}
        if "feedback_source" not in feedback_columns:
            await conn.execute("ALTER TABLE feedback_records ADD COLUMN feedback_source TEXT DEFAULT 'cli'")
            await conn.commit()

    async def store_investigation(self, investigation: Investigation) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("BEGIN")
            try:
                await self._store_investigation_record(conn, investigation)
                await self._store_hypotheses(conn, investigation)
                await self._store_evidence_items(conn, investigation)
                await self._store_causal_chains(conn, investigation)
                await self._store_challenges(conn, investigation)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def _store_investigation_record(self, conn: aiosqlite.Connection, investigation: Investigation) -> None:
        await conn.execute(
            """
            INSERT OR REPLACE INTO investigations (
                id, timestamp, trigger_error_json, context_logs_json,
                outcome, hypotheses_json, evidence_json, causal_chains_json,
                challenges_json, matched_pattern_id, similar_investigation_ids_json,
                duration_seconds, started_at, completed_at, processing_tier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                investigation.id,
                investigation.started_at.isoformat(),
                investigation.trigger_error.model_dump_json(),
                json.dumps([log.model_dump(mode="json") for log in investigation.context_logs]),
                investigation.outcome.value if investigation.outcome else None,
                json.dumps([h.model_dump(mode="json") for h in investigation.hypotheses]),
                investigation.evidence.model_dump_json(),
                json.dumps([c.model_dump(mode="json") for c in investigation.causal_chains]),
                json.dumps([ch.model_dump(mode="json") for ch in investigation.challenges]),
                investigation.matched_pattern_id,
                json.dumps(investigation.similar_investigation_ids),
                (
                    (investigation.completed_at - investigation.started_at).total_seconds()
                    if investigation.completed_at
                    else None
                ),
                investigation.started_at.isoformat(),
                investigation.completed_at.isoformat() if investigation.completed_at else None,
                getattr(investigation, "processing_tier", 3),
            ),
        )

    async def _store_hypotheses(self, conn: aiosqlite.Connection, investigation: Investigation) -> None:
        for rank, hypothesis in enumerate(investigation.hypotheses):
            await conn.execute(
                """
                INSERT OR REPLACE INTO hypotheses (
                    id, investigation_id, description, source,
                    prior_probability, score, rank
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis.id,
                    investigation.id,
                    hypothesis.description,
                    hypothesis.source,
                    hypothesis.prior,
                    hypothesis.score,
                    rank,
                ),
            )

    async def _store_evidence_items(self, conn: aiosqlite.Connection, investigation: Investigation) -> None:
        for item in investigation.evidence.items.values():
            await conn.execute(
                """
                INSERT OR REPLACE INTO evidence_items (
                    id, investigation_id, evidence_type, content,
                    source, strength
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (item.id, investigation.id, item.evidence_type, item.content, item.source, item.strength),
            )

    async def _store_causal_chains(self, conn: aiosqlite.Connection, investigation: Investigation) -> None:
        strength_map = {"STRONG": 0.9, "MODERATE": 0.6, "WEAK": 0.3, "NONE": 0.0}
        for chain in investigation.causal_chains:
            hypothesis_id = None
            if investigation.hypotheses:
                hypothesis_id = investigation.hypotheses[0].id
            root_cause = chain.steps[0].claim if chain.steps else None
            final_effect = chain.steps[-1].claim if chain.steps else None
            if not root_cause and investigation.hypotheses:
                hyp_id = getattr(chain, "hypothesis_id", None)
                if hyp_id:
                    for h in investigation.hypotheses:
                        if h.id == hyp_id:
                            root_cause = h.description
                            break
                if not root_cause:
                    root_cause = investigation.hypotheses[0].description
            await conn.execute(
                """
                INSERT OR REPLACE INTO causal_chains (
                    id, investigation_id, hypothesis_id, root_cause,
                    final_effect, chain_strength
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chain.id, investigation.id, hypothesis_id, root_cause, final_effect, chain.logical_validity),
            )
            for step_num, step in enumerate(chain.steps):
                confidence = strength_map.get(step.evidence_strength, 0.0)
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO causal_steps (
                        id, chain_id, step_number, cause, effect,
                        mechanism, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (step.id, chain.id, step_num, step.claim, step.claim, step.mechanism, confidence),
                )

    async def _store_challenges(self, conn: aiosqlite.Connection, investigation: Investigation) -> None:
        for challenge in investigation.challenges:
            hypothesis_id = None
            if investigation.hypotheses:
                hypothesis_id = investigation.hypotheses[0].id
            await conn.execute(
                """
                INSERT OR REPLACE INTO challenges (
                    id, investigation_id, hypothesis_id, challenge_type,
                    description, severity, requires_response, resolved, resolution
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    challenge.id,
                    investigation.id,
                    hypothesis_id,
                    (
                        challenge.challenge_type
                        if challenge.challenge_type and challenge.challenge_type != "unknown"
                        else "unspecified"
                    ),
                    challenge.content,
                    challenge.severity,
                    challenge.requires_response,
                    challenge.resolved,
                    challenge.resolution,
                ),
            )

    async def get_investigation(self, investigation_id: str) -> Investigation | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM investigations WHERE id = ?", (investigation_id,)) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return row_to_investigation(dict(row))

    async def get_recent_investigations(self, limit: int = 100, offset: int = 0) -> list[Investigation]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT * FROM investigations ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset)
            ) as cursor:
                rows = await cursor.fetchall()
                return [row_to_investigation(dict(row)) for row in rows]

    async def count_investigations(self) -> int:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute("SELECT COUNT(*) FROM investigations") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def find_pattern(self, signature: ErrorSignature) -> PatternMatch | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT * FROM error_patterns
                WHERE is_active = TRUE
                AND (signature_function = ? OR signature_function IS NULL)
                ORDER BY times_seen DESC
                """,
                (signature.function,),
            ) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    pattern = row_to_pattern(dict(row))
                    pattern_sig = ErrorSignature(
                        function=pattern.signature_function,
                        message_pattern=pattern.signature_message_pattern or "",
                        level=pattern.signature_level,
                    )
                    if pattern_sig.matches(signature):
                        matched_fields = []
                        if pattern.signature_function:
                            matched_fields.append("function")
                        if pattern.signature_message_pattern:
                            matched_fields.append("message_pattern")
                        confidence = pattern.pattern_confidence
                        return PatternMatch(pattern=pattern, confidence=confidence, matched_fields=matched_fields)
        return None

    async def get_pattern_root_causes(self, pattern_id: str) -> list[RootCausePattern]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                """
                SELECT * FROM root_cause_patterns
                WHERE error_pattern_id = ?
                ORDER BY frequency DESC
                """,
                (pattern_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [row_to_root_cause(dict(row)) for row in rows]

    async def get_patterns_by_ids(self, pattern_ids: list[str]) -> list[ErrorPattern]:
        if not pattern_ids:
            return []
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            placeholders = ",".join("?" * len(pattern_ids))
            async with conn.execute(
                f"SELECT * FROM error_patterns WHERE id IN ({placeholders})", pattern_ids
            ) as cursor:
                rows = await cursor.fetchall()
                return [row_to_pattern(dict(row)) for row in rows]

    async def get_pattern_statistics(self) -> dict[str, Any]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            stats = {}
            async with conn.execute("SELECT COUNT(*) FROM error_patterns") as cursor:
                stats["total_patterns"] = (await cursor.fetchone())[0]
            async with conn.execute("SELECT COUNT(*) FROM error_patterns WHERE is_active = TRUE") as cursor:
                stats["active_patterns"] = (await cursor.fetchone())[0]
            async with conn.execute(
                "SELECT AVG(pattern_confidence) FROM error_patterns WHERE is_active = TRUE"
            ) as cursor:
                result = (await cursor.fetchone())[0]
                stats["average_confidence"] = result if result else 0.0
            async with conn.execute(
                """
                SELECT
                    SUM(CASE WHEN times_correct > times_incorrect THEN 1 ELSE 0 END) as high_accuracy,
                    SUM(CASE WHEN times_correct <= times_incorrect THEN 1 ELSE 0 END) as low_accuracy
                FROM error_patterns
                WHERE is_active = TRUE AND times_seen >= 5
                """
            ) as cursor:
                row = await cursor.fetchone()
                stats["high_accuracy_patterns"] = row[0] if row[0] else 0
                stats["low_accuracy_patterns"] = row[1] if row[1] else 0
            async with conn.execute("SELECT COUNT(*) FROM root_cause_patterns") as cursor:
                stats["root_cause_patterns"] = (await cursor.fetchone())[0]
        return stats

    async def update_pattern_stats(self, pattern_id: str, correct: bool) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            if correct:
                await conn.execute(
                    """
                    UPDATE error_patterns
                    SET times_correct = times_correct + 1,
                        times_seen = times_seen + 1,
                        last_seen = ?,
                        pattern_confidence = CAST(times_correct + 1 AS REAL) / (times_seen + 1)
                    WHERE id = ?
                    """,
                    (datetime.now().isoformat(), pattern_id),
                )
            else:
                await conn.execute(
                    """
                    UPDATE error_patterns
                    SET times_incorrect = times_incorrect + 1,
                        times_seen = times_seen + 1,
                        last_seen = ?,
                        pattern_confidence = CAST(times_correct AS REAL) / (times_seen + 1)
                    WHERE id = ?
                    """,
                    (datetime.now().isoformat(), pattern_id),
                )
            await conn.commit()

    async def list_patterns(
        self, active_only: bool = True, limit: int = 50, offset: int = 0
    ) -> tuple[list[ErrorPattern], int]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            where_clause = "WHERE is_active = TRUE" if active_only else ""
            count_where = "WHERE is_active = TRUE" if active_only else ""
            async with conn.execute(f"SELECT COUNT(*) FROM error_patterns {count_where}") as cursor:
                total = (await cursor.fetchone())[0]
            async with conn.execute(
                f"\n                SELECT * FROM error_patterns\n                {where_clause}\n                ORDER BY pattern_confidence DESC, times_seen DESC\n                LIMIT ? OFFSET ?\n                ",
                (limit, offset),
            ) as cursor:
                rows = await cursor.fetchall()
                patterns = [row_to_pattern(dict(row)) for row in rows]
        return (patterns, total)

    async def deactivate_pattern(self, pattern_id: str) -> bool:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute("UPDATE error_patterns SET is_active = FALSE WHERE id = ?", (pattern_id,))
            await conn.commit()
            return cursor.rowcount > 0

    async def get_pattern_by_id(self, pattern_id: str) -> ErrorPattern | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM error_patterns WHERE id = ?", (pattern_id,)) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return row_to_pattern(dict(row))

    async def get_calibration(self, model: str, error_type: str | None = None) -> CalibrationData | None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if error_type:
                query = "SELECT * FROM model_calibration WHERE model_name = ? AND error_type = ?"
                params = (model, error_type)
            else:
                query = "SELECT * FROM model_calibration WHERE model_name = ? AND error_type IS NULL"
                params = (model,)
            async with conn.execute(query, params) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return row_to_calibration(dict(row))

    async def update_calibration(self, model: str, stated: float, actual: bool, error_type: str | None = None) -> None:
        await self._ensure_initialized()
        bucket_key = self._get_bucket_key(stated)
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            calibration = await self.get_calibration(model, error_type)
            if calibration is None:
                calibration = CalibrationData(
                    model_name=model, error_type=error_type, buckets={}, overall_bias=0.0, sample_size=0
                )
            if bucket_key not in calibration.buckets:
                calibration.buckets[bucket_key] = CalibrationBucket(
                    stated_confidence=stated, actual_accuracy=1.0 if actual else 0.0, sample_count=1
                )
            else:
                bucket = calibration.buckets[bucket_key]
                new_count = bucket.sample_count + 1
                new_accuracy = (bucket.actual_accuracy * bucket.sample_count + (1.0 if actual else 0.0)) / new_count
                calibration.buckets[bucket_key] = CalibrationBucket(
                    stated_confidence=(bucket.stated_confidence * bucket.sample_count + stated) / new_count,
                    actual_accuracy=new_accuracy,
                    sample_count=new_count,
                )
            calibration.sample_size += 1
            calibration.overall_bias = self._calculate_overall_bias(calibration.buckets)
            await conn.execute(
                """
                INSERT OR REPLACE INTO model_calibration (
                    id, model_name, error_type, buckets_json, overall_bias, sample_size, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{model}:{error_type or 'general'}",
                    model,
                    error_type,
                    json.dumps({k: v.model_dump() for k, v in calibration.buckets.items()}),
                    calibration.overall_bias,
                    calibration.sample_size,
                    datetime.now().isoformat(),
                ),
            )
            await conn.commit()

    def _get_bucket_key(self, confidence: float) -> str:
        bucket_start = int(confidence * 10) / 10
        bucket_end = min(1.0, bucket_start + 0.1)
        return f"{bucket_start:.1f}-{bucket_end:.1f}"

    def _calculate_overall_bias(self, buckets: dict[str, CalibrationBucket]) -> float:
        if not buckets:
            return 0.0
        total_weight = 0
        weighted_bias = 0.0
        for bucket in buckets.values():
            if bucket.sample_count > 0:
                bias = bucket.stated_confidence - bucket.actual_accuracy
                weight = bucket.sample_count
                weighted_bias += bias * weight
                total_weight += weight
        return weighted_bias / total_weight if total_weight > 0 else 0.0

    async def record_feedback(
        self,
        investigation_id: str,
        was_correct: bool,
        actual_cause: str | None = None,
        feedback_notes: str | None = None,
        user_id: str | None = None,
        patterns_updated: list[str] | None = None,
        patterns_created: list[str] | None = None,
        feedback_source: str = "cli",
    ) -> str:
        await self._ensure_initialized()
        from srcs.models import generate_id

        feedback_id = generate_id()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO feedback_records (
                    id, investigation_id, was_correct, actual_cause,
                    feedback_notes, user_id, patterns_updated_json,
                    patterns_created_json, feedback_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback_id,
                    investigation_id,
                    was_correct,
                    actual_cause,
                    feedback_notes,
                    user_id,
                    json.dumps(patterns_updated or []),
                    json.dumps(patterns_created or []),
                    feedback_source,
                ),
            )
            await conn.commit()
        return feedback_id

    async def get_feedback_history(self, investigation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if investigation_id:
                query = """
                    SELECT * FROM feedback_records
                    WHERE investigation_id = ?
                    ORDER BY created_at DESC LIMIT ?
                """
                params = (investigation_id, limit)
            else:
                query = """
                    SELECT * FROM feedback_records
                    ORDER BY created_at DESC LIMIT ?
                """
                params = (limit,)
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": row["id"],
                        "investigation_id": row["investigation_id"],
                        "was_correct": bool(row["was_correct"]),
                        "actual_cause": row["actual_cause"],
                        "feedback_notes": row["feedback_notes"],
                        "user_id": row["user_id"],
                        "created_at": row["created_at"],
                        "patterns_updated": json.loads(row["patterns_updated_json"] or "[]"),
                        "patterns_created": json.loads(row["patterns_created_json"] or "[]"),
                    }
                    for row in rows
                ]

    async def get_all_calibrations(self) -> list[CalibrationData]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM model_calibration") as cursor:
                rows = await cursor.fetchall()
            results = []
            for row in rows:
                results.append(row_to_calibration(dict(row)))
            return results

    async def create_pattern(
        self, pattern: ErrorPattern, root_cause_description: str, evidence_patterns: list[str]
    ) -> None:
        await self._ensure_initialized()
        from srcs.models import generate_id

        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("BEGIN")
            try:
                await conn.execute(
                    """
                    INSERT INTO error_patterns (
                        id, name, description, signature_function,
                        signature_message_pattern, signature_level,
                        times_seen, times_correct, times_incorrect,
                        pattern_confidence, is_active, first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pattern.id,
                        pattern.name,
                        pattern.description,
                        pattern.signature_function,
                        pattern.signature_message_pattern,
                        pattern.signature_level,
                        pattern.times_seen,
                        pattern.times_correct,
                        pattern.times_incorrect,
                        pattern.pattern_confidence,
                        pattern.is_active,
                        pattern.first_seen.isoformat() if pattern.first_seen else None,
                        pattern.last_seen.isoformat() if pattern.last_seen else None,
                    ),
                )
                await conn.execute(
                    """
                    INSERT INTO root_cause_patterns (
                        id, error_pattern_id, description, frequency,
                        confirming_evidence, refuting_evidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        generate_id(),
                        pattern.id,
                        root_cause_description,
                        pattern.pattern_confidence,
                        json.dumps(evidence_patterns),
                        json.dumps([]),
                    ),
                )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def update_pattern(
        self, pattern_id: str, times_seen: int, times_correct: int, times_incorrect: int, pattern_confidence: float
    ) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                UPDATE error_patterns
                SET times_seen = ?,
                    times_correct = ?,
                    times_incorrect = ?,
                    pattern_confidence = ?,
                    last_seen = ?
                WHERE id = ?
                """,
                (
                    times_seen,
                    times_correct,
                    times_incorrect,
                    pattern_confidence,
                    datetime.now().isoformat(),
                    pattern_id,
                ),
            )
            await conn.commit()

    async def find_similar_patterns(self, signature: ErrorSignature, limit: int = 10) -> list[ErrorPattern]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            query = """
                SELECT * FROM error_patterns
                WHERE is_active = TRUE
                AND (
                    (signature_function = ? AND signature_function IS NOT NULL)
                    OR (signature_message_pattern LIKE ? AND signature_message_pattern IS NOT NULL)
                )
                ORDER BY pattern_confidence DESC
                LIMIT ?
            """
            message_pattern = f"%{signature.message_pattern[:50]}%" if signature.message_pattern else "%"
            async with conn.execute(query, (signature.function, message_pattern, limit)) as cursor:
                rows = await cursor.fetchall()
            return [row_to_pattern(dict(row)) for row in rows]

    async def find_patterns_by_cause(self, cause: str, limit: int = 5) -> list[ErrorPattern]:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            keywords = cause.split()[:5]
            conditions = []
            params: list[Any] = []
            for kw in keywords:
                if len(kw) > 3:
                    conditions.append("description LIKE ?")
                    params.append(f"%{kw}%")
            if not conditions:
                return []
            params.append(limit)
            query = f"\n                SELECT * FROM error_patterns\n                WHERE is_active = TRUE AND ({' OR '.join(conditions)})\n                ORDER BY pattern_confidence DESC\n                LIMIT ?\n            "
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
            return [row_to_pattern(dict(row)) for row in rows]

    async def decay_old_patterns(self, threshold_date: str, decay_factor: float) -> int:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """
                SELECT id, pattern_confidence
                FROM error_patterns
                WHERE last_seen < ? AND is_active = TRUE
                """,
                (threshold_date,),
            ) as cursor:
                rows = await cursor.fetchall()
            count = 0
            for row in rows:
                new_confidence = row[1] * decay_factor
                if new_confidence < 0.1:
                    await conn.execute("UPDATE error_patterns SET is_active = FALSE WHERE id = ?", (row[0],))
                else:
                    await conn.execute(
                        "UPDATE error_patterns SET pattern_confidence = ? WHERE id = ?", (new_confidence, row[0])
                    )
                count += 1
            await conn.commit()
        return count

    async def find_similar_investigations_by_signature(self, signature: ErrorSignature, limit: int = 100) -> list[str]:
        await self._ensure_initialized()
        from .patterns import extract_signature

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            query = """
                SELECT id, trigger_error_json, outcome
                FROM investigations
                WHERE outcome IN ('CONFIDENT', 'PROBABLE')
                ORDER BY timestamp DESC
                LIMIT ?
            """
            async with conn.execute(query, (limit,)) as cursor:
                rows = await cursor.fetchall()
            similar = []
            for row in rows:
                try:
                    trigger = Log.model_validate_json(row["trigger_error_json"])
                    trigger_sig = extract_signature(
                        function=trigger.function,
                        message=trigger.message,
                        level=trigger.level,
                        component=trigger.component,
                    )
                    if self._signatures_similar(signature, trigger_sig):
                        similar.append(row["id"])
                except Exception:
                    pass
            return similar

    def _signatures_similar(self, sig1: ErrorSignature, sig2: ErrorSignature) -> bool:
        if sig1.function and sig2.function and (sig1.function == sig2.function):
            return True
        if sig1.message_pattern and sig2.message_pattern:
            pattern1 = sig1.message_pattern[:50]
            pattern2 = sig2.message_pattern[:50]
            if pattern1 in pattern2 or pattern2 in pattern1:
                return True
            words1 = set(re.findall("\\w+", pattern1.lower()))
            words2 = set(re.findall("\\w+", pattern2.lower()))
            common = len(words1 & words2)
            total = len(words1 | words2)
            if total > 0 and common / total > 0.7:
                return True
        return False

    async def ensure_calibration_history_table(self) -> None:
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
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
            """
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cal_history_model ON calibration_history(model_name, recorded_at)"
            )
            await conn.commit()

    async def record_calibration_snapshot(
        self,
        model: str,
        error_type: str | None,
        overall_bias: float,
        sample_size: int,
        overall_accuracy: float,
        buckets_json: str,
    ) -> None:
        await self.ensure_calibration_history_table()
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO calibration_history (
                    model_name, error_type, recorded_at,
                    overall_bias, sample_size, overall_accuracy, buckets_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model,
                    error_type,
                    datetime.now().isoformat(),
                    overall_bias,
                    sample_size,
                    overall_accuracy,
                    buckets_json,
                ),
            )
            await conn.commit()

    async def get_calibration_trend(self, model: str, error_type: str | None, limit: int = 30) -> list[dict[str, Any]]:
        await self.ensure_calibration_history_table()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            if error_type:
                query = """
                    SELECT * FROM calibration_history
                    WHERE model_name = ? AND error_type = ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                """
                params: tuple = (model, error_type, limit)
            else:
                query = """
                    SELECT * FROM calibration_history
                    WHERE model_name = ? AND error_type IS NULL
                    ORDER BY recorded_at DESC
                    LIMIT ?
                """
                params = (model, limit)
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
        return [
            {
                "recorded_at": row["recorded_at"],
                "overall_bias": row["overall_bias"],
                "sample_size": row["sample_size"],
                "overall_accuracy": row["overall_accuracy"],
                "buckets_json": row["buckets_json"],
            }
            for row in reversed(list(rows))
        ]

    async def clear_calibration_history(self, model: str | None = None) -> None:
        await self.ensure_calibration_history_table()
        async with aiosqlite.connect(self.db_path) as conn:
            if model:
                await conn.execute("DELETE FROM calibration_history WHERE model_name = ?", (model,))
            else:
                await conn.execute("DELETE FROM calibration_history")
            await conn.commit()
