"""
File: sql_store.py
Purpose: Backend-agnostic implementation of the structured store.
Category: Utility
Author: artdaq team
Depends: models
Exports: SqlStructuredStore, MAX_PATTERN_CANDIDATES, STRENGTH_TO_CONFIDENCE
Complexity: High | Lines: 590
"""

from __future__ import annotations
import json
import logging
import re
from abc import abstractmethod
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any
from srcs.models import CalibrationBucket, CalibrationData, ErrorPattern, ErrorSignature, Investigation, Log, PatternMatch, RootCausePattern
from .row_mappers import row_to_calibration, row_to_investigation, row_to_pattern, row_to_root_cause
from .sql import SqlConnection, SqlDialect
from .store_interface import StructuredStore
logger = logging.getLogger(__name__)
MAX_PATTERN_CANDIDATES = 200
STRENGTH_TO_CONFIDENCE = {'STRONG': 0.9, 'MODERATE': 0.6, 'WEAK': 0.3, 'NONE': 0.0}

class SqlStructuredStore(StructuredStore):
    dialect: SqlDialect

    @abstractmethod
    def _connect(self) -> AbstractAsyncContextManager[SqlConnection]:
        pass

    @abstractmethod
    async def _ensure_initialized(self) -> None:
        pass

    def _acquire(self) -> AbstractAsyncContextManager[SqlConnection]:
        return self._connect()

    async def initialize(self) -> None:
        await self._ensure_initialized()

    async def store_investigation(self, investigation: Investigation) -> None:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            async with conn.transaction():
                await self._store_investigation_record(conn, investigation)
                await self._store_hypotheses(conn, investigation)
                await self._store_evidence_items(conn, investigation)
                await self._store_causal_chains(conn, investigation)
                await self._store_challenges(conn, investigation)

    async def _store_investigation_record(self, conn: SqlConnection, investigation: Investigation) -> None:
        columns = ['id', 'timestamp', 'trigger_error_json', 'context_logs_json', 'outcome', 'hypotheses_json', 'evidence_json', 'causal_chains_json', 'challenges_json', 'matched_pattern_id', 'similar_investigation_ids_json', 'duration_seconds', 'started_at', 'completed_at', 'processing_tier', 'confidence']
        await conn.execute(self.dialect.upsert('investigations', columns), (investigation.id, investigation.started_at.isoformat(), investigation.trigger_error.model_dump_json(), json.dumps([log.model_dump(mode='json') for log in investigation.context_logs]), investigation.outcome.value if investigation.outcome else None, json.dumps([h.model_dump(mode='json') for h in investigation.hypotheses]), investigation.evidence.model_dump_json(), json.dumps([c.model_dump(mode='json') for c in investigation.causal_chains]), json.dumps([ch.model_dump(mode='json') for ch in investigation.challenges]), investigation.matched_pattern_id, json.dumps(investigation.similar_investigation_ids), (investigation.completed_at - investigation.started_at).total_seconds() if investigation.completed_at else None, investigation.started_at.isoformat(), investigation.completed_at.isoformat() if investigation.completed_at else None, getattr(investigation, 'processing_tier', 3), investigation.confidence))

    async def _store_hypotheses(self, conn: SqlConnection, investigation: Investigation) -> None:
        columns = ['id', 'investigation_id', 'description', 'source', 'prior_probability', 'score', 'rank']
        statement = self.dialect.upsert('hypotheses', columns)
        for rank, hypothesis in enumerate(investigation.hypotheses):
            await conn.execute(statement, (hypothesis.id, investigation.id, hypothesis.description, hypothesis.source, hypothesis.prior, hypothesis.score, rank))

    async def _store_evidence_items(self, conn: SqlConnection, investigation: Investigation) -> None:
        columns = ['id', 'investigation_id', 'evidence_type', 'content', 'source', 'strength']
        statement = self.dialect.upsert('evidence_items', columns)
        for item in investigation.evidence.items.values():
            await conn.execute(statement, (item.id, investigation.id, item.evidence_type, item.content, item.source, item.strength))

    async def _store_causal_chains(self, conn: SqlConnection, investigation: Investigation) -> None:
        chain_statement = self.dialect.upsert('causal_chains', ['id', 'investigation_id', 'hypothesis_id', 'root_cause', 'final_effect', 'chain_strength'])
        step_statement = self.dialect.upsert('causal_steps', ['id', 'chain_id', 'step_number', 'cause', 'effect', 'mechanism', 'confidence'])
        for chain in investigation.causal_chains:
            hypothesis_id = investigation.hypotheses[0].id if investigation.hypotheses else None
            root_cause = chain.steps[0].claim if chain.steps else None
            final_effect = chain.steps[-1].claim if chain.steps else None
            if not root_cause and investigation.hypotheses:
                hyp_id = getattr(chain, 'hypothesis_id', None)
                if hyp_id:
                    for h in investigation.hypotheses:
                        if h.id == hyp_id:
                            root_cause = h.description
                            break
                if not root_cause:
                    root_cause = investigation.hypotheses[0].description
            await conn.execute(chain_statement, (chain.id, investigation.id, hypothesis_id, root_cause, final_effect, chain.logical_validity))
            for step_num, step in enumerate(chain.steps):
                await conn.execute(step_statement, (step.id, chain.id, step_num, step.claim, step.claim, step.mechanism, STRENGTH_TO_CONFIDENCE.get(step.evidence_strength, 0.0)))

    async def _store_challenges(self, conn: SqlConnection, investigation: Investigation) -> None:
        columns = ['id', 'investigation_id', 'hypothesis_id', 'challenge_type', 'description', 'severity', 'requires_response', 'resolved', 'resolution']
        statement = self.dialect.upsert('challenges', columns)
        for challenge in investigation.challenges:
            hypothesis_id = investigation.hypotheses[0].id if investigation.hypotheses else None
            await conn.execute(statement, (challenge.id, investigation.id, hypothesis_id, challenge.challenge_type if challenge.challenge_type and challenge.challenge_type != 'unknown' else 'unspecified', challenge.content, challenge.severity, challenge.requires_response, challenge.resolved, challenge.resolution))

    async def get_investigation(self, investigation_id: str) -> Investigation | None:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            row = await conn.fetch_one('SELECT * FROM investigations WHERE id = ?', (investigation_id,))
            return row_to_investigation(row) if row is not None else None

    async def get_recent_investigations(self, limit: int=100, offset: int=0, outcome: str | None=None) -> list[Investigation]:
        await self._ensure_initialized()
        where = 'WHERE outcome = ?' if outcome is not None else ''
        params: list[Any] = [outcome] if outcome is not None else []
        params.extend([limit, offset])
        async with self._acquire() as conn:
            rows = await conn.fetch_all(f'SELECT * FROM investigations {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?', params)
            return [row_to_investigation(row) for row in rows]

    async def count_investigations(self, outcome: str | None=None) -> int:
        await self._ensure_initialized()
        where = 'WHERE outcome = ?' if outcome is not None else ''
        params: list[Any] = [outcome] if outcome is not None else []
        async with self._acquire() as conn:
            return int(await conn.fetch_value(f'SELECT COUNT(*) FROM investigations {where}', params, default=0))

    async def find_pattern(self, signature: ErrorSignature) -> PatternMatch | None:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            rows = await conn.fetch_all('''
                SELECT * FROM error_patterns
                WHERE is_active = TRUE
                AND (signature_function = ? OR signature_function IS NULL)
                ORDER BY times_seen DESC
                LIMIT ?
                ''', (signature.function, MAX_PATTERN_CANDIDATES))
        for row in rows:
            pattern = row_to_pattern(row)
            pattern_sig = ErrorSignature(function=pattern.signature_function, message_pattern=pattern.signature_message_pattern or '', level=pattern.signature_level)
            if pattern_sig.matches(signature):
                matched_fields = []
                if pattern.signature_function:
                    matched_fields.append('function')
                if pattern.signature_message_pattern:
                    matched_fields.append('message_pattern')
                return PatternMatch(pattern=pattern, confidence=pattern.pattern_confidence, matched_fields=matched_fields)
        return None

    async def get_pattern_root_causes(self, pattern_id: str) -> list[RootCausePattern]:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            rows = await conn.fetch_all('''
                SELECT * FROM root_cause_patterns
                WHERE error_pattern_id = ?
                ORDER BY frequency DESC
                ''', (pattern_id,))
            return [row_to_root_cause(row) for row in rows]

    async def get_patterns_by_ids(self, pattern_ids: list[str]) -> list[ErrorPattern]:
        if not pattern_ids:
            return []
        await self._ensure_initialized()
        placeholders = ','.join('?' * len(pattern_ids))
        async with self._acquire() as conn:
            rows = await conn.fetch_all(f'SELECT * FROM error_patterns WHERE id IN ({placeholders})', pattern_ids)
            return [row_to_pattern(row) for row in rows]

    async def get_pattern_by_id(self, pattern_id: str) -> ErrorPattern | None:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            row = await conn.fetch_one('SELECT * FROM error_patterns WHERE id = ?', (pattern_id,))
            return row_to_pattern(row) if row is not None else None

    async def get_pattern_statistics(self) -> dict[str, Any]:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            stats: dict[str, Any] = {'total_patterns': await conn.fetch_value('SELECT COUNT(*) FROM error_patterns', default=0), 'active_patterns': await conn.fetch_value('SELECT COUNT(*) FROM error_patterns WHERE is_active = TRUE', default=0), 'average_confidence': await conn.fetch_value('SELECT AVG(pattern_confidence) FROM error_patterns WHERE is_active = TRUE', default=0.0)}
            accuracy = await conn.fetch_one('''
                SELECT
                    SUM(CASE WHEN times_correct > times_incorrect THEN 1 ELSE 0 END)
                        AS high_accuracy,
                    SUM(CASE WHEN times_correct <= times_incorrect THEN 1 ELSE 0 END)
                        AS low_accuracy
                FROM error_patterns
                WHERE is_active = TRUE AND times_seen >= 5
                ''')
            stats['high_accuracy_patterns'] = (accuracy or {}).get('high_accuracy') or 0
            stats['low_accuracy_patterns'] = (accuracy or {}).get('low_accuracy') or 0
            stats['root_cause_patterns'] = await conn.fetch_value('SELECT COUNT(*) FROM root_cause_patterns', default=0)
        return stats

    async def update_pattern_stats(self, pattern_id: str, correct: bool) -> None:
        await self._ensure_initialized()
        if correct:
            sql = '''
                UPDATE error_patterns
                SET times_correct = times_correct + 1,
                    times_seen = times_seen + 1,
                    last_seen = ?,
                    pattern_confidence =
                        CAST(times_correct + 1 AS REAL) / (times_seen + 1)
                WHERE id = ?
            '''
        else:
            sql = '''
                UPDATE error_patterns
                SET times_incorrect = times_incorrect + 1,
                    times_seen = times_seen + 1,
                    last_seen = ?,
                    pattern_confidence =
                        CAST(times_correct AS REAL) / (times_seen + 1)
                WHERE id = ?
            '''
        async with self._acquire() as conn:
            await conn.execute(sql, (datetime.now().isoformat(), pattern_id))

    async def list_patterns(self, active_only: bool=True, limit: int=50, offset: int=0) -> tuple[list[ErrorPattern], int]:
        await self._ensure_initialized()
        where = 'WHERE is_active = TRUE' if active_only else ''
        async with self._acquire() as conn:
            total = int(await conn.fetch_value(f'SELECT COUNT(*) FROM error_patterns {where}', default=0))
            rows = await conn.fetch_all(f'\n                SELECT * FROM error_patterns\n                {where}\n                ORDER BY pattern_confidence DESC, times_seen DESC\n                LIMIT ? OFFSET ?\n                ', (limit, offset))
        return ([row_to_pattern(row) for row in rows], total)

    async def deactivate_pattern(self, pattern_id: str) -> bool:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            affected = await conn.execute('UPDATE error_patterns SET is_active = FALSE WHERE id = ?', (pattern_id,))
            return int(affected) > 0

    async def create_pattern(self, pattern: ErrorPattern, root_cause_description: str, evidence_patterns: list[str]) -> None:
        await self._ensure_initialized()
        from srcs.models import generate_id
        async with self._acquire() as conn:
            async with conn.transaction():
                await conn.execute('''
                    INSERT INTO error_patterns (
                        id, name, description, signature_function,
                        signature_message_pattern, signature_level,
                        times_seen, times_correct, times_incorrect,
                        pattern_confidence, is_active, first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (pattern.id, pattern.name, pattern.description, pattern.signature_function, pattern.signature_message_pattern, pattern.signature_level, pattern.times_seen, pattern.times_correct, pattern.times_incorrect, pattern.pattern_confidence, pattern.is_active, pattern.first_seen.isoformat() if pattern.first_seen else None, pattern.last_seen.isoformat() if pattern.last_seen else None))
                await conn.execute('''
                    INSERT INTO root_cause_patterns (
                        id, error_pattern_id, description, frequency,
                        confirming_evidence, refuting_evidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ''', (generate_id(), pattern.id, root_cause_description, pattern.pattern_confidence, json.dumps(evidence_patterns), json.dumps([])))

    async def update_pattern(self, pattern_id: str, times_seen: int, times_correct: int, times_incorrect: int, pattern_confidence: float) -> None:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            await conn.execute('''
                UPDATE error_patterns
                SET times_seen = ?,
                    times_correct = ?,
                    times_incorrect = ?,
                    pattern_confidence = ?,
                    last_seen = ?
                WHERE id = ?
                ''', (times_seen, times_correct, times_incorrect, pattern_confidence, datetime.now().isoformat(), pattern_id))

    async def find_similar_patterns(self, signature: ErrorSignature, limit: int=10) -> list[ErrorPattern]:
        await self._ensure_initialized()
        message_pattern = f'%{signature.message_pattern[:50]}%' if signature.message_pattern else '%'
        async with self._acquire() as conn:
            rows = await conn.fetch_all('''
                SELECT * FROM error_patterns
                WHERE is_active = TRUE
                AND (
                    (signature_function = ? AND signature_function IS NOT NULL)
                    OR (signature_message_pattern LIKE ?
                        AND signature_message_pattern IS NOT NULL)
                )
                ORDER BY pattern_confidence DESC
                LIMIT ?
                ''', (signature.function, message_pattern, limit))
            return [row_to_pattern(row) for row in rows]

    async def find_patterns_by_cause(self, cause: str, limit: int=5) -> list[ErrorPattern]:
        await self._ensure_initialized()
        conditions = []
        params: list[Any] = []
        for keyword in cause.split()[:5]:
            if len(keyword) > 3:
                conditions.append('description LIKE ?')
                params.append(f'%{keyword}%')
        if not conditions:
            return []
        params.append(limit)
        async with self._acquire() as conn:
            rows = await conn.fetch_all(f"\n                SELECT * FROM error_patterns\n                WHERE is_active = TRUE AND ({' OR '.join(conditions)})\n                ORDER BY pattern_confidence DESC\n                LIMIT ?\n                ", params)
            return [row_to_pattern(row) for row in rows]

    async def decay_old_patterns(self, threshold_date: str, decay_factor: float) -> int:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            rows = await conn.fetch_all('''
                SELECT id, pattern_confidence
                FROM error_patterns
                WHERE last_seen < ? AND is_active = TRUE
                ''', (threshold_date,))
            count = 0
            for row in rows:
                new_confidence = row['pattern_confidence'] * decay_factor
                if new_confidence < 0.1:
                    await conn.execute('UPDATE error_patterns SET is_active = FALSE WHERE id = ?', (row['id'],))
                else:
                    await conn.execute('UPDATE error_patterns SET pattern_confidence = ? WHERE id = ?', (new_confidence, row['id']))
                count += 1
        return count

    async def find_similar_investigations_by_signature(self, signature: ErrorSignature, limit: int=100) -> list[str]:
        await self._ensure_initialized()
        from .patterns import extract_signature
        async with self._acquire() as conn:
            rows = await conn.fetch_all("""
                SELECT id, trigger_error_json, outcome
                FROM investigations
                WHERE outcome IN ('CONFIDENT', 'PROBABLE')
                ORDER BY timestamp DESC
                LIMIT ?
                """, (limit,))
        similar = []
        for row in rows:
            try:
                trigger = Log.model_validate_json(row['trigger_error_json'])
                trigger_sig = extract_signature(function=trigger.function, message=trigger.message, level=trigger.level, component=trigger.component)
                if self._signatures_similar(signature, trigger_sig):
                    similar.append(row['id'])
            except Exception:
                logger.debug('Skipping unparseable investigation %s', row.get('id'))
        return similar

    @staticmethod
    def _signatures_similar(sig1: ErrorSignature, sig2: ErrorSignature) -> bool:
        if sig1.function and sig2.function and (sig1.function == sig2.function):
            return True
        if sig1.message_pattern and sig2.message_pattern:
            pattern1 = sig1.message_pattern[:50]
            pattern2 = sig2.message_pattern[:50]
            if pattern1 in pattern2 or pattern2 in pattern1:
                return True
            words1 = set(re.findall('\\w+', pattern1.lower()))
            words2 = set(re.findall('\\w+', pattern2.lower()))
            total = len(words1 | words2)
            if total > 0 and len(words1 & words2) / total > 0.7:
                return True
        return False

    async def get_calibration(self, model: str, error_type: str | None=None) -> CalibrationData | None:
        await self._ensure_initialized()
        if error_type:
            sql = 'SELECT * FROM model_calibration WHERE model_name = ? AND error_type = ?'
            params: tuple[Any, ...] = (model, error_type)
        else:
            sql = 'SELECT * FROM model_calibration WHERE model_name = ? AND error_type IS NULL'
            params = (model,)
        async with self._acquire() as conn:
            row = await conn.fetch_one(sql, params)
            return row_to_calibration(row) if row is not None else None

    async def update_calibration(self, model: str, stated: float, actual: bool, error_type: str | None=None) -> None:
        await self._ensure_initialized()
        bucket_key = self._get_bucket_key(stated)
        calibration = await self.get_calibration(model, error_type)
        if calibration is None:
            calibration = CalibrationData(model_name=model, error_type=error_type, buckets={}, overall_bias=0.0, sample_size=0)
        if bucket_key not in calibration.buckets:
            calibration.buckets[bucket_key] = CalibrationBucket(stated_confidence=stated, actual_accuracy=1.0 if actual else 0.0, sample_count=1)
        else:
            bucket = calibration.buckets[bucket_key]
            new_count = bucket.sample_count + 1
            calibration.buckets[bucket_key] = CalibrationBucket(stated_confidence=(bucket.stated_confidence * bucket.sample_count + stated) / new_count, actual_accuracy=(bucket.actual_accuracy * bucket.sample_count + (1.0 if actual else 0.0)) / new_count, sample_count=new_count)
        calibration.sample_size += 1
        calibration.overall_bias = self._calculate_overall_bias(calibration.buckets)
        columns = ['id', 'model_name', 'error_type', 'buckets_json', 'overall_bias', 'sample_size', 'last_updated']
        async with self._acquire() as conn:
            await conn.execute(self.dialect.upsert('model_calibration', columns), (f"{model}:{error_type or 'general'}", model, error_type, json.dumps({k: v.model_dump() for k, v in calibration.buckets.items()}), calibration.overall_bias, calibration.sample_size, datetime.now().isoformat()))

    @staticmethod
    def _get_bucket_key(confidence: float) -> str:
        from .calibration import _get_bucket_key
        return _get_bucket_key(confidence)

    @staticmethod
    def _calculate_overall_bias(buckets: dict[str, CalibrationBucket]) -> float:
        if not buckets:
            return 0.0
        total_weight = 0
        weighted_bias = 0.0
        for bucket in buckets.values():
            if bucket.sample_count > 0:
                weighted_bias += (bucket.stated_confidence - bucket.actual_accuracy) * bucket.sample_count
                total_weight += bucket.sample_count
        return weighted_bias / total_weight if total_weight > 0 else 0.0

    async def get_all_calibrations(self) -> list[CalibrationData]:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            rows = await conn.fetch_all('SELECT * FROM model_calibration')
            return [row_to_calibration(row) for row in rows]

    async def record_feedback(self, investigation_id: str, was_correct: bool, actual_cause: str | None=None, feedback_notes: str | None=None, user_id: str | None=None, patterns_updated: list[str] | None=None, patterns_created: list[str] | None=None, feedback_source: str='cli') -> str:
        await self._ensure_initialized()
        from srcs.models import generate_id
        feedback_id = generate_id()
        async with self._acquire() as conn:
            await conn.execute('''
                INSERT INTO feedback_records (
                    id, investigation_id, was_correct, actual_cause,
                    feedback_notes, user_id, patterns_updated_json,
                    patterns_created_json, feedback_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (feedback_id, investigation_id, was_correct, actual_cause, feedback_notes, user_id, json.dumps(patterns_updated or []), json.dumps(patterns_created or []), feedback_source))
        return feedback_id

    async def get_feedback_history(self, investigation_id: str | None=None, limit: int=100) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        if investigation_id:
            sql = '''
                SELECT * FROM feedback_records
                WHERE investigation_id = ?
                ORDER BY created_at DESC LIMIT ?
            '''
            params: tuple[Any, ...] = (investigation_id, limit)
        else:
            sql = '''
                SELECT * FROM feedback_records
                ORDER BY created_at DESC LIMIT ?
            '''
            params = (limit,)
        async with self._acquire() as conn:
            rows = await conn.fetch_all(sql, params)
        return [{'id': row['id'], 'investigation_id': row['investigation_id'], 'was_correct': bool(row['was_correct']), 'actual_cause': row['actual_cause'], 'feedback_notes': row['feedback_notes'], 'user_id': row['user_id'], 'created_at': row['created_at'], 'patterns_updated': json.loads(row['patterns_updated_json'] or '[]'), 'patterns_created': json.loads(row['patterns_created_json'] or '[]')} for row in rows]

    async def record_calibration_snapshot(self, model: str, error_type: str | None, overall_bias: float, sample_size: int, overall_accuracy: float, buckets_json: str) -> None:
        await self.ensure_calibration_history_table()
        async with self._acquire() as conn:
            await conn.execute('''
                INSERT INTO calibration_history (
                    model_name, error_type, recorded_at,
                    overall_bias, sample_size, overall_accuracy, buckets_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (model, error_type, datetime.now().isoformat(), overall_bias, sample_size, overall_accuracy, buckets_json))

    async def get_calibration_trend(self, model: str, error_type: str | None, limit: int=30) -> list[dict[str, Any]]:
        await self.ensure_calibration_history_table()
        if error_type:
            sql = '''
                SELECT * FROM calibration_history
                WHERE model_name = ? AND error_type = ?
                ORDER BY recorded_at DESC
                LIMIT ?
            '''
            params: tuple[Any, ...] = (model, error_type, limit)
        else:
            sql = '''
                SELECT * FROM calibration_history
                WHERE model_name = ? AND error_type IS NULL
                ORDER BY recorded_at DESC
                LIMIT ?
            '''
            params = (model, limit)
        async with self._acquire() as conn:
            rows = await conn.fetch_all(sql, params)
        return [{'recorded_at': row['recorded_at'], 'overall_bias': row['overall_bias'], 'sample_size': row['sample_size'], 'overall_accuracy': row['overall_accuracy'], 'buckets_json': row['buckets_json']} for row in reversed(rows)]

    async def clear_calibration_history(self, model: str | None=None) -> None:
        await self.ensure_calibration_history_table()
        async with self._acquire() as conn:
            if model:
                await conn.execute('DELETE FROM calibration_history WHERE model_name = ?', (model,))
            else:
                await conn.execute('DELETE FROM calibration_history')

    async def update_strategy_performance(self, strategy_name: str, was_correct: bool, confidence: float, rank: int, error_type: str | None=None) -> None:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            existing = await conn.fetch_one('''
                SELECT * FROM hypothesis_strategy_performance
                WHERE strategy_name = ?
                AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                ''', (strategy_name, error_type, error_type))
            if existing:
                used = existing['times_used']
                new_used = used + 1
                await conn.execute('''
                    UPDATE hypothesis_strategy_performance
                    SET times_used = ?, times_correct = ?, avg_confidence = ?,
                        avg_rank = ?, last_used = ?
                    WHERE strategy_name = ?
                    AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                    ''', (new_used, existing['times_correct'] + (1 if was_correct else 0), (existing['avg_confidence'] * used + confidence) / new_used, (existing['avg_rank'] * used + rank) / new_used, datetime.now().isoformat(), strategy_name, error_type, error_type))
            else:
                from srcs.models import generate_id
                await conn.execute('''
                    INSERT INTO hypothesis_strategy_performance (
                        id, strategy_name, error_type, times_used, times_correct,
                        avg_confidence, avg_rank, last_used
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (generate_id(), strategy_name, error_type, 1, 1 if was_correct else 0, confidence, float(rank), datetime.now().isoformat()))

    async def update_query_effectiveness(self, query_type: str, was_useful: bool, evidence_strength: float, result_count: int, error_type: str | None=None) -> None:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            existing = await conn.fetch_one('''
                SELECT * FROM query_type_effectiveness
                WHERE query_type = ?
                AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                ''', (query_type, error_type, error_type))
            if existing:
                used = existing['times_used']
                new_used = used + 1
                await conn.execute('''
                    UPDATE query_type_effectiveness
                    SET times_used = ?, times_useful = ?, avg_evidence_strength = ?,
                        avg_result_count = ?, last_used = ?
                    WHERE query_type = ?
                    AND (error_type = ? OR (error_type IS NULL AND ? IS NULL))
                    ''', (new_used, existing['times_useful'] + (1 if was_useful else 0), (existing['avg_evidence_strength'] * used + evidence_strength) / new_used, (existing['avg_result_count'] * used + result_count) / new_used, datetime.now().isoformat(), query_type, error_type, error_type))
            else:
                from srcs.models import generate_id
                await conn.execute('''
                    INSERT INTO query_type_effectiveness (
                        id, query_type, error_type, times_used, times_useful,
                        avg_evidence_strength, avg_result_count, last_used
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (generate_id(), query_type, error_type, 1, 1 if was_useful else 0, evidence_strength, float(result_count), datetime.now().isoformat()))

    async def get_strategy_performance(self, error_type: str | None=None) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        if error_type:
            sql = '''
                SELECT * FROM hypothesis_strategy_performance
                WHERE error_type = ?
                ORDER BY times_correct DESC
            '''
            params: tuple[Any, ...] = (error_type,)
        else:
            sql = '''
                SELECT * FROM hypothesis_strategy_performance
                ORDER BY times_correct DESC
            '''
            params = ()
        async with self._acquire() as conn:
            rows = await conn.fetch_all(sql, params)
        return [{'strategy_name': row['strategy_name'], 'error_type': row['error_type'], 'times_used': row['times_used'], 'times_correct': row['times_correct'], 'accuracy': row['times_correct'] / row['times_used'] if row['times_used'] > 0 else 0, 'avg_confidence': row['avg_confidence'], 'avg_rank': row['avg_rank'], 'last_used': row['last_used']} for row in rows]

    async def get_query_effectiveness(self, error_type: str | None=None) -> list[dict[str, Any]]:
        await self._ensure_initialized()
        if error_type:
            sql = '''
                SELECT * FROM query_type_effectiveness
                WHERE error_type = ?
                ORDER BY times_useful DESC
            '''
            params: tuple[Any, ...] = (error_type,)
        else:
            sql = '''
                SELECT * FROM query_type_effectiveness
                ORDER BY times_useful DESC
            '''
            params = ()
        async with self._acquire() as conn:
            rows = await conn.fetch_all(sql, params)
        return [{'query_type': row['query_type'], 'error_type': row['error_type'], 'times_used': row['times_used'], 'times_useful': row['times_useful'], 'usefulness_rate': row['times_useful'] / row['times_used'] if row['times_used'] > 0 else 0, 'avg_evidence_strength': row['avg_evidence_strength'], 'avg_result_count': row['avg_result_count'], 'last_used': row['last_used']} for row in rows]

    async def get_hypothesis_statistics(self) -> dict[str, Any]:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            stats: dict[str, Any] = {'total_hypotheses': await conn.fetch_value('SELECT COUNT(*) FROM hypotheses', default=0), 'avg_hypotheses_per_investigation': await conn.fetch_value('''
                    SELECT AVG(cnt) FROM (
                        SELECT COUNT(*) AS cnt FROM hypotheses
                        GROUP BY investigation_id
                    ) AS per_investigation
                    ''', default=0), 'avg_winning_score': await conn.fetch_value('SELECT AVG(score) FROM hypotheses WHERE rank = 0', default=0)}
            source_rows = await conn.fetch_all('''
                SELECT source, COUNT(*) AS cnt
                FROM hypotheses
                WHERE source IS NOT NULL
                GROUP BY source
                ORDER BY cnt DESC
                LIMIT 10
                ''')
            stats['hypothesis_sources'] = {row['source']: row['cnt'] for row in source_rows}
        return stats

    async def get_evidence_statistics(self) -> dict[str, Any]:
        await self._ensure_initialized()
        async with self._acquire() as conn:
            stats: dict[str, Any] = {'total_evidence_items': await conn.fetch_value('SELECT COUNT(*) FROM evidence_items', default=0)}
            type_rows = await conn.fetch_all('''
                SELECT evidence_type, COUNT(*) AS cnt
                FROM evidence_items
                GROUP BY evidence_type
                ORDER BY cnt DESC
                ''')
            stats['evidence_by_type'] = {row['evidence_type']: row['cnt'] for row in type_rows}
            strength_rows = await conn.fetch_all('''
                SELECT strength, COUNT(*) AS cnt
                FROM evidence_items
                GROUP BY strength
                ORDER BY cnt DESC
                ''')
            stats['evidence_by_strength'] = {row['strength']: row['cnt'] for row in strength_rows}
        return stats