"""
File: postgres_store.py
Purpose: PostgreSQL storage for structured data.
Category: Utility
Author: artdaq team
Depends: models
Exports: PostgresStore
Complexity: High | Lines: 1182
"""

import json
import logging
import re
from datetime import datetime
from typing import Any
from srcs.models import (
    CalibrationBucket,
    CalibrationData,
    CausalChain,
    Challenge,
    ErrorPattern,
    ErrorSignature,
    Evidence,
    Hypothesis,
    Investigation,
    InvestigationOutcome,
    Log,
    PatternMatch,
    RootCausePattern,
)
from .postgres_schema import SCHEMA
from .store_interface import StructuredStore

logger = logging.getLogger(__name__)
try:
    import asyncpg

    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False
    asyncpg = None


class PostgresStore(StructuredStore):

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "daq_analyzer",
        user: str = "postgres",
        password: str = "",
        min_connections: int = 2,
        max_connections: int = 10,
        ssl: bool = False,
    ):
        if not ASYNCPG_AVAILABLE:
            raise ImportError("asyncpg is required for PostgreSQL support. Install with: pip install asyncpg")
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.ssl = ssl
        self._pool: "asyncpg.Pool | None" = None

    async def initialize(self) -> None:
        if self._pool is not None:
            return
        ssl_context = "require" if self.ssl else None
        self._pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            min_size=self.min_connections,
            max_size=self.max_connections,
            ssl=ssl_context,
        )
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA)
        logger.info(f"PostgreSQL store initialized: {self.host}:{self.port}/{self.database}")

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL connection pool closed")

    async def _get_pool(self) -> "asyncpg.Pool":
        if self._pool is None:
            await self.initialize()
        return self._pool

    async def store_investigation(self, investigation: Investigation) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO investigations (
                        id, timestamp, trigger_error_json, context_logs_json,
                        outcome, hypotheses_json, evidence_json, causal_chains_json,
                        challenges_json, matched_pattern_id, similar_investigation_ids_json,
                        duration_seconds, started_at, completed_at, processing_tier
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    ON CONFLICT (id) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        trigger_error_json = EXCLUDED.trigger_error_json,
                        context_logs_json = EXCLUDED.context_logs_json,
                        outcome = EXCLUDED.outcome,
                        hypotheses_json = EXCLUDED.hypotheses_json,
                        evidence_json = EXCLUDED.evidence_json,
                        causal_chains_json = EXCLUDED.causal_chains_json,
                        challenges_json = EXCLUDED.challenges_json,
                        matched_pattern_id = EXCLUDED.matched_pattern_id,
                        similar_investigation_ids_json = EXCLUDED.similar_investigation_ids_json,
                        duration_seconds = EXCLUDED.duration_seconds,
                        started_at = EXCLUDED.started_at,
                        completed_at = EXCLUDED.completed_at,
                        processing_tier = EXCLUDED.processing_tier
                    """,
                    investigation.id,
                    investigation.started_at,
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
                    investigation.started_at,
                    investigation.completed_at,
                    getattr(investigation, "processing_tier", 3),
                )
                for rank, hypothesis in enumerate(investigation.hypotheses):
                    await conn.execute(
                        """
                        INSERT INTO hypotheses (
                            id, investigation_id, description, source,
                            prior_probability, score, rank
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        ON CONFLICT (id) DO UPDATE SET
                            description = EXCLUDED.description,
                            source = EXCLUDED.source,
                            prior_probability = EXCLUDED.prior_probability,
                            score = EXCLUDED.score,
                            rank = EXCLUDED.rank
                        """,
                        hypothesis.id,
                        investigation.id,
                        hypothesis.description,
                        hypothesis.source,
                        hypothesis.prior,
                        hypothesis.score,
                        rank,
                    )
                for item in investigation.evidence.items.values():
                    await conn.execute(
                        """
                        INSERT INTO evidence_items (
                            id, investigation_id, evidence_type, content,
                            source, strength
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (id) DO UPDATE SET
                            evidence_type = EXCLUDED.evidence_type,
                            content = EXCLUDED.content,
                            source = EXCLUDED.source,
                            strength = EXCLUDED.strength
                        """,
                        item.id,
                        investigation.id,
                        item.evidence_type,
                        item.content,
                        item.source,
                        item.strength,
                    )
                for chain in investigation.causal_chains:
                    hypothesis_id = None
                    if investigation.hypotheses:
                        hypothesis_id = investigation.hypotheses[0].id
                    root_cause = chain.steps[0].claim if chain.steps else None
                    final_effect = chain.steps[-1].claim if chain.steps else None
                    chain_strength = chain.logical_validity
                    await conn.execute(
                        """
                        INSERT INTO causal_chains (
                            id, investigation_id, hypothesis_id, root_cause,
                            final_effect, chain_strength
                        ) VALUES ($1, $2, $3, $4, $5, $6)
                        ON CONFLICT (id) DO UPDATE SET
                            hypothesis_id = EXCLUDED.hypothesis_id,
                            root_cause = EXCLUDED.root_cause,
                            final_effect = EXCLUDED.final_effect,
                            chain_strength = EXCLUDED.chain_strength
                        """,
                        chain.id,
                        investigation.id,
                        hypothesis_id,
                        root_cause,
                        final_effect,
                        chain_strength,
                    )
                    strength_map = {"STRONG": 0.9, "MODERATE": 0.6, "WEAK": 0.3, "NONE": 0.0}
                    for step_num, step in enumerate(chain.steps):
                        confidence = strength_map.get(step.evidence_strength, 0.0)
                        await conn.execute(
                            """
                            INSERT INTO causal_steps (
                                id, chain_id, step_number, cause, effect,
                                mechanism, confidence
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT (id) DO UPDATE SET
                                step_number = EXCLUDED.step_number,
                                cause = EXCLUDED.cause,
                                effect = EXCLUDED.effect,
                                mechanism = EXCLUDED.mechanism,
                                confidence = EXCLUDED.confidence
                            """,
                            step.id,
                            chain.id,
                            step_num,
                            step.claim,
                            step.claim,
                            step.mechanism,
                            confidence,
                        )
                for challenge in investigation.challenges:
                    hypothesis_id = None
                    if investigation.hypotheses:
                        hypothesis_id = investigation.hypotheses[0].id
                    await conn.execute(
                        """
                        INSERT INTO challenges (
                            id, investigation_id, hypothesis_id, challenge_type,
                            description, severity, requires_response, resolved, resolution
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ON CONFLICT (id) DO UPDATE SET
                            hypothesis_id = EXCLUDED.hypothesis_id,
                            challenge_type = EXCLUDED.challenge_type,
                            description = EXCLUDED.description,
                            severity = EXCLUDED.severity,
                            requires_response = EXCLUDED.requires_response,
                            resolved = EXCLUDED.resolved,
                            resolution = EXCLUDED.resolution
                        """,
                        challenge.id,
                        investigation.id,
                        hypothesis_id,
                        challenge.challenge_type,
                        challenge.content,
                        challenge.severity,
                        challenge.requires_response,
                        challenge.resolved,
                        challenge.resolution,
                    )

    async def get_investigation(self, investigation_id: str) -> Investigation | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM investigations WHERE id = $1", investigation_id)
            if row is None:
                return None
            return self._row_to_investigation(dict(row))

    async def get_recent_investigations(self, limit: int = 100, offset: int = 0) -> list[Investigation]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM investigations ORDER BY timestamp DESC LIMIT $1 OFFSET $2", limit, offset
            )
            return [self._row_to_investigation(dict(row)) for row in rows]

    async def count_investigations(self) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchval("SELECT COUNT(*) FROM investigations")
            return row or 0

    def _row_to_investigation(self, row: dict) -> Investigation:
        trigger_error = Log.model_validate_json(row["trigger_error_json"])
        context_logs = []
        if row.get("context_logs_json"):
            context_data = json.loads(row["context_logs_json"])
            context_logs = [Log.model_validate(log) for log in context_data]
        hypotheses = []
        if row.get("hypotheses_json"):
            hyp_data = json.loads(row["hypotheses_json"])
            hypotheses = [Hypothesis.model_validate(h) for h in hyp_data]
        evidence = Evidence()
        if row.get("evidence_json"):
            ev_data = json.loads(row["evidence_json"])
            evidence = Evidence.model_validate(ev_data)
        causal_chains = []
        if row.get("causal_chains_json"):
            chains_data = json.loads(row["causal_chains_json"])
            causal_chains = [CausalChain.model_validate(c) for c in chains_data]
        challenges = []
        if row.get("challenges_json"):
            ch_data = json.loads(row["challenges_json"])
            challenges = [Challenge.model_validate(ch) for ch in ch_data]
        similar_ids = []
        if row.get("similar_investigation_ids_json"):
            similar_ids = json.loads(row["similar_investigation_ids_json"])
        outcome = None
        if row.get("outcome"):
            outcome = InvestigationOutcome(row["outcome"])
        started_at = row["started_at"]
        completed_at = row.get("completed_at")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at)
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)
        return Investigation(
            id=row["id"],
            trigger_error=trigger_error,
            context_logs=context_logs,
            hypotheses=hypotheses,
            evidence=evidence,
            causal_chains=causal_chains,
            challenges=challenges,
            outcome=outcome,
            matched_pattern_id=row.get("matched_pattern_id"),
            similar_investigation_ids=similar_ids,
            started_at=started_at,
            completed_at=completed_at,
        )

    async def find_pattern(self, signature: ErrorSignature) -> PatternMatch | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM error_patterns
                WHERE is_active = TRUE
                AND (signature_function = $1 OR signature_function IS NULL)
                ORDER BY times_seen DESC
                """,
                signature.function,
            )
            for row in rows:
                pattern = self._row_to_pattern(dict(row))
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
                    return PatternMatch(
                        pattern=pattern, confidence=pattern.pattern_confidence, matched_fields=matched_fields
                    )
        return None

    async def get_pattern_by_id(self, pattern_id: str) -> ErrorPattern | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM error_patterns WHERE id = $1", pattern_id)
            if row is None:
                return None
            return self._row_to_pattern(dict(row))

    async def get_patterns_by_ids(self, pattern_ids: list[str]) -> list[ErrorPattern]:
        if not pattern_ids:
            return []
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM error_patterns WHERE id = ANY($1)", pattern_ids)
            return [self._row_to_pattern(dict(row)) for row in rows]

    async def get_pattern_root_causes(self, pattern_id: str) -> list[RootCausePattern]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM root_cause_patterns
                WHERE error_pattern_id = $1
                ORDER BY frequency DESC
                """,
                pattern_id,
            )
            return [self._row_to_root_cause(dict(row)) for row in rows]

    async def list_patterns(
        self, active_only: bool = True, limit: int = 50, offset: int = 0
    ) -> tuple[list[ErrorPattern], int]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            where_clause = "WHERE is_active = TRUE" if active_only else ""
            count_row = await conn.fetchrow(f"SELECT COUNT(*) FROM error_patterns {where_clause}")
            total = count_row[0]
            rows = await conn.fetch(
                f"\n                SELECT * FROM error_patterns\n                {where_clause}\n                ORDER BY pattern_confidence DESC, times_seen DESC\n                LIMIT $1 OFFSET $2\n                ",
                limit,
                offset,
            )
            patterns = [self._row_to_pattern(dict(row)) for row in rows]
        return (patterns, total)

    async def update_pattern_stats(self, pattern_id: str, correct: bool) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if correct:
                await conn.execute(
                    """
                    UPDATE error_patterns
                    SET times_correct = times_correct + 1,
                        times_seen = times_seen + 1,
                        last_seen = $1,
                        pattern_confidence = CAST(times_correct + 1 AS DOUBLE PRECISION) / (times_seen + 1)
                    WHERE id = $2
                    """,
                    datetime.now(),
                    pattern_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE error_patterns
                    SET times_incorrect = times_incorrect + 1,
                        times_seen = times_seen + 1,
                        last_seen = $1,
                        pattern_confidence = CAST(times_correct AS DOUBLE PRECISION) / (times_seen + 1)
                    WHERE id = $2
                    """,
                    datetime.now(),
                    pattern_id,
                )

    async def deactivate_pattern(self, pattern_id: str) -> bool:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("UPDATE error_patterns SET is_active = FALSE WHERE id = $1", pattern_id)
            return "UPDATE 1" in result

    async def get_pattern_statistics(self) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            stats: dict[str, Any] = {}
            row = await conn.fetchrow("SELECT COUNT(*) FROM error_patterns")
            stats["total_patterns"] = row[0]
            row = await conn.fetchrow("SELECT COUNT(*) FROM error_patterns WHERE is_active = TRUE")
            stats["active_patterns"] = row[0]
            row = await conn.fetchrow("SELECT AVG(pattern_confidence) FROM error_patterns WHERE is_active = TRUE")
            stats["average_confidence"] = row[0] if row[0] else 0.0
            row = await conn.fetchrow(
                """
                SELECT
                    SUM(CASE WHEN times_correct > times_incorrect THEN 1 ELSE 0 END) as high_accuracy,
                    SUM(CASE WHEN times_correct <= times_incorrect THEN 1 ELSE 0 END) as low_accuracy
                FROM error_patterns
                WHERE is_active = TRUE AND times_seen >= 5
                """
            )
            stats["high_accuracy_patterns"] = row[0] if row[0] else 0
            stats["low_accuracy_patterns"] = row[1] if row[1] else 0
            row = await conn.fetchrow("SELECT COUNT(*) FROM root_cause_patterns")
            stats["root_cause_patterns"] = row[0]
        return stats

    async def create_pattern(
        self, pattern: ErrorPattern, root_cause_description: str, evidence_patterns: list[str]
    ) -> None:
        from srcs.models import generate_id

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO error_patterns (
                        id, name, description, signature_function,
                        signature_message_pattern, signature_level,
                        times_seen, times_correct, times_incorrect,
                        pattern_confidence, is_active, first_seen, last_seen
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    """,
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
                    pattern.first_seen,
                    pattern.last_seen,
                )
                await conn.execute(
                    """
                    INSERT INTO root_cause_patterns (
                        id, error_pattern_id, description, frequency,
                        confirming_evidence, refuting_evidence
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    generate_id(),
                    pattern.id,
                    root_cause_description,
                    pattern.pattern_confidence,
                    json.dumps(evidence_patterns),
                    json.dumps([]),
                )

    async def update_pattern(
        self, pattern_id: str, times_seen: int, times_correct: int, times_incorrect: int, pattern_confidence: float
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE error_patterns
                SET times_seen = $1,
                    times_correct = $2,
                    times_incorrect = $3,
                    pattern_confidence = $4,
                    last_seen = $5
                WHERE id = $6
                """,
                times_seen,
                times_correct,
                times_incorrect,
                pattern_confidence,
                datetime.now(),
                pattern_id,
            )

    async def find_similar_patterns(self, signature: ErrorSignature, limit: int = 10) -> list[ErrorPattern]:
        pool = await self._get_pool()
        message_pattern = f"%{signature.message_pattern[:50]}%" if signature.message_pattern else "%"
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM error_patterns
                WHERE is_active = TRUE
                AND (
                    (signature_function = $1 AND signature_function IS NOT NULL)
                    OR (signature_message_pattern LIKE $2 AND signature_message_pattern IS NOT NULL)
                )
                ORDER BY pattern_confidence DESC
                LIMIT $3
                """,
                signature.function,
                message_pattern,
                limit,
            )
            return [self._row_to_pattern(dict(row)) for row in rows]

    async def find_patterns_by_cause(self, cause: str, limit: int = 5) -> list[ErrorPattern]:
        pool = await self._get_pool()
        keywords = cause.split()[:5]
        conditions = []
        params: list[Any] = []
        for i, kw in enumerate(keywords, start=1):
            if len(kw) > 3:
                conditions.append(f"description LIKE ${i}")
                params.append(f"%{kw}%")
        if not conditions:
            return []
        params.append(limit)
        async with pool.acquire() as conn:
            query = f"\n                SELECT * FROM error_patterns\n                WHERE is_active = TRUE AND ({' OR '.join(conditions)})\n                ORDER BY pattern_confidence DESC\n                LIMIT ${len(params)}\n            "
            rows = await conn.fetch(query, *params)
            return [self._row_to_pattern(dict(row)) for row in rows]

    async def decay_old_patterns(self, threshold_date: str, decay_factor: float) -> int:
        pool = await self._get_pool()
        threshold_dt = datetime.fromisoformat(threshold_date)
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, pattern_confidence
                FROM error_patterns
                WHERE last_seen < $1 AND is_active = TRUE
                """,
                threshold_dt,
            )
            count = 0
            for row in rows:
                new_confidence = row["pattern_confidence"] * decay_factor
                if new_confidence < 0.1:
                    await conn.execute("UPDATE error_patterns SET is_active = FALSE WHERE id = $1", row["id"])
                else:
                    await conn.execute(
                        "UPDATE error_patterns SET pattern_confidence = $1 WHERE id = $2", new_confidence, row["id"]
                    )
                count += 1
        return count

    def _row_to_pattern(self, row: dict) -> ErrorPattern:
        first_seen = row.get("first_seen")
        last_seen = row.get("last_seen")
        if isinstance(first_seen, str):
            first_seen = datetime.fromisoformat(first_seen)
        if isinstance(last_seen, str):
            last_seen = datetime.fromisoformat(last_seen)
        return ErrorPattern(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            signature_function=row.get("signature_function"),
            signature_message_pattern=row.get("signature_message_pattern"),
            signature_level=row.get("signature_level", "ERROR"),
            times_seen=row.get("times_seen", 0),
            times_correct=row.get("times_correct", 0),
            times_incorrect=row.get("times_incorrect", 0),
            pattern_confidence=row.get("pattern_confidence", 0.0),
            is_active=row.get("is_active", True),
            first_seen=first_seen,
            last_seen=last_seen,
        )

    def _row_to_root_cause(self, row: dict) -> RootCausePattern:
        confirming_evidence = []
        if row.get("confirming_evidence"):
            data = row["confirming_evidence"]
            if isinstance(data, str):
                confirming_evidence = json.loads(data)
            else:
                confirming_evidence = data
        refuting_evidence = []
        if row.get("refuting_evidence"):
            data = row["refuting_evidence"]
            if isinstance(data, str):
                refuting_evidence = json.loads(data)
            else:
                refuting_evidence = data
        return RootCausePattern(
            id=row["id"],
            error_pattern_id=row["error_pattern_id"],
            description=row["description"],
            frequency=row.get("frequency", 0.0),
            confirming_evidence_patterns=confirming_evidence,
            refuting_evidence_patterns=refuting_evidence,
        )

    async def get_calibration(self, model: str, error_type: str | None = None) -> CalibrationData | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if error_type:
                row = await conn.fetchrow(
                    "SELECT * FROM model_calibration WHERE model_name = $1 AND error_type = $2", model, error_type
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM model_calibration WHERE model_name = $1 AND error_type IS NULL", model
                )
            if row is None:
                return None
            return self._row_to_calibration(dict(row))

    async def update_calibration(self, model: str, stated: float, actual: bool, error_type: str | None = None) -> None:
        bucket_key = self._get_bucket_key(stated)
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
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO model_calibration (
                    id, model_name, error_type, buckets_json, overall_bias, sample_size, last_updated
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (model_name, error_type) DO UPDATE SET
                    buckets_json = EXCLUDED.buckets_json,
                    overall_bias = EXCLUDED.overall_bias,
                    sample_size = EXCLUDED.sample_size,
                    last_updated = EXCLUDED.last_updated
                """,
                f"{model}:{error_type or 'general'}",
                model,
                error_type,
                json.dumps({k: v.model_dump() for k, v in calibration.buckets.items()}),
                calibration.overall_bias,
                calibration.sample_size,
                datetime.now(),
            )

    async def get_all_calibrations(self) -> list[CalibrationData]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM model_calibration")
            return [self._row_to_calibration(dict(row)) for row in rows]

    def _row_to_calibration(self, row: dict) -> CalibrationData:
        buckets_raw = row.get("buckets_json", "{}")
        if isinstance(buckets_raw, str):
            buckets_raw = json.loads(buckets_raw)
        buckets = {k: CalibrationBucket.model_validate(v) for k, v in buckets_raw.items()}
        return CalibrationData(
            model_name=row["model_name"],
            error_type=row.get("error_type"),
            buckets=buckets,
            overall_bias=row.get("overall_bias", 0.0),
            sample_size=row.get("sample_size", 0),
        )

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
    ) -> str:
        from srcs.models import generate_id

        feedback_id = generate_id()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO feedback_records (
                    id, investigation_id, was_correct, actual_cause,
                    feedback_notes, user_id, patterns_updated_json, patterns_created_json
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                feedback_id,
                investigation_id,
                was_correct,
                actual_cause,
                feedback_notes,
                user_id,
                json.dumps(patterns_updated or []),
                json.dumps(patterns_created or []),
            )
        return feedback_id

    async def get_feedback_history(self, investigation_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if investigation_id:
                rows = await conn.fetch(
                    """
                    SELECT * FROM feedback_records
                    WHERE investigation_id = $1
                    ORDER BY created_at DESC LIMIT $2
                    """,
                    investigation_id,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM feedback_records
                    ORDER BY created_at DESC LIMIT $1
                    """,
                    limit,
                )
            return [
                {
                    "id": row["id"],
                    "investigation_id": row["investigation_id"],
                    "was_correct": row["was_correct"],
                    "actual_cause": row["actual_cause"],
                    "feedback_notes": row["feedback_notes"],
                    "user_id": row["user_id"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "patterns_updated": json.loads(row["patterns_updated_json"] or "[]"),
                    "patterns_created": json.loads(row["patterns_created_json"] or "[]"),
                }
                for row in rows
            ]

    async def update_strategy_performance(
        self, strategy_name: str, was_correct: bool, confidence: float, rank: int, error_type: str | None = None
    ) -> None:
        from srcs.models import generate_id

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if error_type:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM hypothesis_strategy_performance
                    WHERE strategy_name = $1 AND error_type = $2
                    """,
                    strategy_name,
                    error_type,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM hypothesis_strategy_performance
                    WHERE strategy_name = $1 AND error_type IS NULL
                    """,
                    strategy_name,
                )
            if row:
                new_times_used = row["times_used"] + 1
                new_times_correct = row["times_correct"] + (1 if was_correct else 0)
                new_avg_confidence = (row["avg_confidence"] * row["times_used"] + confidence) / new_times_used
                new_avg_rank = (row["avg_rank"] * row["times_used"] + rank) / new_times_used
                await conn.execute(
                    """
                    UPDATE hypothesis_strategy_performance
                    SET times_used = $1, times_correct = $2, avg_confidence = $3,
                        avg_rank = $4, last_used = $5
                    WHERE id = $6
                    """,
                    new_times_used,
                    new_times_correct,
                    new_avg_confidence,
                    new_avg_rank,
                    datetime.now(),
                    row["id"],
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO hypothesis_strategy_performance (
                        id, strategy_name, error_type, times_used, times_correct,
                        avg_confidence, avg_rank, last_used
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    generate_id(),
                    strategy_name,
                    error_type,
                    1,
                    1 if was_correct else 0,
                    confidence,
                    float(rank),
                    datetime.now(),
                )

    async def update_query_effectiveness(
        self,
        query_type: str,
        was_useful: bool,
        evidence_strength: float,
        result_count: int,
        error_type: str | None = None,
    ) -> None:
        from srcs.models import generate_id

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if error_type:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM query_type_effectiveness
                    WHERE query_type = $1 AND error_type = $2
                    """,
                    query_type,
                    error_type,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM query_type_effectiveness
                    WHERE query_type = $1 AND error_type IS NULL
                    """,
                    query_type,
                )
            if row:
                new_times_used = row["times_used"] + 1
                new_times_useful = row["times_useful"] + (1 if was_useful else 0)
                new_avg_strength = (
                    row["avg_evidence_strength"] * row["times_used"] + evidence_strength
                ) / new_times_used
                new_avg_count = (row["avg_result_count"] * row["times_used"] + result_count) / new_times_used
                await conn.execute(
                    """
                    UPDATE query_type_effectiveness
                    SET times_used = $1, times_useful = $2, avg_evidence_strength = $3,
                        avg_result_count = $4, last_used = $5
                    WHERE id = $6
                    """,
                    new_times_used,
                    new_times_useful,
                    new_avg_strength,
                    new_avg_count,
                    datetime.now(),
                    row["id"],
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO query_type_effectiveness (
                        id, query_type, error_type, times_used, times_useful,
                        avg_evidence_strength, avg_result_count, last_used
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    generate_id(),
                    query_type,
                    error_type,
                    1,
                    1 if was_useful else 0,
                    evidence_strength,
                    float(result_count),
                    datetime.now(),
                )

    async def get_strategy_performance(self, error_type: str | None = None) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if error_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM hypothesis_strategy_performance
                    WHERE error_type = $1
                    ORDER BY times_correct DESC
                    """,
                    error_type,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM hypothesis_strategy_performance
                    ORDER BY times_correct DESC
                    """
                )
            return [
                {
                    "strategy_name": row["strategy_name"],
                    "error_type": row["error_type"],
                    "times_used": row["times_used"],
                    "times_correct": row["times_correct"],
                    "accuracy": row["times_correct"] / row["times_used"] if row["times_used"] > 0 else 0,
                    "avg_confidence": row["avg_confidence"],
                    "avg_rank": row["avg_rank"],
                    "last_used": row["last_used"].isoformat() if row["last_used"] else None,
                }
                for row in rows
            ]

    async def get_query_effectiveness(self, error_type: str | None = None) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if error_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM query_type_effectiveness
                    WHERE error_type = $1
                    ORDER BY times_useful DESC
                    """,
                    error_type,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM query_type_effectiveness
                    ORDER BY times_useful DESC
                    """
                )
            return [
                {
                    "query_type": row["query_type"],
                    "error_type": row["error_type"],
                    "times_used": row["times_used"],
                    "times_useful": row["times_useful"],
                    "usefulness_rate": row["times_useful"] / row["times_used"] if row["times_used"] > 0 else 0,
                    "avg_evidence_strength": row["avg_evidence_strength"],
                    "avg_result_count": row["avg_result_count"],
                    "last_used": row["last_used"].isoformat() if row["last_used"] else None,
                }
                for row in rows
            ]

    async def get_hypothesis_statistics(self) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            stats: dict[str, Any] = {}
            row = await conn.fetchrow("SELECT COUNT(*) FROM hypotheses")
            stats["total_hypotheses"] = row[0]
            row = await conn.fetchrow(
                """
                SELECT AVG(cnt) FROM (
                    SELECT COUNT(*) as cnt FROM hypotheses GROUP BY investigation_id
                ) sub
                """
            )
            stats["avg_hypotheses_per_investigation"] = row[0] or 0
            rows = await conn.fetch(
                """
                SELECT source, COUNT(*) as cnt
                FROM hypotheses
                WHERE source IS NOT NULL
                GROUP BY source
                ORDER BY cnt DESC
                LIMIT 10
                """
            )
            stats["hypothesis_sources"] = {row["source"]: row["cnt"] for row in rows}
            row = await conn.fetchrow("SELECT AVG(score) FROM hypotheses WHERE rank = 0")
            stats["avg_winning_score"] = row[0] or 0
            return stats

    async def get_evidence_statistics(self) -> dict[str, Any]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            stats: dict[str, Any] = {}
            row = await conn.fetchrow("SELECT COUNT(*) FROM evidence_items")
            stats["total_evidence_items"] = row[0]
            rows = await conn.fetch(
                """
                SELECT evidence_type, COUNT(*) as cnt
                FROM evidence_items
                GROUP BY evidence_type
                ORDER BY cnt DESC
                """
            )
            stats["evidence_by_type"] = {row["evidence_type"]: row["cnt"] for row in rows}
            rows = await conn.fetch(
                """
                SELECT strength, COUNT(*) as cnt
                FROM evidence_items
                GROUP BY strength
                ORDER BY cnt DESC
                """
            )
            stats["evidence_by_strength"] = {row["strength"]: row["cnt"] for row in rows}
            return stats

    async def find_similar_investigations_by_signature(self, signature: ErrorSignature, limit: int = 100) -> list[str]:
        from .patterns import extract_signature

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, trigger_error_json, outcome
                FROM investigations
                WHERE outcome IN ('CONFIDENT', 'PROBABLE')
                ORDER BY timestamp DESC
                LIMIT $1
                """,
                limit,
            )
            similar = []
            for row in rows:
                try:
                    trigger_data = row["trigger_error_json"]
                    if isinstance(trigger_data, str):
                        trigger = Log.model_validate_json(trigger_data)
                    else:
                        trigger = Log.model_validate(trigger_data)
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
        pass

    async def record_calibration_snapshot(
        self,
        model: str,
        error_type: str | None,
        overall_bias: float,
        sample_size: int,
        overall_accuracy: float,
        buckets_json: str,
    ) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO calibration_history (
                    model_name, error_type, recorded_at,
                    overall_bias, sample_size, overall_accuracy, buckets_json
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                model,
                error_type,
                datetime.now(),
                overall_bias,
                sample_size,
                overall_accuracy,
                buckets_json,
            )

    async def get_calibration_trend(self, model: str, error_type: str | None, limit: int = 30) -> list[dict[str, Any]]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if error_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM calibration_history
                    WHERE model_name = $1 AND error_type = $2
                    ORDER BY recorded_at DESC
                    LIMIT $3
                    """,
                    model,
                    error_type,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM calibration_history
                    WHERE model_name = $1 AND error_type IS NULL
                    ORDER BY recorded_at DESC
                    LIMIT $2
                    """,
                    model,
                    limit,
                )
        return [
            {
                "recorded_at": row["recorded_at"].isoformat() if row["recorded_at"] else None,
                "overall_bias": row["overall_bias"],
                "sample_size": row["sample_size"],
                "overall_accuracy": row["overall_accuracy"],
                "buckets_json": row["buckets_json"],
            }
            for row in reversed(list(rows))
        ]

    async def clear_calibration_history(self, model: str | None = None) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if model:
                await conn.execute("DELETE FROM calibration_history WHERE model_name = $1", model)
            else:
                await conn.execute("DELETE FROM calibration_history")
