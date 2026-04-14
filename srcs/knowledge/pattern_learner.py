"""
File: pattern_learner.py
Purpose: Pattern learning from completed investigations.
Category: Utility
Author: artdaq team
Depends: models
Exports: PatternLearner
Complexity: Medium | Lines: 580
"""

from __future__ import annotations
import json
import logging
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
import aiosqlite
from srcs.models import ErrorPattern, ErrorSignature, Evidence, Investigation, InvestigationOutcome, Log
from .calibration import wilson_score_interval
from .chroma_store import ChromaStore
from .learning_config import LearningConfig, PatternCandidate
from .patterns import extract_signature, normalize_message

if TYPE_CHECKING:
    from .store_interface import StructuredStore
logger = logging.getLogger(__name__)


class PatternLearner:

    def __init__(
        self,
        db_path: str | None = None,
        config: LearningConfig | None = None,
        chroma_store: "ChromaStore | None" = None,
        store: "StructuredStore | None" = None,
    ):
        from .store_interface import StructuredStore as StoreInterface

        self._store: StoreInterface | None = store
        self.db_path = db_path or "./data/knowledge.db"
        self.config = config or LearningConfig()
        self._chroma_store = chroma_store

    @classmethod
    def from_store(
        cls, store: "StructuredStore", config: LearningConfig | None = None, chroma_store: "ChromaStore | None" = None
    ) -> "PatternLearner":
        return cls(db_path=None, config=config, chroma_store=chroma_store, store=store)

    async def learn_from_investigation_by_id(
        self, investigation_id: str, was_correct: bool | None = None
    ) -> list[ErrorPattern]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM investigations WHERE id = ?", (investigation_id,)) as cursor:
                row = await cursor.fetchone()
            if not row:
                logger.warning("Investigation %s not found for learning", investigation_id)
                return []
            row_dict = dict(row)
            try:
                trigger_error = Log.model_validate_json(row_dict["trigger_error_json"])
                outcome = InvestigationOutcome(row_dict["outcome"]) if row_dict["outcome"] else None
                hypotheses = []
                if row_dict.get("hypotheses_json"):
                    from srcs.models import Hypothesis

                    hyp_data = json.loads(row_dict["hypotheses_json"])
                    hypotheses = [Hypothesis.model_validate(h) for h in hyp_data]
                from srcs.models import Evidence as EvidenceModel

                evidence = EvidenceModel()
                if row_dict.get("evidence_json"):
                    ev_data = json.loads(row_dict["evidence_json"])
                    evidence = EvidenceModel.model_validate(ev_data)
                investigation = Investigation(
                    id=row_dict["id"],
                    trigger_error=trigger_error,
                    context_logs=[],
                    hypotheses=hypotheses,
                    evidence=evidence,
                    outcome=outcome,
                    started_at=datetime.fromisoformat(row_dict["timestamp"]),
                )
                return await self.learn_from_investigation(investigation, was_correct)
            except Exception as e:
                logger.error("Failed to reconstruct investigation %s: %s", investigation_id, e)
                return []

    async def learn_from_investigation(
        self, investigation: Investigation, was_correct: bool | None = None
    ) -> list[ErrorPattern]:
        if investigation.outcome not in [InvestigationOutcome.CONFIDENT, InvestigationOutcome.PROBABLE]:
            logger.debug("Skipping learning for %s investigation", investigation.outcome)
            return []
        candidate = self._extract_pattern_candidate(investigation)
        if candidate is None:
            return []
        existing = await self._find_similar_patterns(candidate.signature)
        if existing:
            updated = await self._update_pattern(existing[0], candidate, was_correct)
            return [updated] if updated else []
        else:
            similar_investigations = await self._find_similar_investigations(candidate.signature)
            if len(similar_investigations) >= self.config.min_investigations_for_pattern:
                pattern = await self._create_pattern(candidate, similar_investigations)
                return [pattern] if pattern else []
        return []

    def _extract_pattern_candidate(self, investigation: Investigation) -> PatternCandidate | None:
        if not investigation.hypotheses:
            return None
        top_hypothesis = max(investigation.hypotheses, key=lambda h: h.score)
        if top_hypothesis.score < self.config.min_confidence_for_pattern:
            return None
        signature = extract_signature(
            function=investigation.trigger_error.function,
            message=investigation.trigger_error.message,
            level=investigation.trigger_error.level,
            component=investigation.trigger_error.component,
        )
        evidence_patterns = self._extract_evidence_patterns(investigation.evidence)
        return PatternCandidate(
            signature=signature,
            root_cause=top_hypothesis.description,
            supporting_investigations=[investigation.id],
            evidence_patterns=evidence_patterns,
            confidence=min(top_hypothesis.score, 1.0),
            times_seen=1,
        )

    def _extract_evidence_patterns(self, evidence: Evidence) -> list[str]:
        patterns = []
        for item in evidence.items.values():
            if item.strength in ["STRONG", "MODERATE"]:
                normalized = normalize_message(item.content)
                if len(normalized) < 200:
                    patterns.append(normalized)
        return patterns[:10]

    async def _find_similar_patterns(self, signature: ErrorSignature) -> list[ErrorPattern]:
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
                LIMIT 10
            """
            message_pattern = f"%{signature.message_pattern[:50]}%" if signature.message_pattern else "%"
            async with conn.execute(query, (signature.function, message_pattern)) as cursor:
                rows = await cursor.fetchall()
            patterns = []
            for row in rows:
                row_dict = dict(row)
                patterns.append(
                    ErrorPattern(
                        id=row_dict["id"],
                        name=row_dict["name"],
                        description=row_dict.get("description"),
                        signature_function=row_dict.get("signature_function"),
                        signature_message_pattern=row_dict.get("signature_message_pattern"),
                        signature_level=row_dict.get("signature_level", "ERROR"),
                        times_seen=row_dict.get("times_seen", 0),
                        times_correct=row_dict.get("times_correct", 0),
                        times_incorrect=row_dict.get("times_incorrect", 0),
                        pattern_confidence=row_dict.get("pattern_confidence", 0.0),
                        is_active=row_dict.get("is_active", True),
                        first_seen=(
                            datetime.fromisoformat(row_dict["first_seen"]) if row_dict.get("first_seen") else None
                        ),
                        last_seen=datetime.fromisoformat(row_dict["last_seen"]) if row_dict.get("last_seen") else None,
                    )
                )
            return patterns

    async def _find_similar_investigations(self, signature: ErrorSignature) -> list[str]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            query = """
                SELECT id, trigger_error_json, outcome
                FROM investigations
                WHERE outcome IN ('CONFIDENT', 'PROBABLE')
                ORDER BY timestamp DESC
                LIMIT 100
            """
            async with conn.execute(query) as cursor:
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
                except Exception as e:
                    logger.debug("Failed to parse investigation %s: %s", row["id"], e)
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
            if total > 0 and common / total > self.config.pattern_similarity_threshold:
                return True
        return False

    async def _update_pattern(
        self, pattern: ErrorPattern, candidate: PatternCandidate, was_correct: bool | None
    ) -> ErrorPattern | None:
        async with aiosqlite.connect(self.db_path) as conn:
            new_times_seen = pattern.times_seen + 1
            new_times_correct = pattern.times_correct + (1 if was_correct else 0)
            new_times_incorrect = pattern.times_incorrect + (1 if was_correct is False else 0)
            if new_times_seen >= self.config.min_samples_for_confidence:
                lower, _ = wilson_score_interval(new_times_correct, new_times_seen)
                new_confidence = lower
            else:
                prior_weight = 0.3
                sample_weight = 0.7 * (new_times_seen / self.config.min_samples_for_confidence)
                simple_ratio = new_times_correct / max(1, new_times_seen)
                new_confidence = (prior_weight * pattern.pattern_confidence + sample_weight * simple_ratio) / (
                    prior_weight + sample_weight
                )
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
                    new_times_seen,
                    new_times_correct,
                    new_times_incorrect,
                    new_confidence,
                    datetime.now().isoformat(),
                    pattern.id,
                ),
            )
            await conn.commit()
            pattern.times_seen = new_times_seen
            pattern.times_correct = new_times_correct
            pattern.times_incorrect = new_times_incorrect
            pattern.pattern_confidence = new_confidence
            pattern.last_seen = datetime.now()
            await self._store_pattern_in_chroma(pattern, candidate)
            return pattern

    async def _create_pattern(
        self, candidate: PatternCandidate, similar_investigations: list[str]
    ) -> ErrorPattern | None:
        from srcs.models import generate_id

        pattern_id = generate_id()
        now = datetime.now()
        name = candidate.root_cause
        times_seen = len(similar_investigations)
        if times_seen >= self.config.min_samples_for_confidence:
            estimated_correct = min(int(times_seen * candidate.confidence), times_seen)
            lower, _ = wilson_score_interval(estimated_correct, times_seen)
            initial_confidence = lower
        else:
            initial_confidence = candidate.confidence * 0.8
        pattern = ErrorPattern(
            id=pattern_id,
            name=name,
            description=candidate.root_cause,
            signature_function=candidate.signature.function,
            signature_message_pattern=candidate.signature.message_pattern,
            signature_level=candidate.signature.level,
            times_seen=times_seen,
            times_correct=0,
            times_incorrect=0,
            pattern_confidence=initial_confidence,
            is_active=True,
            first_seen=now,
            last_seen=now,
        )
        async with aiosqlite.connect(self.db_path) as conn:
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
                    pattern.first_seen.isoformat(),
                    pattern.last_seen.isoformat(),
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
                    candidate.root_cause,
                    candidate.confidence,
                    json.dumps(candidate.evidence_patterns),
                    json.dumps([]),
                ),
            )
            await conn.commit()
        await self._store_pattern_in_chroma(pattern, candidate)
        logger.info("Created new pattern: %s (id=%s)", pattern.name, pattern.id)
        return pattern

    async def _store_pattern_in_chroma(self, pattern: ErrorPattern, candidate: PatternCandidate) -> None:
        if self._chroma_store is None:
            return
        try:
            description_parts = [
                f"Error pattern: {pattern.name}",
                f"Description: {pattern.description or candidate.root_cause}",
            ]
            if pattern.signature_function:
                description_parts.append(f"Function: {pattern.signature_function}")
            if pattern.signature_message_pattern:
                description_parts.append(f"Message pattern: {pattern.signature_message_pattern}")
            if candidate.evidence_patterns:
                description_parts.append(f"Evidence patterns: {', '.join(candidate.evidence_patterns[:3])}")
            explanation = " | ".join(description_parts)
            metadata = {
                "pattern_name": pattern.name,
                "signature_function": pattern.signature_function,
                "signature_level": pattern.signature_level,
                "pattern_confidence": pattern.pattern_confidence,
                "times_seen": pattern.times_seen,
            }
            await self._chroma_store.store_error_explanation(
                pattern_id=pattern.id, explanation=explanation, metadata=metadata
            )
            logger.debug("Stored pattern %s in ChromaDB", pattern.id)
        except Exception as e:
            logger.warning("Failed to store pattern in ChromaDB: %s", e)

    async def apply_feedback(
        self, investigation_id: str, was_correct: bool, actual_cause: str | None = None, feedback_source: str = "cli"
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {"patterns_updated": [], "patterns_created": [], "calibration_updated": False}
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("SELECT * FROM investigations WHERE id = ?", (investigation_id,)) as cursor:
                row = await cursor.fetchone()
            if not row:
                logger.warning("Investigation %s not found", investigation_id)
                return updates
            try:
                trigger = Log.model_validate_json(row["trigger_error_json"])
                signature = extract_signature(
                    function=trigger.function, message=trigger.message, level=trigger.level, component=trigger.component
                )
            except Exception as e:
                logger.error("Failed to parse investigation: %s", e)
                return updates
        matched_pattern_id = row["matched_pattern_id"] if "matched_pattern_id" in row.keys() else None
        if matched_pattern_id:
            await self._update_pattern_feedback(matched_pattern_id, was_correct)
            updates["patterns_updated"].append(matched_pattern_id)
        if not was_correct and actual_cause:
            confidence = 0.9 if feedback_source == "slack_interactive" else 0.8
            candidate = PatternCandidate(
                signature=signature,
                root_cause=actual_cause,
                supporting_investigations=[investigation_id],
                confidence=confidence,
                times_seen=1,
            )
            existing = await self._find_patterns_by_cause(actual_cause)
            if existing:
                pattern = await self._update_pattern(existing[0], candidate, True)
                if pattern:
                    updates["patterns_updated"].append(pattern.id)
                    if feedback_source == "slack_interactive":
                        await self._mark_user_verified(pattern.id)
            else:
                pattern = await self._create_pattern(candidate, [investigation_id])
                if pattern:
                    updates["patterns_created"].append(pattern.id)
                    if feedback_source == "slack_interactive":
                        await self._mark_user_verified(pattern.id)
        updates["calibration_updated"] = True
        return updates

    async def _update_pattern_feedback(self, pattern_id: str, was_correct: bool) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute(
                "SELECT times_seen, times_correct, times_incorrect, name FROM error_patterns WHERE id = ?",
                (pattern_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return
            new_times_seen = row["times_seen"] + 1
            new_times_correct = row["times_correct"] + (1 if was_correct else 0)
            new_times_incorrect = row["times_incorrect"] + (0 if was_correct else 1)
            if new_times_seen >= self.config.min_samples_for_confidence:
                lower, _ = wilson_score_interval(new_times_correct, new_times_seen)
                new_confidence = lower
            else:
                new_confidence = new_times_correct / new_times_seen
            should_deactivate = False
            if new_times_seen >= self.config.min_samples_for_deactivation:
                accuracy = new_times_correct / new_times_seen
                if accuracy < self.config.min_accuracy_threshold:
                    should_deactivate = True
                    logger.warning(
                        f"Pattern '{row['name']}' ({pattern_id}) accuracy dropped to {accuracy:.1%} ({new_times_correct}/{new_times_seen}), deactivating"
                    )
            if should_deactivate:
                await conn.execute(
                    """
                    UPDATE error_patterns
                    SET times_correct = ?,
                        times_incorrect = ?,
                        times_seen = ?,
                        pattern_confidence = ?,
                        is_active = FALSE,
                        last_seen = ?
                    WHERE id = ?
                    """,
                    (
                        new_times_correct,
                        new_times_incorrect,
                        new_times_seen,
                        new_confidence,
                        datetime.now().isoformat(),
                        pattern_id,
                    ),
                )
            elif was_correct:
                await conn.execute(
                    """
                    UPDATE error_patterns
                    SET times_correct = times_correct + 1,
                        times_seen = times_seen + 1,
                        pattern_confidence = ?,
                        last_seen = ?
                    WHERE id = ?
                    """,
                    (new_confidence, datetime.now().isoformat(), pattern_id),
                )
            else:
                await conn.execute(
                    """
                    UPDATE error_patterns
                    SET times_incorrect = times_incorrect + 1,
                        times_seen = times_seen + 1,
                        pattern_confidence = ?,
                        last_seen = ?
                    WHERE id = ?
                    """,
                    (new_confidence, datetime.now().isoformat(), pattern_id),
                )
            await conn.commit()

    async def _find_patterns_by_cause(self, cause: str) -> list[ErrorPattern]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            keywords = cause.split()[:5]
            conditions = []
            params = []
            for kw in keywords:
                if len(kw) > 3:
                    conditions.append("description LIKE ?")
                    params.append(f"%{kw}%")
            if not conditions:
                return []
            query = f"\n                SELECT * FROM error_patterns\n                WHERE is_active = TRUE AND ({' OR '.join(conditions)})\n                ORDER BY pattern_confidence DESC\n                LIMIT 5\n            "
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
            return [
                ErrorPattern(
                    id=row_dict["id"],
                    name=row_dict["name"],
                    description=row_dict.get("description"),
                    signature_function=row_dict.get("signature_function"),
                    signature_message_pattern=row_dict.get("signature_message_pattern"),
                    signature_level=row_dict.get("signature_level", "ERROR"),
                    times_seen=row_dict.get("times_seen", 0),
                    times_correct=row_dict.get("times_correct", 0),
                    times_incorrect=row_dict.get("times_incorrect", 0),
                    pattern_confidence=row_dict.get("pattern_confidence", 0.0),
                    is_active=row_dict.get("is_active", True),
                )
                for row in rows
                for row_dict in [dict(row)]
            ]

    async def _mark_user_verified(self, pattern_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("UPDATE error_patterns SET user_verified = TRUE WHERE id = ?", (pattern_id,))
            await conn.commit()
        logger.info("Marked pattern %s as user-verified", pattern_id)

    async def decay_old_patterns(self, months_threshold: int = 6) -> int:
        threshold_date = datetime.now() - timedelta(days=months_threshold * 30)
        decay_factor = self.config.pattern_decay_factor**months_threshold
        async with aiosqlite.connect(self.db_path) as conn:
            async with conn.execute(
                """
                SELECT id, pattern_confidence
                FROM error_patterns
                WHERE last_seen < ? AND is_active = TRUE
                """,
                (threshold_date.isoformat(),),
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
        logger.info("Decayed %s old patterns", count)
        return count

    async def get_pattern_statistics(self) -> dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as conn:
            stats: dict[str, Any] = {}
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
